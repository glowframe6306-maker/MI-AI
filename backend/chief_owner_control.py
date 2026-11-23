import os
import re
import uuid
from datetime import datetime, timezone
from functools import wraps

from flask import Blueprint, current_app, jsonify, request

try:
    from backend.chief_owner_identity import (
        CHIEF_OWNER_EMAIL,
        CHIEF_OWNER_UID,
        CHIEF_OWNER_UID_CONFIGURED,
        CHIEF_OWNER_UID_CONFIG_VALID,
        is_chief_owner_candidate,
        is_chief_owner_identity,
        read_persisted_chief_owner_uid,
    )
except ImportError:
    from chief_owner_identity import (
        CHIEF_OWNER_EMAIL,
        CHIEF_OWNER_UID,
        CHIEF_OWNER_UID_CONFIGURED,
        CHIEF_OWNER_UID_CONFIG_VALID,
        is_chief_owner_candidate,
        is_chief_owner_identity,
        read_persisted_chief_owner_uid,
    )

try:
    from firebase_admin import auth as firebase_auth
    from firebase_admin import firestore
except Exception:
    firebase_auth = None
    firestore = None


chief_owner_control = Blueprint(
    "chief_owner_control",
    __name__,
)

_WHATSAPP_FIRESTORE_INT64_MAX = (1 << 63) - 1


def _is_whatsapp_coexistence_revision(value):
    return (
        type(value) is int
        and 0 <= value <= _WHATSAPP_FIRESTORE_INT64_MAX
    )


def _whatsapp_coexistence_revision(data):
    revision = (data or {}).get("coexistenceEventVersion", 0)
    if not _is_whatsapp_coexistence_revision(revision):
        raise ValueError("WhatsApp coexistence revision is invalid")
    return revision


def utc_now():
    return datetime.now(timezone.utc)


def database():
    if os.getenv("MI_AI_TEST_MODE") == "1":
        raise RuntimeError(
            "Firestore access is disabled in test mode; inject a fake database."
        )

    if firestore is None:
        raise RuntimeError(
            "Firebase Admin Firestore is unavailable."
        )

    firebase_app = current_app.extensions.get("firebase_admin_app")
    if firebase_app is None:
        raise RuntimeError("Firebase Admin app is not configured.")
    return firestore.client(app=firebase_app)


def persisted_chief_owner_uid():
    return read_persisted_chief_owner_uid(
        database(),
        configured_email=CHIEF_OWNER_EMAIL,
    )


def normalize_email(value):
    return str(value or "").strip().lower()


def get_bearer_token():
    header = request.headers.get(
        "Authorization",
        "",
    )

    if not header.lower().startswith("bearer "):
        return ""

    return header.split(" ", 1)[1].strip()


def verify_identity():
    if firebase_auth is None:
        raise PermissionError(
            "Firebase Admin authentication is unavailable."
        )

    token = get_bearer_token()

    if not token:
        raise PermissionError(
            "Authentication token is missing."
        )

    decoded = firebase_auth.verify_id_token(
        token,
        check_revoked=True,
    )

    uid = str(
        decoded.get("uid")
        or decoded.get("sub")
        or ""
    ).strip()

    email = normalize_email(
        decoded.get("email")
    )

    if not uid or not email:
        raise PermissionError(
            "The authentication token is incomplete."
        )

    return {
        "uid": uid,
        "email": email,
        "email_verified": bool(decoded.get("email_verified", False)),
        "token": decoded,
    }


def is_chief_owner(identity, persisted_uid=None):
    uid_configured = CHIEF_OWNER_UID_CONFIGURED or bool(CHIEF_OWNER_UID)
    uid_config_valid = CHIEF_OWNER_UID_CONFIG_VALID and (
        not CHIEF_OWNER_UID_CONFIGURED or bool(CHIEF_OWNER_UID)
    )
    return is_chief_owner_identity(
        identity.get("email"),
        identity.get("uid"),
        persisted_uid=persisted_uid,
        email_verified=identity.get("email_verified", False),
        configured_email=CHIEF_OWNER_EMAIL,
        configured_uid=CHIEF_OWNER_UID,
        uid_configured=uid_configured,
        uid_config_valid=uid_config_valid,
    )


def require_chief_owner(function):
    @wraps(function)
    def protected(*args, **kwargs):
        try:
            identity = verify_identity()

            uid_configured = CHIEF_OWNER_UID_CONFIGURED or bool(
                CHIEF_OWNER_UID
            )
            uid_config_valid = CHIEF_OWNER_UID_CONFIG_VALID and (
                not CHIEF_OWNER_UID_CONFIGURED or bool(CHIEF_OWNER_UID)
            )
            if not is_chief_owner_candidate(
                identity["email"],
                identity["uid"],
                identity["email_verified"],
                configured_email=CHIEF_OWNER_EMAIL,
                configured_uid=CHIEF_OWNER_UID,
                uid_configured=uid_configured,
                uid_config_valid=uid_config_valid,
            ):
                return jsonify({
                    "ok": False,
                    "message":
                        "Chief Owner access is required.",
                }), 403

            try:
                persisted_uid = persisted_chief_owner_uid()
            except Exception:
                current_app.logger.exception(
                    "Chief Owner identity binding could not be verified."
                )
                return jsonify({
                    "ok": False,
                    "message":
                        "Owner identity validation is unavailable.",
                }), 503

            if not is_chief_owner(identity, persisted_uid):
                return jsonify({
                    "ok": False,
                    "message":
                        "Chief Owner access is required.",
                }), 403

            request.chief_owner_identity = identity
            request.chief_owner_request_id = (
                request.headers.get("X-Request-Id")
                or str(uuid.uuid4())
            )

            return function(*args, **kwargs)

        except PermissionError as error:
            return jsonify({
                "ok": False,
                "message": str(error),
            }), 401

        except Exception:
            current_app.logger.exception(
                "Chief Owner authorization failed."
            )

            return jsonify({
                "ok": False,
                "message":
                    "Authorization validation failed.",
            }), 500

    return protected


def create_security_alert(alert_type, identity):
    try:
        alert_id = str(uuid.uuid4())

        database().collection(
            "securityAlerts"
        ).document(alert_id).set({
            "alertId": alert_id,
            "type": alert_type,
            "actorUid": identity.get("uid", ""),
            "actorEmail": identity.get("email", ""),
            "path": request.path,
            "ipAddress": request.headers.get(
                "X-Forwarded-For",
                request.remote_addr or "",
            ),
            "device": request.headers.get(
                "User-Agent",
                "",
            ),
            "timestamp": utc_now(),
        })

    except Exception:
        current_app.logger.exception(
            "Security alert creation failed."
        )


def create_audit(
    action,
    target_type,
    target_id,
    reason,
    previous=None,
    new=None,
    success=True,
    error_message="",
):
    identity = getattr(
        request,
        "chief_owner_identity",
        {},
    )

    audit_id = str(uuid.uuid4())

    database().collection(
        "auditLogs"
    ).document(audit_id).set({
        "auditId": audit_id,
        "actorUid": identity.get("uid", ""),
        "actorEmail": identity.get("email", ""),
        "actorRole": "chief_owner",
        "action": action,
        "targetType": target_type,
        "targetId": target_id,
        "previousValue": previous or {},
        "newValue": new or {},
        "reason": reason,
        "timestamp": utc_now(),
        "ipAddress": request.headers.get(
            "X-Forwarded-For",
            request.remote_addr or "",
        ),
        "deviceInformation": request.headers.get(
            "User-Agent",
            "",
        ),
        "sessionId": request.headers.get(
            "X-Session-Id",
            "",
        ),
        "requestId": getattr(
            request,
            "chief_owner_request_id",
            "",
        ),
        "success": bool(success),
        "errorMessage": error_message,
    })


def protected_target(email):
    if normalize_email(email) == CHIEF_OWNER_EMAIL:
        raise PermissionError(
            "The permanent Chief Owner account is protected."
        )


def find_user(email):
    protected_target(email)

    try:
        return firebase_auth.get_user_by_email(
            email
        )

    except firebase_auth.UserNotFoundError:
        return None


def safe_user(record):
    metadata = record.user_metadata

    return {
        "uid": record.uid,
        "email": record.email or "",
        "displayName": record.display_name or "",
        "disabled": bool(record.disabled),
        "emailVerified":
            bool(record.email_verified),
        "customClaims":
            dict(record.custom_claims or {}),
        "createdAt":
            metadata.creation_timestamp
            if metadata else None,
        "lastLogin":
            metadata.last_sign_in_timestamp
            if metadata else None,
        "isChiefOwner":
            normalize_email(record.email)
            == CHIEF_OWNER_EMAIL,
    }


@chief_owner_control.get(
    "/api/chief-owner/options"
)
@require_chief_owner
def chief_owner_options():
    pages = [
        "Dashboard",
        "Users",
        "User Profiles",
        "Chats",
        "Conversation Viewer",
        "Messages",
        "Staff Management",
        "Roles",
        "Permission Center",
        "Access Requests",
        "Reports",
        "Moderation",
        "Customer Support",
        "Analytics",
        "System Status",
        "AI Management",
        "Model Settings",
        "API Management",
        "Security Center",
        "Login Sessions",
        "Devices",
        "Audit Logs",
        "Activity History",
        "Notifications",
        "Announcements",
        "Content Management",
        "Settings",
        "Admin Profile",
        "Backup and Restore",
        "Deleted Items",
        "Blocked Users",
        "Suspended Users",
        "Error Logs",
        "Feature Controls",
        "Maintenance Mode",
        "Permission Templates",
        "Ownership Settings",
    ]

    return jsonify({
        "ok": True,
        "pages": pages,
    })


@chief_owner_control.get(
    "/api/chief-owner/users"
)
@require_chief_owner
def chief_owner_users():
    email = normalize_email(
        request.args.get("email")
    )

    if email:
        if email == CHIEF_OWNER_EMAIL:
            record = firebase_auth.get_user_by_email(
                email
            )

            return jsonify({
                "ok": True,
                "users": [safe_user(record)],
            })

        record = find_user(email)

        return jsonify({
            "ok": True,
            "users":
                [safe_user(record)]
                if record else [],
        })

    result = firebase_auth.list_users(
        max_results=100
    )

    return jsonify({
        "ok": True,
        "users": [
            safe_user(record)
            for record in result.users
        ],
    })


@chief_owner_control.post(
    "/api/chief-owner/users/action"
)
@require_chief_owner
def chief_owner_user_action():
    body = request.get_json(
        silent=True
    ) or {}

    email = normalize_email(
        body.get("email")
    )

    action = str(
        body.get("action") or ""
    ).strip().lower()

    reason = str(
        body.get("reason") or ""
    ).strip()

    if not email or "@" not in email:
        return jsonify({
            "ok": False,
            "message":
                "A valid user email is required.",
        }), 400

    if not reason:
        return jsonify({
            "ok": False,
            "message":
                "A written reason is required.",
        }), 400

    supported = {
        "block",
        "unblock",
        "suspend",
        "restore",
        "disable",
        "enable",
        "force_logout",
        "delete",
    }

    if action not in supported:
        return jsonify({
            "ok": False,
            "message":
                "Unsupported user action.",
        }), 400

    protected_target(email)

    record = find_user(email)

    if record is None:
        return jsonify({
            "ok": False,
            "message":
                "User account was not found.",
        }), 404

    uid = record.uid

    previous = {
        "disabled": bool(record.disabled),
        "claims":
            dict(record.custom_claims or {}),
    }

    try:
        claims = dict(
            record.custom_claims or {}
        )

        if action in {
            "block",
            "suspend",
            "disable",
        }:
            status = {
                "block": "blocked",
                "suspend": "suspended",
                "disable": "disabled",
            }[action]

            claims["accountStatus"] = status
            claims["blocked"] = (
                action == "block"
            )
            claims["suspended"] = (
                action == "suspend"
            )

            firebase_auth.set_custom_user_claims(
                uid,
                claims,
            )

            firebase_auth.update_user(
                uid,
                disabled=True,
            )

            firebase_auth.revoke_refresh_tokens(
                uid
            )

            database().collection(
                "userRestrictions"
            ).document(uid).set({
                "uid": uid,
                "email": email,
                "status": status,
                "reason": reason,
                "active": True,
                "createdAt": utc_now(),
                "createdBy":
                    request
                    .chief_owner_identity["uid"],
                "createdByEmail":
                    request
                    .chief_owner_identity["email"],
            }, merge=True)

            database().collection(
                "users"
            ).document(uid).set({
                "uid": uid,
                "email": email,
                "accountStatus": status,
                "disabled": True,
                "updatedAt": utc_now(),
            }, merge=True)

        elif action in {
            "unblock",
            "restore",
            "enable",
        }:
            claims.pop("blocked", None)
            claims.pop("suspended", None)
            claims["accountStatus"] = "active"

            firebase_auth.set_custom_user_claims(
                uid,
                claims,
            )

            firebase_auth.update_user(
                uid,
                disabled=False,
            )

            firebase_auth.revoke_refresh_tokens(
                uid
            )

            database().collection(
                "userRestrictions"
            ).document(uid).set({
                "active": False,
                "restoredAt": utc_now(),
                "restoredBy":
                    request
                    .chief_owner_identity["uid"],
                "restoreReason": reason,
            }, merge=True)

            database().collection(
                "users"
            ).document(uid).set({
                "accountStatus": "active",
                "disabled": False,
                "updatedAt": utc_now(),
            }, merge=True)

        elif action == "force_logout":
            firebase_auth.revoke_refresh_tokens(
                uid
            )

        elif action == "delete":
            database().collection(
                "deletedItems"
            ).document(uid).set({
                "uid": uid,
                "email": email,
                "displayName":
                    record.display_name or "",
                "reason": reason,
                "deletedAt": utc_now(),
                "deletedBy":
                    request
                    .chief_owner_identity["uid"],
            })

            firebase_auth.revoke_refresh_tokens(
                uid
            )

            firebase_auth.delete_user(uid)

            database().collection(
                "users"
            ).document(uid).set({
                "accountStatus": "deleted",
                "deleted": True,
                "deletedAt": utc_now(),
            }, merge=True)

        new_value = {
            "action": action,
            "email": email,
        }

        create_audit(
            action=action,
            target_type="user",
            target_id=uid,
            reason=reason,
            previous=previous,
            new=new_value,
        )

        return jsonify({
            "ok": True,
            "message":
                action.replace(
                    "_",
                    " ",
                ).title()
                + " completed for "
                + email,
            "uid": uid,
        })

    except Exception as error:
        create_audit(
            action=action,
            target_type="user",
            target_id=uid,
            reason=reason,
            previous=previous,
            success=False,
            error_message=str(error),
        )

        current_app.logger.exception(
            "Chief Owner user action failed."
        )

        return jsonify({
            "ok": False,
            "message":
                "The user action failed.",
        }), 500


def find_chat_documents(
    collection_name,
    uid,
    email,
):
    collection = database().collection(
        collection_name
    )

    documents = {}

    searches = [
        ("uid", uid),
        ("userId", uid),
        ("ownerUid", uid),
        ("email", email),
        ("userEmail", email),
        ("ownerEmail", email),
    ]

    for field, value in searches:
        try:
            stream = (
                collection
                .where(field, "==", value)
                .limit(100)
                .stream()
            )

            for snapshot in stream:
                documents[
                    snapshot.reference.path
                ] = snapshot

        except Exception:
            continue

    return list(documents.values())


@chief_owner_control.get(
    "/api/chief-owner/chats"
)
@require_chief_owner
def chief_owner_chats():
    email = normalize_email(
        request.args.get("email")
    )

    reason = str(
        request.args.get("reason") or ""
    ).strip()

    if not email or not reason:
        return jsonify({
            "ok": False,
            "message":
                "Email and access reason are required.",
        }), 400

    record = find_user(email)

    if record is None:
        return jsonify({
            "ok": False,
            "message":
                "User account was not found.",
        }), 404

    results = []

    for collection_name in [
        "conversations",
        "chats",
    ]:
        snapshots = find_chat_documents(
            collection_name,
            record.uid,
            email,
        )

        for snapshot in snapshots:
            data = snapshot.to_dict() or {}

            results.append({
                "id": snapshot.id,
                "collection": collection_name,
                "title":
                    data.get("title")
                    or data.get("name")
                    or "Untitled Chat",
                "createdAt":
                    str(data.get("createdAt") or ""),
                "updatedAt":
                    str(data.get("updatedAt") or ""),
                "messageCount":
                    data.get("messageCount", 0),
                "data": data,
            })

    create_audit(
        action="chats.view_all",
        target_type="user",
        target_id=record.uid,
        reason=reason,
        new={
            "email": email,
            "chatCount": len(results),
        },
    )

    return jsonify({
        "ok": True,
        "chats": results,
    })


@chief_owner_control.post(
    "/api/chief-owner/chats/delete"
)
@require_chief_owner
def chief_owner_delete_chat():
    body = request.get_json(
        silent=True
    ) or {}

    email = normalize_email(
        body.get("email")
    )

    collection_name = str(
        body.get("collection") or ""
    ).strip()

    chat_id = str(
        body.get("chatId") or ""
    ).strip()

    reason = str(
        body.get("reason") or ""
    ).strip()

    if (
        not email
        or not chat_id
        or not reason
    ):
        return jsonify({
            "ok": False,
            "message":
                "Email, chat ID and reason are required.",
        }), 400

    if collection_name not in {
        "chats",
        "conversations",
    }:
        return jsonify({
            "ok": False,
            "message":
                "Invalid chat collection.",
        }), 400

    record = find_user(email)

    if record is None:
        return jsonify({
            "ok": False,
            "message":
                "User account was not found.",
        }), 404

    reference = (
        database()
        .collection(collection_name)
        .document(chat_id)
    )

    snapshot = reference.get()

    if not snapshot.exists:
        return jsonify({
            "ok": False,
            "message":
                "Chat was not found.",
        }), 404

    old_data = snapshot.to_dict() or {}

    owner_values = {
        str(old_data.get("uid") or ""),
        str(old_data.get("userId") or ""),
        str(old_data.get("ownerUid") or ""),
        normalize_email(
            old_data.get("email")
        ),
        normalize_email(
            old_data.get("userEmail")
        ),
        normalize_email(
            old_data.get("ownerEmail")
        ),
    }

    if (
        record.uid not in owner_values
        and email not in owner_values
    ):
        return jsonify({
            "ok": False,
            "message":
                "The chat does not belong to that user.",
        }), 403

    database().collection(
        "deletedItems"
    ).document(
        "chat-" + chat_id
    ).set({
        "type": "chat",
        "chatId": chat_id,
        "collection": collection_name,
        "userUid": record.uid,
        "userEmail": email,
        "reason": reason,
        "deletedAt": utc_now(),
        "deletedBy":
            request
            .chief_owner_identity["uid"],
        "data": old_data,
    })

    reference.delete()

    messages = database().collection(
        "messages"
    )

    for field in [
        "conversationId",
        "chatId",
    ]:
        try:
            stream = messages.where(
                field,
                "==",
                chat_id,
            ).stream()

            for message in stream:
                message.reference.delete()

        except Exception:
            continue

    create_audit(
        action="chats.delete",
        target_type="chat",
        target_id=chat_id,
        reason=reason,
        previous=old_data,
        new={
            "deleted": True,
            "userEmail": email,
        },
    )

    return jsonify({
        "ok": True,
        "message":
            "Chat and connected messages were deleted.",
    })


@chief_owner_control.get(
    "/api/chief-owner/audit-logs"
)
@require_chief_owner
def chief_owner_audit_logs():
    rows = []

    try:
        stream = (
            database()
            .collection("auditLogs")
            .order_by(
                "timestamp",
                direction=
                    firestore.Query.DESCENDING,
            )
            .limit(100)
            .stream()
        )

    except Exception:
        stream = (
            database()
            .collection("auditLogs")
            .limit(100)
            .stream()
        )

    for snapshot in stream:
        data = snapshot.to_dict() or {}

        rows.append({
            "id": snapshot.id,
            "actorEmail":
                data.get("actorEmail", ""),
            "action":
                data.get("action", ""),
            "targetType":
                data.get("targetType", ""),
            "targetId":
                data.get("targetId", ""),
            "reason":
                data.get("reason", ""),
            "timestamp":
                str(data.get("timestamp") or ""),
            "success":
                data.get("success", False),
        })

    return jsonify({
        "ok": True,
        "logs": rows,
    })



# MI COMPLETE RBAC EXTENSION START

ROLE_LEVELS = {
    "chief_owner": 120, "sub_owner": 110, "chief_director": 100,
    "sub_director": 90, "chief_manager": 80, "sub_manager": 70,
    "chief_developer": 60, "sub_developer": 50, "admin": 40,
    "support_agent": 30, "moderator": 20, "normal_user": 10,
}

BUILT_IN_ROLES = {
    "sub_owner", "chief_director", "sub_director", "chief_manager",
    "sub_manager", "chief_developer", "sub_developer", "admin",
    "support_agent", "moderator",
}

ALL_PERMISSIONS = sorted({
    "users.view","users.search","users.edit","users.suspend","users.block",
    "users.unblock","users.delete","users.restore","users.force_logout",
    "users.view_sessions","users.revoke_sessions","chats.view_reported",
    "chats.view_all","chats.search","chats.moderate","chats.delete_content",
    "messages.view_reported","messages.view_all","staff.view","staff.create",
    "staff.edit","staff.suspend","staff.remove","staff.promote","staff.demote",
    "roles.view","roles.assign","roles.remove","roles.create_template",
    "roles.edit_template","permissions.view","permissions.request",
    "permissions.approve","permissions.reject","permissions.grant",
    "permissions.revoke","support.view","support.assign","support.reply",
    "support.close","support.escalate","moderation.view","moderation.warn",
    "moderation.restrict","moderation.suspend","moderation.remove_content",
    "analytics.view_basic","analytics.view_advanced","analytics.export",
    "audit.view_own","audit.view_department","audit.view_all","audit.export",
    "ai.view","ai.manage_models","ai.manage_prompts","ai.manage_limits",
    "api.view_status","api.manage_configuration","api.rotate_credentials",
    "system.view_status","system.manage_settings","system.manage_features",
    "system.maintenance_mode","system.manage_branding",
    "system.manage_announcements","system.backup","system.restore",
    "security.view_alerts","security.manage_sessions",
    "security.manage_devices","security.block_device",
    "security.manage_ip_rules","ownership.view","ownership.transfer",
})


def mi_role_key(value):
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def mi_doc(collection, document_id):
    snapshot = database().collection(collection).document(document_id).get()
    return snapshot.to_dict() if snapshot.exists else {}


@chief_owner_control.get("/api/chief-owner/rbac-options")
@require_chief_owner
def mi_rbac_options():
    custom = []
    for snapshot in database().collection("roles").stream():
        data = snapshot.to_dict() or {}
        if data.get("active", True):
            custom.append(mi_role_key(data.get("key") or snapshot.id))
    return jsonify({
        "ok": True,
        "roles": sorted(BUILT_IN_ROLES | set(custom)),
        "permissions": ALL_PERMISSIONS,
    })


def whatsapp_away_sender_id():
    phone_number_id = str(
        current_app.config.get("WHATSAPP_AWAY_PHONE_NUMBER_ID") or ""
    ).strip()
    sender_provider = current_app.config.get(
        "WHATSAPP_SENDER_IDS_PROVIDER"
    )
    if not phone_number_id.isdigit() or not callable(sender_provider):
        return ""
    try:
        if phone_number_id not in sender_provider():
            return ""
    except Exception:
        return ""
    return phone_number_id


def whatsapp_coexistence_status(data):
    account_update = (data or {}).get("coexistence_accountUpdate") or {}
    if not isinstance(account_update, dict):
        return "not_observed"
    if data.get("manualReviewConfirmedAt"):
        return "manual_review_completed_unverified"
    allowed_states = {
        "PARTNER_ADDED": "partner_added_unverified",
        "PARTNER_APP_INSTALLED": "partner_app_installed_unverified",
        "PARTNER_APP_UNINSTALLED": "partner_app_uninstalled_needs_review",
        "PARTNER_REMOVED": "partner_removed",
        "ACCOUNT_DELETED": "account_deleted",
        "ACCOUNT_OFFBOARDED": "account_offboarded",
        "ACCOUNT_RECONNECTED": "reconnected_needs_review",
        "ACCOUNT_RESTRICTION": "account_restricted",
        "ACCOUNT_VIOLATION": "account_violation",
        "DISABLED_UPDATE": "disabled_state_changed_needs_review",
        "UNRECOGNIZED": "manual_review_required",
    }
    event = str(account_update.get("event") or "").strip().upper()
    status = str(account_update.get("status") or "").strip()
    return status if allowed_states.get(event) == status else "not_observed"


def whatsapp_manual_review_required(data):
    if (data or {}).get("manualReviewRequired") is True:
        return True
    return (
        isinstance((data or {}).get("coexistence_accountUpdate"), dict)
        and not (data or {}).get("manualReviewConfirmedAt")
    )


def _run_whatsapp_availability_transaction(database_client, operation):
    run_transaction = getattr(database_client, "run_transaction", None)
    if callable(run_transaction):
        return run_transaction(operation)

    transactional = getattr(firestore, "transactional", None)
    if not callable(transactional):
        raise RuntimeError("WhatsApp availability storage is unavailable")
    return transactional(operation)(database_client.transaction(max_attempts=5))


def whatsapp_away_mode_response(phone_number_id):
    if not phone_number_id:
        return {
            "ok": True,
            "configured": False,
            "mode": "AVAILABLE",
            "persistedMode": None,
            "effectiveMode": "AVAILABLE",
            "stateSource": "unconfigured",
            "coexistenceStatus": "not_configured",
            "manualReviewRequired": False,
            "reviewVersion": None,
        }

    try:
        database_provider = current_app.config.get(
            "WHATSAPP_FIRESTORE_PROVIDER"
        )
        database_client = database_provider() if callable(database_provider) else None
        if database_client is None:
            raise RuntimeError("WhatsApp availability storage is unavailable")
        snapshot = (
            database_client.collection("whatsappManualAvailability")
            .document(phone_number_id)
            .get()
        )
        exists = bool(snapshot.exists)
        data = snapshot.to_dict() or {} if exists else {}
    except Exception:
        return {
            "ok": True,
            "configured": True,
            "mode": "AVAILABLE",
            "persistedMode": None,
            "effectiveMode": "AVAILABLE",
            "stateSource": "unavailable",
            "coexistenceStatus": "unknown",
            "manualReviewRequired": True,
            "reviewVersion": None,
        }

    try:
        revision = _whatsapp_coexistence_revision(data) if exists else 0
    except ValueError:
        return {
            "ok": True,
            "configured": True,
            "mode": "AVAILABLE",
            "persistedMode": None,
            "effectiveMode": "AVAILABLE",
            "stateSource": "invalid",
            "coexistenceStatus": whatsapp_coexistence_status(data),
            "manualReviewRequired": True,
            "reviewVersion": None,
        }

    if not exists:
        return {
            "ok": True,
            "configured": True,
            "mode": "AVAILABLE",
            "persistedMode": None,
            "effectiveMode": "AVAILABLE",
            "stateSource": "default",
            "coexistenceStatus": "not_observed",
            "manualReviewRequired": False,
            "reviewVersion": None,
        }

    mode = str(data.get("mode") or "").strip().upper()
    manual_review_required = whatsapp_manual_review_required(data)
    if data.get("phoneNumberId") != phone_number_id or mode not in {"AVAILABLE", "AWAY"}:
        return {
            "ok": True,
            "configured": True,
            "mode": "AVAILABLE",
            "persistedMode": None,
            "effectiveMode": "AVAILABLE",
            "stateSource": "invalid",
            "coexistenceStatus": whatsapp_coexistence_status(data),
            "manualReviewRequired": True,
            "reviewVersion": revision,
        }
    return {
        "ok": True,
        "configured": True,
        "mode": "AVAILABLE" if manual_review_required else mode,
        "persistedMode": mode,
        "effectiveMode": "AVAILABLE" if manual_review_required else mode,
        "stateSource": "review_required" if manual_review_required else "persistent",
        "coexistenceStatus": whatsapp_coexistence_status(data),
        "manualReviewRequired": manual_review_required,
        "reviewVersion": revision if manual_review_required else None,
    }


@chief_owner_control.route(
    "/api/chief-owner/whatsapp-away-mode",
    methods=["GET", "POST"],
)
@require_chief_owner
def chief_owner_whatsapp_away_mode():
    phone_number_id = whatsapp_away_sender_id()
    if request.method == "GET":
        return jsonify(whatsapp_away_mode_response(phone_number_id))
    if not phone_number_id:
        return jsonify({
            "ok": False,
            "message": "The designated WhatsApp Business sender is not configured.",
        }), 503

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        payload = {}
    mode = str(payload.get("mode") or "").strip().upper()
    if mode not in {"AVAILABLE", "AWAY"}:
        return jsonify({
            "ok": False,
            "message": "Mode must be AVAILABLE or AWAY.",
        }), 400

    try:
        database_provider = current_app.config.get(
            "WHATSAPP_FIRESTORE_PROVIDER"
        )
        database_client = database_provider() if callable(database_provider) else None
        if database_client is None:
            raise RuntimeError("WhatsApp availability storage is unavailable")
        reference = (
            database_client.collection("whatsappManualAvailability")
            .document(phone_number_id)
        )
        review_confirmed = payload.get("reviewConfirmed") is True
        review_version = payload.get("reviewVersion")

        def update_mode(transaction):
            snapshot = reference.get(transaction=transaction)
            previous_data = snapshot.to_dict() or {} if snapshot.exists else {}
            current_revision = _whatsapp_coexistence_revision(previous_data)
            manual_review_required = whatsapp_manual_review_required(
                previous_data
            )
            if mode == "AWAY" and manual_review_required:
                if not review_confirmed:
                    return {"status": "manual_review_required"}
                if not _is_whatsapp_coexistence_revision(review_version):
                    return {"status": "invalid_review_version"}
                if (
                    review_version != current_revision
                ):
                    return {"status": "stale_review"}

            updated_state = {
                "phoneNumberId": phone_number_id,
                "mode": mode,
                "updatedAt": utc_now(),
                "updatedByUid": request.chief_owner_identity["uid"],
            }
            if mode == "AWAY" and manual_review_required:
                updated_state.update({
                    "manualReviewRequired": False,
                    "manualReviewConfirmedAt": utc_now(),
                    "manualReviewConfirmedByUid": (
                        request.chief_owner_identity["uid"]
                    ),
                })
            transaction.set(reference, updated_state, merge=True)
            return {
                "status": "updated",
                "previousMode": str(
                    previous_data.get("mode") or "AVAILABLE"
                ).upper(),
                "manualReviewRequired": manual_review_required,
            }

        update_result = _run_whatsapp_availability_transaction(
            database_client,
            update_mode,
        )
        if update_result["status"] == "manual_review_required":
            return jsonify({
                "ok": False,
                "code": "MANUAL_REVIEW_REQUIRED",
                "message": (
                    "Review the Meta account state and confirm its connection "
                    "before re-enabling AWAY."
                ),
            }), 409
        if update_result["status"] == "stale_review":
            return jsonify({
                "ok": False,
                "code": "STALE_REVIEW_CONFIRMATION",
                "message": (
                    "The Meta account state changed. Reload and review the "
                    "latest event before confirming AWAY."
                ),
            }), 409
        if update_result["status"] == "invalid_review_version":
            return jsonify({
                "ok": False,
                "code": "INVALID_REVIEW_VERSION",
                "message": "A valid current review revision is required.",
            }), 400

        previous_mode = update_result["previousMode"]
        manual_review_required = update_result["manualReviewRequired"]
        persisted_snapshot = reference.get()
        persisted_state = (
            persisted_snapshot.to_dict() or {}
            if persisted_snapshot.exists
            else {}
        )
        if mode == "AWAY" and whatsapp_manual_review_required(persisted_state):
            return jsonify({
                "ok": False,
                "code": "STALE_REVIEW_CONFIRMATION",
                "message": (
                    "The Meta account state changed. Reload and review the "
                    "latest event before confirming AWAY."
                ),
            }), 409
        if (
            persisted_state.get("phoneNumberId") != phone_number_id
            or persisted_state.get("mode") != mode
            or (
                mode == "AWAY"
                and manual_review_required
                and persisted_state.get("manualReviewRequired") is not False
            )
        ):
            raise RuntimeError("WhatsApp availability write was not confirmed")
    except Exception as exc:
        current_app.logger.warning(
            "WhatsApp away-mode update failed (%s)",
            type(exc).__name__,
        )
        return jsonify({
            "ok": False,
            "message": "Availability update failed; verify the currently saved mode.",
        }), 503

    try:
        create_audit(
            "whatsapp.manual_away_mode",
            "whatsapp_sender",
            phone_number_id,
            "Manual WhatsApp availability changed.",
            {"mode": previous_mode},
            {
                "mode": mode,
                "manualReviewConfirmed": (
                    mode == "AWAY" and manual_review_required
                ),
            },
        )
    except Exception:
        current_app.logger.warning("WhatsApp away-mode audit write failed.")

    manual_review_required = whatsapp_manual_review_required(persisted_state)
    return jsonify({
        "ok": True,
        "configured": True,
        "mode": mode,
        "persistedMode": mode,
        "effectiveMode": "AVAILABLE" if manual_review_required else mode,
        "stateSource": "persistent",
        "manualReviewRequired": manual_review_required,
        "coexistenceStatus": whatsapp_coexistence_status(persisted_state),
        "reviewVersion": None,
    })


@chief_owner_control.get(
    "/api/chief-owner/whatsapp-embedded-signup/readiness"
)
@require_chief_owner
def chief_owner_whatsapp_embedded_signup_readiness():
    required_settings = (
        "META_APP_ID",
        "META_EMBEDDED_SIGNUP_CONFIG_ID",
        "META_EMBEDDED_SIGNUP_VERSION",
        "META_EMBEDDED_SIGNUP_ENABLED",
        "WHATSAPP_APP_SECRET",
        "WHATSAPP_ID_HMAC_KEY",
        "WHATSAPP_VERIFY_TOKEN",
        "WHATSAPP_GRAPH_API_VERSION",
        "WHATSAPP_WABA_ID",
        "GROQ_API_KEY",
    )
    missing_settings = [
        setting
        for setting in required_settings
        if not str(os.getenv(setting) or "").strip()
    ]
    invalid_settings = []
    identifier_key = str(os.getenv("WHATSAPP_ID_HMAC_KEY") or "").strip()
    if identifier_key and len(identifier_key.encode("utf-8")) < 32:
        invalid_settings.append("WHATSAPP_ID_HMAC_KEY")
    version = str(os.getenv("META_EMBEDDED_SIGNUP_VERSION") or "").strip()
    unsupported_settings = (
        ["META_EMBEDDED_SIGNUP_VERSION"]
        if version and version not in {"v4", "v5"}
        else []
    )
    graph_version = str(os.getenv("WHATSAPP_GRAPH_API_VERSION") or "").strip()
    if graph_version and not re.fullmatch(r"v\d+\.\d+", graph_version):
        invalid_settings.append("WHATSAPP_GRAPH_API_VERSION")

    sender_provider = current_app.config.get("WHATSAPP_SENDER_IDS_PROVIDER")
    senders = {}
    sender_configuration_status = "not_configured"
    if callable(sender_provider):
        try:
            senders = sender_provider()
            sender_configuration_status = (
                "configured" if senders else "not_configured"
            )
        except Exception:
            sender_configuration_status = "configuration_error"
            invalid_settings.append("WHATSAPP_SENDERS_JSON")
    if not senders and "WHATSAPP_SENDERS_JSON" not in invalid_settings:
        missing_settings.append("WHATSAPP_SENDERS_JSON")

    designated_phone_number_id = str(
        current_app.config.get("WHATSAPP_AWAY_PHONE_NUMBER_ID") or ""
    ).strip()
    designated_sender_configured = (
        designated_phone_number_id.isdigit()
        and designated_phone_number_id in senders
    )
    if not designated_phone_number_id:
        missing_settings.append("WHATSAPP_AWAY_PHONE_NUMBER_ID")
    elif not designated_sender_configured:
        invalid_settings.append("WHATSAPP_AWAY_PHONE_NUMBER_ID")

    local_webhook_ready = (
        bool(str(os.getenv("WHATSAPP_APP_SECRET") or "").strip())
        and len(str(os.getenv("WHATSAPP_ID_HMAC_KEY") or "").strip().encode("utf-8")) >= 32
        and bool(str(os.getenv("WHATSAPP_VERIFY_TOKEN") or "").strip())
        and bool(senders)
        and bool(graph_version)
        and "WHATSAPP_GRAPH_API_VERSION" not in invalid_settings
    )
    configuration_ready = not (
        missing_settings or unsupported_settings or invalid_settings
    )
    enabled_by_configuration = str(
        os.getenv("META_EMBEDDED_SIGNUP_ENABLED") or ""
    ).strip().lower() in {"1", "true", "yes"}

    if unsupported_settings or invalid_settings:
        readiness_status = "configuration_error"
    elif missing_settings:
        readiness_status = "configuration_incomplete"
    else:
        readiness_status = "configuration_present_approval_unverified"

    return jsonify({
        "ok": True,
        "status": readiness_status,
        "missingSettings": missing_settings,
        "unsupportedSettings": unsupported_settings,
        "invalidSettings": invalid_settings,
        "configurationReady": configuration_ready,
        "enabledByConfiguration": enabled_by_configuration,
        "senderConfigurationStatus": sender_configuration_status,
        "designatedSenderConfigured": designated_sender_configured,
        "localWebhookStatus": (
            "configured" if local_webhook_ready else "configuration_incomplete"
        ),
        "webhookSubscriptionStatus": "unknown",
        "eligibilityStatus": "unknown",
        "signupStatus": "not_started",
        "launchEnabled": False,
        "metaApproval": "not_verified",
        "connectionStatus": "not_verified",
        "secureTokenStorageReady": False,
        "secureTokenStorageStatus": "unavailable",
        "requiredPermissions": [
            "whatsapp_business_management",
            "whatsapp_business_messaging",
        ],
        "businessManagementPermissionMayBeRequired": True,
        "message": (
            "Embedded Signup remains disabled until Meta approval, "
            "account eligibility, secure server-side code exchange, "
            "and approved token storage are verified."
        ),
    })


@chief_owner_control.get("/api/chief-owner/staff")
@require_chief_owner
def mi_staff_list():
    email = normalize_email(request.args.get("email"))
    rows = []
    if email:
        try:
            record = firebase_auth.get_user_by_email(email)
        except firebase_auth.UserNotFoundError:
            return jsonify({"ok": True, "staff": []})
        snapshot = database().collection("staffAccounts").document(record.uid).get()
        if snapshot.exists:
            row = snapshot.to_dict() or {}
            row["id"] = snapshot.id
            rows.append(row)
    else:
        for snapshot in database().collection("staffAccounts").limit(100).stream():
            row = snapshot.to_dict() or {}
            row["id"] = snapshot.id
            rows.append(row)
    return jsonify({"ok": True, "staff": rows})


@chief_owner_control.post("/api/chief-owner/staff/action")
@require_chief_owner
def mi_staff_action():
    body = request.get_json(silent=True) or {}
    email = normalize_email(body.get("email"))
    role = mi_role_key(body.get("role"))
    department = str(body.get("department") or "").strip()
    reason = str(body.get("reason") or "").strip()
    action = str(body.get("action") or "").strip().lower()

    if not email or "@" not in email:
        return jsonify({"ok": False, "message": "A valid staff email is required."}), 400
    if not reason:
        return jsonify({"ok": False, "message": "A written reason is required."}), 400

    protected_target(email)
    try:
        record = firebase_auth.get_user_by_email(email)
    except firebase_auth.UserNotFoundError:
        return jsonify({"ok": False, "message": "Account not found."}), 404

    reference = database().collection("staffAccounts").document(record.uid)
    previous = mi_doc("staffAccounts", record.uid)
    custom_roles = {
        mi_role_key((s.to_dict() or {}).get("key") or s.id)
        for s in database().collection("roles").stream()
        if (s.to_dict() or {}).get("active", True)
    }

    if action in {"assign_role", "promote", "demote"}:
        if role not in BUILT_IN_ROLES | custom_roles:
            return jsonify({"ok": False, "message": "Select a valid role."}), 400
        role_data = mi_doc("roles", role)
        permissions = sorted(set(role_data.get("permissions") or []))
        reference.set({
            "uid": record.uid, "email": email, "role": role,
            "department": department or previous.get("department", ""),
            "status": "active", "permissions": permissions,
            "updatedAt": utc_now(),
            "updatedBy": request.chief_owner_identity["uid"],
        }, merge=True)
        claims = dict(record.custom_claims or {})
        claims.update({"staff": True, "role": role, "permissions": permissions})
        firebase_auth.set_custom_user_claims(record.uid, claims)
        firebase_auth.revoke_refresh_tokens(record.uid)
    elif action == "suspend":
        reference.set({"status": "suspended", "updatedAt": utc_now()}, merge=True)
        claims = dict(record.custom_claims or {})
        claims["staffSuspended"] = True
        firebase_auth.set_custom_user_claims(record.uid, claims)
        firebase_auth.revoke_refresh_tokens(record.uid)
    elif action == "restore":
        reference.set({"status": "active", "updatedAt": utc_now()}, merge=True)
        claims = dict(record.custom_claims or {})
        claims.pop("staffSuspended", None)
        firebase_auth.set_custom_user_claims(record.uid, claims)
        firebase_auth.revoke_refresh_tokens(record.uid)
    elif action in {"remove_role", "remove_staff"}:
        reference.set({
            "role": "normal_user", "status": "removed",
            "permissions": [], "updatedAt": utc_now(),
        }, merge=True)
        claims = dict(record.custom_claims or {})
        for key in ("staff", "role", "permissions", "staffSuspended"):
            claims.pop(key, None)
        firebase_auth.set_custom_user_claims(record.uid, claims)
        firebase_auth.revoke_refresh_tokens(record.uid)
    else:
        return jsonify({"ok": False, "message": "Unsupported staff action."}), 400

    updated = mi_doc("staffAccounts", record.uid)
    create_audit("staff." + action, "staff", record.uid, reason, previous, updated)
    return jsonify({"ok": True, "message": "Staff action completed.", "staff": updated})


@chief_owner_control.post("/api/chief-owner/permissions/action")
@require_chief_owner
def mi_permission_action():
    body = request.get_json(silent=True) or {}
    email = normalize_email(body.get("email"))
    permission = str(body.get("permission") or "").strip()
    reason = str(body.get("reason") or "").strip()
    action = str(body.get("action") or "").strip().lower()

    if permission not in ALL_PERMISSIONS:
        return jsonify({"ok": False, "message": "Invalid permission."}), 400
    if not email or not reason:
        return jsonify({"ok": False, "message": "Email and reason are required."}), 400

    protected_target(email)
    try:
        record = firebase_auth.get_user_by_email(email)
    except firebase_auth.UserNotFoundError:
        return jsonify({"ok": False, "message": "Account not found."}), 404

    reference = database().collection("staffAccounts").document(record.uid)
    previous = mi_doc("staffAccounts", record.uid)
    permissions = set(previous.get("permissions") or [])
    if action == "grant":
        permissions.add(permission)
    elif action == "revoke":
        permissions.discard(permission)
    else:
        return jsonify({"ok": False, "message": "Invalid permission action."}), 400

    reference.set({"permissions": sorted(permissions), "updatedAt": utc_now()}, merge=True)
    claims = dict(record.custom_claims or {})
    claims["permissions"] = sorted(permissions)
    firebase_auth.set_custom_user_claims(record.uid, claims)
    firebase_auth.revoke_refresh_tokens(record.uid)
    updated = mi_doc("staffAccounts", record.uid)
    create_audit("permissions." + action, "staff", record.uid, reason, previous, updated)
    return jsonify({"ok": True, "message": "Permission action completed.", "permissions": sorted(permissions)})


@chief_owner_control.get("/api/chief-owner/roles")
@require_chief_owner
def mi_roles_list():
    rows = []
    for key in sorted(BUILT_IN_ROLES):
        data = mi_doc("roles", key)
        rows.append({
            "key": key,
            "name": data.get("name") or key.replace("_", " ").title(),
            "level": data.get("level") or ROLE_LEVELS[key],
            "permissions": data.get("permissions") or [],
            "builtIn": True,
            "active": data.get("active", True),
        })
    for snapshot in database().collection("roles").stream():
        data = snapshot.to_dict() or {}
        key = mi_role_key(data.get("key") or snapshot.id)
        if key not in BUILT_IN_ROLES:
            data["key"] = key
            data["builtIn"] = False
            rows.append(data)
    return jsonify({"ok": True, "roles": rows, "permissions": ALL_PERMISSIONS})


@chief_owner_control.post("/api/chief-owner/roles/action")
@require_chief_owner
def mi_roles_action():
    body = request.get_json(silent=True) or {}
    action = str(body.get("action") or "").strip().lower()
    key = mi_role_key(body.get("key"))
    name = str(body.get("name") or "").strip()
    reason = str(body.get("reason") or "").strip()
    permissions = sorted({
        str(item) for item in body.get("permissions", [])
        if str(item) in ALL_PERMISSIONS
    })
    try:
        level = int(body.get("level"))
    except Exception:
        level = 0

    if not key or not reason:
        return jsonify({"ok": False, "message": "Role key and reason are required."}), 400
    if key in {"chief_owner", "normal_user"}:
        return jsonify({"ok": False, "message": "Protected role."}), 403
    if action == "delete" and key in BUILT_IN_ROLES:
        return jsonify({"ok": False, "message": "Built-in roles cannot be deleted."}), 403
    if action in {"create", "update"} and (not name or level <= 10 or level >= 120):
        return jsonify({"ok": False, "message": "Name and level 11-119 are required."}), 400

    reference = database().collection("roles").document(key)
    previous = mi_doc("roles", key)
    if action in {"create", "update"}:
        reference.set({
            "key": key, "name": name, "level": level,
            "permissions": permissions, "active": True,
            "builtIn": key in BUILT_IN_ROLES,
            "updatedAt": utc_now(),
            "updatedBy": request.chief_owner_identity["uid"],
        }, merge=True)
        updated = mi_doc("roles", key)
    elif action == "delete":
        reference.delete()
        updated = {"deleted": True}
    else:
        return jsonify({"ok": False, "message": "Invalid role action."}), 400

    create_audit("roles." + action, "role", key, reason, previous, updated)
    return jsonify({"ok": True, "message": "Role action completed.", "role": updated})

# MI COMPLETE RBAC EXTENSION END


def register_chief_owner_control(app):
    if (
        "chief_owner_control"
        not in app.blueprints
    ):
        app.register_blueprint(
            chief_owner_control
        )