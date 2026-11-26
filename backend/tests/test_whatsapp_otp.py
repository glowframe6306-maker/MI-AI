from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from importlib import import_module
from threading import RLock
from types import SimpleNamespace

import pytest
from firebase_admin.auth import UserNotFoundError


PHONE_NUMBER = "+94771234567"
OTHER_PHONE_NUMBER = "+94771234568"
TEST_AUTH_APP = object()


class _Snapshot:
    def __init__(self, value):
        self.exists = value is not None
        self._value = deepcopy(value)

    def to_dict(self):
        return deepcopy(self._value or {})


class _DocumentReference:
    def __init__(self, database, path):
        self.database = database
        self.path = path

    def collection(self, name):
        return _CollectionReference(self.database, self.path + (name,))

    def get(self, transaction=None):
        if transaction is not None:
            return transaction.get(self)
        with self.database.lock:
            return _Snapshot(self.database.values.get(self.path))


class _CollectionReference:
    def __init__(self, database, path):
        self.database = database
        self.path = path

    def document(self, document_id):
        return _DocumentReference(self.database, self.path + (str(document_id),))


class _Transaction:
    def __init__(self, database):
        self.database = database
        self.writes = []

    def get(self, reference):
        return _Snapshot(self.database.values.get(reference.path))

    def set(self, reference, value, merge=False):
        self.writes.append((reference.path, deepcopy(value), merge))


class _FakeFirestore:
    def __init__(self):
        self.values = {}
        self.lock = RLock()

    def collection(self, name):
        return _CollectionReference(self, (name,))

    def run_transaction(self, operation):
        with self.lock:
            transaction = _Transaction(self)
            result = operation(transaction)
            for path, value, merge in transaction.writes:
                if merge:
                    self.values[path] = {
                        **self.values.get(path, {}),
                        **value,
                    }
                else:
                    self.values[path] = value
            return result


class _FakeAuth:
    UserNotFoundError = UserNotFoundError

    def __init__(self):
        self.users_by_phone = {
            PHONE_NUMBER: SimpleNamespace(
                uid="existing-firebase-uid",
                phone_number=PHONE_NUMBER,
            )
        }
        self.users_by_uid = {
            "existing-firebase-uid": self.users_by_phone[PHONE_NUMBER]
        }
        self.created_tokens = []

    def get_user_by_phone_number(self, phone_number, *, app):
        assert app is TEST_AUTH_APP
        try:
            return self.users_by_phone[phone_number]
        except KeyError as exc:
            raise UserNotFoundError("No matching phone.") from exc

    def get_user(self, uid, *, app):
        assert app is TEST_AUTH_APP
        try:
            return self.users_by_uid[uid]
        except KeyError as exc:
            raise UserNotFoundError("No matching user.") from exc

    def create_custom_token(self, uid, *, app):
        assert app is TEST_AUTH_APP
        self.created_tokens.append(uid)
        return b"mock-custom-token"


class _MetaResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {"messages": [{"id": "wamid.mock"}]}

    def json(self):
        return self._payload


@pytest.fixture
def whatsapp_otp(monkeypatch):
    module = import_module("backend.whatsapp_otp")
    app_module = import_module("backend.app")
    database = _FakeFirestore()
    auth = _FakeAuth()
    active_members = {"existing-firebase-uid"}
    request_ip = ["203.0.113.10"]
    meta_calls = []
    meta_response = [_MetaResponse()]

    def fake_meta_post(url, *, headers, json, timeout):
        meta_calls.append(
            {
                "url": url,
                "headers": headers,
                "payload": deepcopy(json),
                "timeout": timeout,
            }
        )
        return meta_response[0]

    dependencies = {
        "database_provider": lambda: database,
        "transaction_runner": lambda db, operation: db.run_transaction(operation),
        "firebase_auth_provider": lambda: auth,
        "firebase_app_provider": lambda: TEST_AUTH_APP,
        "graph_api_version_provider": lambda: "v27.0",
        "active_member_provider": lambda uid: uid in active_members,
        "client_ip_provider": lambda: request_ip[0],
    }
    monkeypatch.setitem(
        app_module.app.extensions,
        "whatsapp_otp_dependencies",
        dependencies,
    )
    monkeypatch.setenv("WHATSAPP_OTP_HMAC_SECRET", "test-only-hmac-key-" + ("x" * 32))
    monkeypatch.setenv("WHATSAPP_OTP_PHONE_NUMBER_ID", "15550000123")
    monkeypatch.setenv("WHATSAPP_OTP_ACCESS_TOKEN", "test-only-access-token")
    monkeypatch.setenv("WHATSAPP_OTP_TEMPLATE_NAME", "cortex_login_code")
    monkeypatch.setenv("WHATSAPP_OTP_TEMPLATE_LANGUAGE", "en_US")
    monkeypatch.setattr(module.requests, "post", fake_meta_post)

    return SimpleNamespace(
        module=module,
        app=app_module.app,
        database=database,
        auth=auth,
        active_members=active_members,
        request_ip=request_ip,
        meta_calls=meta_calls,
        meta_response=meta_response,
    )


def _client(whatsapp_otp):
    return whatsapp_otp.app.test_client()


def _request_code(whatsapp_otp, phone_number=PHONE_NUMBER, extra=None):
    payload = {"phoneNumber": phone_number}
    if extra:
        payload.update(extra)
    return _client(whatsapp_otp).post(
        "/api/auth/whatsapp/request",
        json=payload,
    )


def _sent_code(whatsapp_otp, call_index=0):
    components = whatsapp_otp.meta_calls[call_index]["payload"]["template"]["components"]
    return components[0]["parameters"][0]["text"]


def _active_session(whatsapp_otp, session_id):
    return whatsapp_otp.database.values[
        ("whatsappOtpSessions", session_id)
    ]


def test_phone_number_is_normalized_and_validated_with_metadata():
    module = import_module("backend.whatsapp_otp")

    assert module.normalize_phone_number("+94 77 123 4567") == PHONE_NUMBER
    with pytest.raises(ValueError):
        module.normalize_phone_number("0771234567")
    with pytest.raises(ValueError):
        module.normalize_phone_number("+999123")


def test_secure_otp_generator_preserves_leading_zeroes(monkeypatch):
    module = import_module("backend.whatsapp_otp")
    upper_bounds = []

    def fixed_secure_random(bound):
        upper_bounds.append(bound)
        return 42

    monkeypatch.setattr(module.secrets, "randbelow", fixed_secure_random)

    assert module.generate_otp() == "00000042"
    assert upper_bounds == [100_000_000]


def test_request_uses_approved_auth_template_and_ignores_client_uid(whatsapp_otp):
    response = _request_code(
        whatsapp_otp,
        extra={"uid": "attacker-chosen-uid"},
    )

    assert response.status_code == 202
    payload = response.get_json()
    session_id = payload["sessionId"]
    session = _active_session(whatsapp_otp, session_id)
    template = whatsapp_otp.meta_calls[0]["payload"]["template"]
    components = template["components"]

    assert len(_sent_code(whatsapp_otp)) == 8
    assert _sent_code(whatsapp_otp).isdigit()
    assert components[1]["parameters"][0]["text"] == _sent_code(whatsapp_otp)
    assert components[1]["sub_type"] == "url"
    assert session["uid"] == "existing-firebase-uid"
    assert "attacker-chosen-uid" not in repr(session)
    assert "phoneNumber" not in session
    assert "role" not in session
    assert session["status"] == "active"
    assert session["attemptCount"] == 0
    assert session["purpose"] == "login"
    assert _sent_code(whatsapp_otp) not in repr(session)
    assert whatsapp_otp.meta_calls[0]["timeout"] == 15


def test_unknown_account_has_the_same_generic_request_response(whatsapp_otp):
    eligible = _request_code(whatsapp_otp)
    unknown = _request_code(whatsapp_otp, OTHER_PHONE_NUMBER)

    assert eligible.status_code == unknown.status_code == 202
    eligible_payload = eligible.get_json()
    unknown_payload = unknown.get_json()
    assert set(eligible_payload) == set(unknown_payload)
    assert eligible_payload["message"] == unknown_payload["message"]
    assert eligible_payload["expiresInSeconds"] == unknown_payload["expiresInSeconds"]
    assert eligible_payload["resendCooldownSeconds"] == unknown_payload["resendCooldownSeconds"]
    assert eligible_payload["sessionId"] != unknown_payload["sessionId"]
    assert len(whatsapp_otp.meta_calls) == 1
    assert ("whatsappOtpSessions", unknown_payload["sessionId"]) not in whatsapp_otp.database.values


def test_unlinked_uid_cannot_receive_code_or_gain_owner_membership(whatsapp_otp):
    whatsapp_otp.active_members.clear()

    response = _request_code(whatsapp_otp)

    assert response.status_code == 202
    assert not whatsapp_otp.meta_calls
    assert not any(
        collection == "whatsappOtpSessions"
        for collection, *_ in whatsapp_otp.database.values
    )
    assert not whatsapp_otp.auth.created_tokens


def test_verify_creates_token_only_for_existing_uid_and_consumes_session(whatsapp_otp):
    request_response = _request_code(whatsapp_otp)
    session_id = request_response.get_json()["sessionId"]
    code = _sent_code(whatsapp_otp)

    response = _client(whatsapp_otp).post(
        "/api/auth/whatsapp/verify",
        json={"sessionId": session_id, "code": code, "uid": "attacker-uid"},
    )

    assert response.status_code == 200
    assert response.get_json() == {"customToken": "mock-custom-token"}
    assert whatsapp_otp.auth.created_tokens == ["existing-firebase-uid"]
    assert _active_session(whatsapp_otp, session_id)["status"] == "consumed"

    repeated = _client(whatsapp_otp).post(
        "/api/auth/whatsapp/verify",
        json={"sessionId": session_id, "code": code},
    )
    assert repeated.status_code == 401
    assert whatsapp_otp.auth.created_tokens == ["existing-firebase-uid"]


def test_fifth_incorrect_attempt_locks_session(whatsapp_otp):
    session_id = _request_code(whatsapp_otp).get_json()["sessionId"]
    valid_code = _sent_code(whatsapp_otp)
    wrong_code = "00000000" if valid_code != "00000000" else "00000001"

    for _ in range(5):
        response = _client(whatsapp_otp).post(
            "/api/auth/whatsapp/verify",
            json={"sessionId": session_id, "code": wrong_code},
        )
        assert response.status_code == 401

    assert _active_session(whatsapp_otp, session_id)["attemptCount"] == 5
    assert _active_session(whatsapp_otp, session_id)["status"] == "locked"
    assert not whatsapp_otp.auth.created_tokens

    final_attempt = _client(whatsapp_otp).post(
        "/api/auth/whatsapp/verify",
        json={"sessionId": session_id, "code": valid_code},
    )
    assert final_attempt.status_code == 401
    assert not whatsapp_otp.auth.created_tokens


def test_expired_code_is_rejected(monkeypatch, whatsapp_otp):
    now = [datetime(2026, 11, 26, tzinfo=timezone.utc)]
    monkeypatch.setattr(whatsapp_otp.module, "_utcnow", lambda: now[0])
    session_id = _request_code(whatsapp_otp).get_json()["sessionId"]
    code = _sent_code(whatsapp_otp)
    now[0] += timedelta(seconds=301)

    response = _client(whatsapp_otp).post(
        "/api/auth/whatsapp/verify",
        json={"sessionId": session_id, "code": code},
    )

    assert response.status_code == 401
    assert _active_session(whatsapp_otp, session_id)["status"] == "expired"
    assert not whatsapp_otp.auth.created_tokens


def test_resend_cooldown_and_successful_replacement(monkeypatch, whatsapp_otp):
    now = [datetime(2026, 11, 26, tzinfo=timezone.utc)]
    monkeypatch.setattr(whatsapp_otp.module, "_utcnow", lambda: now[0])
    first_response = _request_code(whatsapp_otp)
    first_session_id = first_response.get_json()["sessionId"]
    first_code = _sent_code(whatsapp_otp)

    blocked = _client(whatsapp_otp).post(
        "/api/auth/whatsapp/resend",
        json={"phoneNumber": PHONE_NUMBER},
    )
    assert blocked.status_code == 202
    assert len(whatsapp_otp.meta_calls) == 1

    now[0] += timedelta(seconds=61)
    second_response = _client(whatsapp_otp).post(
        "/api/auth/whatsapp/resend",
        json={"phoneNumber": PHONE_NUMBER},
    )
    second_session_id = second_response.get_json()["sessionId"]
    second_code = _sent_code(whatsapp_otp, 1)

    assert second_response.status_code == 202
    assert second_session_id != first_session_id
    assert _active_session(whatsapp_otp, first_session_id)["status"] == "invalidated"

    old_code_response = _client(whatsapp_otp).post(
        "/api/auth/whatsapp/verify",
        json={"sessionId": first_session_id, "code": first_code},
    )
    assert old_code_response.status_code == 401

    new_code_response = _client(whatsapp_otp).post(
        "/api/auth/whatsapp/verify",
        json={"sessionId": second_session_id, "code": second_code},
    )
    assert new_code_response.status_code == 200
    assert whatsapp_otp.auth.created_tokens == ["existing-firebase-uid"]


def test_concurrent_verification_consumes_session_once(whatsapp_otp):
    session_id = _request_code(whatsapp_otp).get_json()["sessionId"]
    code = _sent_code(whatsapp_otp)

    def verify():
        return _client(whatsapp_otp).post(
            "/api/auth/whatsapp/verify",
            json={"sessionId": session_id, "code": code},
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(executor.map(lambda _: verify(), range(2)))

    assert sorted(statuses) == [200, 401]
    assert whatsapp_otp.auth.created_tokens == ["existing-firebase-uid"]


def test_meta_rejection_does_not_activate_or_claim_delivery(whatsapp_otp):
    whatsapp_otp.meta_response[0] = _MetaResponse(
        status_code=400,
        payload={"error": {"message": "private provider detail"}},
    )

    response = _request_code(whatsapp_otp)
    session_id = response.get_json()["sessionId"]

    assert response.status_code == 202
    assert "sent" not in response.get_json()["message"].lower()
    assert ("whatsappOtpSessions", session_id) not in whatsapp_otp.database.values
    assert not whatsapp_otp.auth.created_tokens


def test_invalid_phone_is_rejected_without_meta_request(whatsapp_otp):
    response = _request_code(whatsapp_otp, "0771234567")

    assert response.status_code == 400
    assert not whatsapp_otp.meta_calls


