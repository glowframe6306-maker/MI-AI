import hashlib
import hmac
import ipaddress
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import phonenumbers
import requests
from firebase_admin.auth import UserNotFoundError
from flask import current_app, jsonify, request


OTP_SESSION_TTL_SECONDS = 5 * 60
OTP_RESEND_COOLDOWN_SECONDS = 60
OTP_MAX_VERIFICATION_ATTEMPTS = 5
OTP_RATE_WINDOW_SECONDS = 60 * 60
OTP_REQUESTS_PER_PHONE_PER_HOUR = 5
OTP_REQUESTS_PER_IP_PER_HOUR = 30
OTP_GLOBAL_REQUESTS_PER_HOUR = 500
OTP_SENDS_PER_PHONE_PER_HOUR = 5
OTP_SENDS_PER_IP_PER_HOUR = 20
OTP_GLOBAL_SENDS_PER_HOUR = 100
OTP_VERIFY_ATTEMPTS_PER_PHONE_PER_HOUR = 30
OTP_VERIFY_ATTEMPTS_PER_IP_PER_HOUR = 60
OTP_DISPATCH_LEASE_SECONDS = 30
OTP_DOCUMENT_RETENTION_SECONDS = 2 * 24 * 60 * 60
OTP_MAX_REQUEST_BYTES = 4096

OTP_SESSION_COLLECTION = "whatsappOtpSessions"
OTP_ACTIVE_SESSION_COLLECTION = "whatsappOtpActiveSessions"
OTP_RATE_LIMIT_COLLECTION = "whatsappOtpRateLimits"
OTP_SESSION_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
OTP_TEMPLATE_NAME_PATTERN = re.compile(r"^[a-z0-9_]{1,512}$")
OTP_TEMPLATE_LANGUAGE_PATTERN = re.compile(r"^[a-z]{2,3}(?:_[A-Z]{2})?$")


class OtpConfigurationError(RuntimeError):
    pass


def _utcnow():
    return datetime.now(timezone.utc)


def normalize_phone_number(value):
    raw_number = str(value or "").strip()
    if not raw_number.startswith("+") or len(raw_number) > 64:
        raise ValueError("A valid international phone number is required.")

    try:
        parsed = phonenumbers.parse(raw_number, None)
    except phonenumbers.NumberParseException as exc:
        raise ValueError("A valid international phone number is required.") from exc

    if not phonenumbers.is_valid_number(parsed):
        raise ValueError("A valid international phone number is required.")

    return phonenumbers.format_number(
        parsed,
        phonenumbers.PhoneNumberFormat.E164,
    )


def generate_otp():
    return str(secrets.randbelow(100_000_000)).zfill(8)


def _load_otp_config(dependencies):
    secret = (os.getenv("WHATSAPP_OTP_HMAC_SECRET") or "").strip().encode("utf-8")
    phone_number_id = (os.getenv("WHATSAPP_OTP_PHONE_NUMBER_ID") or "").strip()
    access_token = (os.getenv("WHATSAPP_OTP_ACCESS_TOKEN") or "").strip()
    template_name = (os.getenv("WHATSAPP_OTP_TEMPLATE_NAME") or "").strip()
    template_language = (os.getenv("WHATSAPP_OTP_TEMPLATE_LANGUAGE") or "").strip()

    if len(secret) < 32:
        raise OtpConfigurationError("OTP signing configuration is unavailable.")
    if not phone_number_id.isdigit() or not access_token:
        raise OtpConfigurationError("OTP sender configuration is unavailable.")
    if not OTP_TEMPLATE_NAME_PATTERN.fullmatch(template_name):
        raise OtpConfigurationError("OTP template configuration is unavailable.")
    if not OTP_TEMPLATE_LANGUAGE_PATTERN.fullmatch(template_language):
        raise OtpConfigurationError("OTP template configuration is unavailable.")

    try:
        graph_api_version = dependencies["graph_api_version_provider"]()
    except (RuntimeError, ValueError) as exc:
        raise OtpConfigurationError("OTP sender configuration is unavailable.") from exc

    if not re.fullmatch(r"v\d+\.\d+", str(graph_api_version or "")):
        raise OtpConfigurationError("OTP sender configuration is unavailable.")

    return {
        "secret": secret,
        "phone_number_id": phone_number_id,
        "access_token": access_token,
        "template_name": template_name,
        "template_language": template_language,
        "graph_api_version": graph_api_version,
    }


def _hmac_digest(secret, purpose, value):
    message = ("cortex-whatsapp-otp:" + purpose + ":" + str(value)).encode("utf-8")
    return hmac.new(secret, message, hashlib.sha256).hexdigest()


def _otp_digest(secret, session_id, phone_key, code):
    return _hmac_digest(
        secret,
        "code",
        session_id + ":" + phone_key + ":" + code,
    )


def _get_snapshot_data(reference, transaction=None):
    snapshot = reference.get(transaction=transaction) if transaction else reference.get()
    if not snapshot.exists:
        return None
    return snapshot.to_dict() or {}


def _to_utc_datetime(value):
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _rate_reference(database, secret, scope, subject):
    rate_id = _hmac_digest(secret, "rate:" + scope, subject)
    return database.collection(OTP_RATE_LIMIT_COLLECTION).document(rate_id)


def _window_state(data, name, now):
    started_at = _to_utc_datetime(data.get(name + "WindowStartedAt"))
    count = int(data.get(name + "Count") or 0)
    if started_at is None or now - started_at >= timedelta(seconds=OTP_RATE_WINDOW_SECONDS):
        return now, 0
    return started_at, count


def _consume_request_quota(database, secret, ip_key, phone_key, run_transaction):
    subjects = [
        ("ip", ip_key, OTP_REQUESTS_PER_IP_PER_HOUR),
        ("global", "all", OTP_GLOBAL_REQUESTS_PER_HOUR),
    ]
    if phone_key:
        subjects.append(("phone", phone_key, OTP_REQUESTS_PER_PHONE_PER_HOUR))
    references = [
        (scope, reference, limit)
        for scope, value, limit in subjects
        for reference in [_rate_reference(database, secret, scope, value)]
    ]
    now = _utcnow()

    def consume(transaction):
        data_by_scope = {
            scope: _get_snapshot_data(reference, transaction) or {}
            for scope, reference, _ in references
        }
        window_states = {
            scope: _window_state(data_by_scope[scope], "request", now)
            for scope, _, _ in references
        }
        if any(
            window_states[scope][1] >= limit
            for scope, _, limit in references
        ):
            return False

        for scope, reference, _ in references:
            window_started_at, count = window_states[scope]
            transaction.set(
                reference,
                {
                    "requestWindowStartedAt": window_started_at,
                    "requestCount": count + 1,
                    "expiresAt": now + timedelta(seconds=OTP_DOCUMENT_RETENTION_SECONDS),
                },
                merge=True,
            )
        return True

    return run_transaction(database, consume)


def _reserve_dispatch(
    database,
    secret,
    session_id,
    ip_key,
    phone_key,
    uid,
    code,
    run_transaction,
):
    phone_reference = _rate_reference(database, secret, "phone", phone_key)
    ip_reference = _rate_reference(database, secret, "ip", ip_key)
    global_reference = _rate_reference(database, secret, "global", "all")
    session_reference = database.collection(OTP_SESSION_COLLECTION).document(session_id)
    references = (
        ("phone", phone_reference, OTP_SENDS_PER_PHONE_PER_HOUR),
        ("ip", ip_reference, OTP_SENDS_PER_IP_PER_HOUR),
        ("global", global_reference, OTP_GLOBAL_SENDS_PER_HOUR),
    )
    now = _utcnow()
    pending_session = {
        "sessionId": session_id,
        "phoneKey": phone_key,
        "uid": uid,
        "codeHmac": _otp_digest(secret, session_id, phone_key, code),
        "createdAt": now,
        "expiresAt": now + timedelta(seconds=OTP_SESSION_TTL_SECONDS),
        "resendAfterAt": now + timedelta(seconds=OTP_RESEND_COOLDOWN_SECONDS),
        "attemptCount": 0,
        "status": "pending",
        "purpose": "login",
    }

    def reserve(transaction):
        data_by_scope = {
            scope: _get_snapshot_data(reference, transaction) or {}
            for scope, reference, _ in references
        }
        phone_data = data_by_scope["phone"]
        last_attempt = _to_utc_datetime(phone_data.get("lastSendAttemptAt"))
        if last_attempt and now - last_attempt < timedelta(
            seconds=OTP_RESEND_COOLDOWN_SECONDS
        ):
            return False

        lock_expires_at = _to_utc_datetime(phone_data.get("dispatchLockExpiresAt"))
        if lock_expires_at and lock_expires_at > now:
            return False

        window_states = {
            scope: _window_state(data_by_scope[scope], "send", now)
            for scope, _, _ in references
        }
        if any(
            window_states[scope][1] >= limit
            for scope, _, limit in references
        ):
            return False

        for scope, reference, _ in references:
            window_started_at, count = window_states[scope]
            update = {
                "sendWindowStartedAt": window_started_at,
                "sendCount": count + 1,
                "expiresAt": now + timedelta(seconds=OTP_DOCUMENT_RETENTION_SECONDS),
            }
            if scope == "phone":
                update.update(
                    {
                        "lastSendAttemptAt": now,
                        "dispatchLockId": session_id,
                        "dispatchLockExpiresAt": now + timedelta(
                            seconds=OTP_DISPATCH_LEASE_SECONDS
                        ),
                    }
                )
            transaction.set(reference, update, merge=True)
        transaction.set(session_reference, pending_session)
        return True

    return run_transaction(database, reserve)


def _finish_dispatch(
    database,
    secret,
    session_id,
    phone_key,
    delivery_state,
    run_transaction,
):
    session_reference = database.collection(OTP_SESSION_COLLECTION).document(session_id)
    phone_reference = _rate_reference(database, secret, "phone", phone_key)
    active_reference = database.collection(
        OTP_ACTIVE_SESSION_COLLECTION
    ).document(phone_key)
    now = _utcnow()

    def finish(transaction):
        session_data = _get_snapshot_data(session_reference, transaction)
        phone_data = _get_snapshot_data(phone_reference, transaction) or {}
        active_data = _get_snapshot_data(active_reference, transaction) or {}
        previous_session_id = str(active_data.get("sessionId") or "")
        previous_reference = (
            database.collection(OTP_SESSION_COLLECTION).document(previous_session_id)
            if previous_session_id and previous_session_id != session_id
            else None
        )
        previous_data = (
            _get_snapshot_data(previous_reference, transaction)
            if previous_reference is not None
            else None
        )

        if not session_data or session_data.get("status") != "pending":
            if phone_data.get("dispatchLockId") == session_id:
                transaction.set(
                    phone_reference,
                    {"dispatchLockId": "", "dispatchLockExpiresAt": now},
                    merge=True,
                )
            return False

        if delivery_state == "rejected":
            session_data.update({"status": "failed", "expiresAt": now})
            transaction.set(session_reference, session_data)
            if phone_data.get("dispatchLockId") == session_id:
                transaction.set(
                    phone_reference,
                    {"dispatchLockId": "", "dispatchLockExpiresAt": now},
                    merge=True,
                )
            return False

        if previous_data and previous_data.get("status") == "active":
            previous_expiry = _to_utc_datetime(previous_data.get("expiresAt"))
            previous_data["status"] = (
                "expired" if previous_expiry is None or previous_expiry <= now
                else "invalidated"
            )
            transaction.set(previous_reference, previous_data)

        session_data.update(
            {
                "status": "active",
                "deliveryState": delivery_state,
                "activatedAt": now,
                "expiresAt": now + timedelta(seconds=OTP_SESSION_TTL_SECONDS),
                "resendAfterAt": now + timedelta(
                    seconds=OTP_RESEND_COOLDOWN_SECONDS
                ),
            }
        )
        transaction.set(session_reference, session_data)
        transaction.set(
            active_reference,
            {
                "sessionId": session_id,
                "expiresAt": now + timedelta(seconds=OTP_SESSION_TTL_SECONDS),
            },
        )
        if phone_data.get("dispatchLockId") == session_id:
            transaction.set(
                phone_reference,
                {"dispatchLockId": "", "dispatchLockExpiresAt": now},
                merge=True,
            )
        return True

    return run_transaction(database, finish)


def _send_authentication_template(config, phone_number, code):
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": phone_number.lstrip("+"),
        "type": "template",
        "template": {
            "name": config["template_name"],
            "language": {"code": config["template_language"]},
            "components": [
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": code}],
                },
                {
                    "type": "button",
                    "sub_type": "url",
                    "index": "0",
                    "parameters": [{"type": "text", "text": code}],
                },
            ],
        },
    }
    try:
        response = requests.post(
            "https://graph.facebook.com/"
            + config["graph_api_version"]
            + "/"
            + config["phone_number_id"]
            + "/messages",
            headers={"Authorization": "Bearer " + config["access_token"]},
            json=payload,
            timeout=15,
        )
    except requests.RequestException:
        return "unknown"

    if 400 <= response.status_code < 500:
        current_app.logger.warning(
            "WhatsApp OTP template request was rejected by Meta (HTTP %s).",
            response.status_code,
        )
        return "rejected"

    if 200 <= response.status_code < 300:
        try:
            response_data = response.json()
        except ValueError:
            return "unknown"
        messages = response_data.get("messages") if isinstance(response_data, dict) else None
        if (
            isinstance(messages, list)
            and messages
            and isinstance(messages[0], dict)
            and messages[0].get("id")
        ):
            return "accepted"
    return "unknown"


def _public_issue_response(session_id=None, status=202):
    return (
        jsonify(
            {
                "sessionId": session_id or uuid.uuid4().hex,
                "expiresInSeconds": OTP_SESSION_TTL_SECONDS,
                "resendCooldownSeconds": OTP_RESEND_COOLDOWN_SECONDS,
                "message": (
                    "If this number is linked to an eligible account, "
                    "check WhatsApp for a verification code."
                ),
            }
        ),
        status,
    )


def _public_error(message, status):
    response = jsonify({"error": message})
    if status == 429:
        response.headers["Retry-After"] = str(OTP_RESEND_COOLDOWN_SECONDS)
    return response, status


def _request_body():
    if request.content_length and request.content_length > OTP_MAX_REQUEST_BYTES:
        return None
    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else None


def _client_ip_key(secret, ip_provider):
    raw_ip = str(ip_provider() or "").strip()
    try:
        client_ip = ipaddress.ip_address(raw_ip).compressed
    except ValueError:
        client_ip = "unknown"
    return _hmac_digest(secret, "ip", client_ip)


def _phone_key(secret, phone_number):
    return _hmac_digest(secret, "phone", phone_number)


def _generic_invalid_verify(database, secret, ip_key, run_transaction):
    reference = _rate_reference(database, secret, "ip", ip_key)
    now = _utcnow()

    def record(transaction):
        data = _get_snapshot_data(reference, transaction) or {}
        started_at, count = _window_state(data, "verify", now)
        if count >= OTP_VERIFY_ATTEMPTS_PER_IP_PER_HOUR:
            return False
        transaction.set(
            reference,
            {
                "verifyWindowStartedAt": started_at,
                "verifyCount": count + 1,
                "expiresAt": now + timedelta(seconds=OTP_DOCUMENT_RETENTION_SECONDS),
            },
            merge=True,
        )
        return True

    return run_transaction(database, record)


def _consume_verify_attempt(
    database,
    secret,
    session_id,
    submitted_code,
    ip_key,
    run_transaction,
):
    session_reference = database.collection(OTP_SESSION_COLLECTION).document(session_id)
    session_data = _get_snapshot_data(session_reference)
    if not session_data:
        return (
            "rate_limited"
            if not _generic_invalid_verify(database, secret, ip_key, run_transaction)
            else "invalid"
        ), None, None

    phone_key = str(session_data.get("phoneKey") or "")
    if not phone_key:
        return "invalid", None, None

    ip_reference = _rate_reference(database, secret, "ip", ip_key)
    phone_reference = _rate_reference(database, secret, "phone", phone_key)
    active_reference = database.collection(
        OTP_ACTIVE_SESSION_COLLECTION
    ).document(phone_key)
    now = _utcnow()
    expected_digest = _otp_digest(secret, session_id, phone_key, submitted_code)

    def consume(transaction):
        current_session = _get_snapshot_data(session_reference, transaction)
        ip_data = _get_snapshot_data(ip_reference, transaction) or {}
        phone_data = _get_snapshot_data(phone_reference, transaction) or {}
        active_data = _get_snapshot_data(active_reference, transaction) or {}

        ip_window, ip_count = _window_state(ip_data, "verify", now)
        phone_window, phone_count = _window_state(phone_data, "verify", now)
        if (
            ip_count >= OTP_VERIFY_ATTEMPTS_PER_IP_PER_HOUR
            or phone_count >= OTP_VERIFY_ATTEMPTS_PER_PHONE_PER_HOUR
        ):
            return "rate_limited", None

        rate_update = {
            "verifyWindowStartedAt": ip_window,
            "verifyCount": ip_count + 1,
            "expiresAt": now + timedelta(seconds=OTP_DOCUMENT_RETENTION_SECONDS),
        }
        phone_rate_update = {
            "verifyWindowStartedAt": phone_window,
            "verifyCount": phone_count + 1,
            "expiresAt": now + timedelta(seconds=OTP_DOCUMENT_RETENTION_SECONDS),
        }

        def persist_rate():
            transaction.set(ip_reference, rate_update, merge=True)
            transaction.set(phone_reference, phone_rate_update, merge=True)

        if not current_session or current_session.get("status") != "active":
            persist_rate()
            return "invalid", None

        expires_at = _to_utc_datetime(current_session.get("expiresAt"))
        if expires_at is None or expires_at <= now:
            current_session["status"] = "expired"
            transaction.set(session_reference, current_session)
            persist_rate()
            return "invalid", None

        if active_data.get("sessionId") != session_id:
            persist_rate()
            return "invalid", None

        attempts = int(current_session.get("attemptCount") or 0)
        if attempts >= OTP_MAX_VERIFICATION_ATTEMPTS:
            current_session["status"] = "locked"
            transaction.set(session_reference, current_session)
            persist_rate()
            return "invalid", None

        if not hmac.compare_digest(
            str(current_session.get("codeHmac") or ""),
            expected_digest,
        ):
            attempts += 1
            current_session["attemptCount"] = attempts
            if attempts >= OTP_MAX_VERIFICATION_ATTEMPTS:
                current_session["status"] = "locked"
            transaction.set(session_reference, current_session)
            persist_rate()
            return "invalid", None

        current_session.update({"status": "consumed", "consumedAt": now})
        transaction.set(session_reference, current_session)
        transaction.set(
            active_reference,
            {"sessionId": "", "expiresAt": now},
        )
        persist_rate()
        return "consumed", str(current_session.get("uid") or "")

    result, uid = run_transaction(database, consume)
    return result, uid, phone_key


def _session_phone_is_current(auth, auth_app, uid, phone_key, secret):
    try:
        user_record = auth.get_user(uid, app=auth_app)
    except UserNotFoundError:
        return False
    phone_number = str(getattr(user_record, "phone_number", "") or "")
    if not phone_number:
        return False
    try:
        normalized = normalize_phone_number(phone_number)
    except ValueError:
        return False
    return hmac.compare_digest(_phone_key(secret, normalized), phone_key)


def register_whatsapp_otp_routes(app, dependencies):
    app.extensions["whatsapp_otp_dependencies"] = dependencies

    def request_code():
        return issue_code(app.extensions["whatsapp_otp_dependencies"])

    def resend_code():
        return issue_code(app.extensions["whatsapp_otp_dependencies"])

    def issue_code(dependencies):
        body = _request_body()
        if body is None:
            return _public_error("A valid request is required.", 400)

        try:
            config = _load_otp_config(dependencies)
            ip_key = _client_ip_key(
                config["secret"],
                dependencies["client_ip_provider"],
            )
            database = dependencies["database_provider"]()
            if database is None:
                raise RuntimeError("WhatsApp OTP storage is unavailable.")
            run_transaction = dependencies["transaction_runner"]
            raw_phone = body.get("phoneNumber")
            try:
                phone_number = normalize_phone_number(raw_phone)
            except ValueError:
                if not _consume_request_quota(
                    database,
                    config["secret"],
                    ip_key,
                    "",
                    run_transaction,
                ):
                    return _public_error(
                        "Please wait before trying again.",
                        429,
                    )
                return _public_error(
                    "Enter a valid international phone number.",
                    400,
                )

            phone_key = _phone_key(config["secret"], phone_number)
            if not _consume_request_quota(
                database,
                config["secret"],
                ip_key,
                phone_key,
                run_transaction,
            ):
                return _public_error("Please wait before trying again.", 429)

            auth = dependencies["firebase_auth_provider"]()
            auth_app = dependencies["firebase_app_provider"]()
            if auth is None or auth_app is None:
                raise RuntimeError("Firebase authentication is unavailable.")

            try:
                user_record = auth.get_user_by_phone_number(
                    phone_number,
                    app=auth_app,
                )
            except UserNotFoundError:
                return _public_issue_response()

            uid = str(getattr(user_record, "uid", "") or "")
            associated_phone = str(getattr(user_record, "phone_number", "") or "")
            if (
                not uid
                or associated_phone != phone_number
                or not dependencies["active_member_provider"](uid)
            ):
                return _public_issue_response()

            session_id = uuid.uuid4().hex
            code = generate_otp()
            if not _reserve_dispatch(
                database,
                config["secret"],
                session_id,
                ip_key,
                phone_key,
                uid,
                code,
                run_transaction,
            ):
                return _public_issue_response()

            try:
                delivery_state = _send_authentication_template(
                    config,
                    phone_number,
                    code,
                )
            except requests.RequestException:
                delivery_state = "unknown"

            if delivery_state not in {"accepted", "unknown"}:
                _finish_dispatch(
                    database,
                    config["secret"],
                    session_id,
                    phone_key,
                    "rejected",
                    run_transaction,
                )
                return _public_issue_response()

            if _finish_dispatch(
                database,
                config["secret"],
                session_id,
                phone_key,
                delivery_state,
                run_transaction,
            ):
                return _public_issue_response(session_id)
            return _public_issue_response()
        except OtpConfigurationError:
            current_app.logger.error("WhatsApp OTP configuration is unavailable.")
            return _public_error(
                "Authentication service is temporarily unavailable.",
                503,
            )
        except Exception:
            current_app.logger.exception("WhatsApp OTP request could not be completed.")
            return _public_error(
                "Authentication service is temporarily unavailable.",
                503,
            )

    def verify_code():
        dependencies = app.extensions["whatsapp_otp_dependencies"]
        body = _request_body()
        if body is None:
            return _public_error("A valid request is required.", 400)

        try:
            config = _load_otp_config(dependencies)
            ip_key = _client_ip_key(
                config["secret"],
                dependencies["client_ip_provider"],
            )
            database = dependencies["database_provider"]()
            if database is None:
                raise RuntimeError("WhatsApp OTP storage is unavailable.")
            run_transaction = dependencies["transaction_runner"]

            session_id = str(body.get("sessionId") or "")
            raw_code = body.get("code")
            submitted_code = (
                raw_code if isinstance(raw_code, str) else ""
            )
            if not OTP_SESSION_ID_PATTERN.fullmatch(session_id):
                if not _generic_invalid_verify(
                    database,
                    config["secret"],
                    ip_key,
                    run_transaction,
                ):
                    return _public_error(
                        "Please wait before trying again.",
                        429,
                    )
                return _public_error(
                    "The code could not be verified. Check it or request another.",
                    401,
                )

            result, uid, phone_key = _consume_verify_attempt(
                database,
                config["secret"],
                session_id,
                submitted_code,
                ip_key,
                run_transaction,
            )
            if result == "rate_limited":
                return _public_error("Please wait before trying again.", 429)
            if result != "consumed" or not uid or not phone_key:
                return _public_error(
                    "The code could not be verified. Check it or request another.",
                    401,
                )

            auth = dependencies["firebase_auth_provider"]()
            auth_app = dependencies["firebase_app_provider"]()
            if auth is None or auth_app is None:
                raise RuntimeError("Firebase authentication is unavailable.")
            if not _session_phone_is_current(
                auth,
                auth_app,
                uid,
                phone_key,
                config["secret"],
            ):
                return _public_error(
                    "The code could not be verified. Check it or request another.",
                    401,
                )
            if not dependencies["active_member_provider"](uid):
                return _public_error(
                    "The code could not be verified. Check it or request another.",
                    401,
                )

            custom_token = auth.create_custom_token(uid, app=auth_app)
            if isinstance(custom_token, bytes):
                custom_token = custom_token.decode("utf-8")
            if not isinstance(custom_token, str) or not custom_token:
                raise RuntimeError("Firebase did not create an authentication token.")
            return jsonify({"customToken": custom_token}), 200
        except OtpConfigurationError:
            current_app.logger.error("WhatsApp OTP configuration is unavailable.")
            return _public_error(
                "Authentication service is temporarily unavailable.",
                503,
            )
        except Exception:
            current_app.logger.exception("WhatsApp OTP verification could not be completed.")
            return _public_error(
                "Authentication service is temporarily unavailable.",
                503,
            )

    app.add_url_rule(
        "/api/auth/whatsapp/request",
        endpoint="whatsapp_otp_request",
        view_func=request_code,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/auth/whatsapp/resend",
        endpoint="whatsapp_otp_resend",
        view_func=resend_code,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/auth/whatsapp/verify",
        endpoint="whatsapp_otp_verify",
        view_func=verify_code,
        methods=["POST"],
    )
