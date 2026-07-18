import os
import uuid
from datetime import datetime, timezone
from functools import wraps

from flask import Blueprint, current_app, jsonify, request

try:
    from firebase_admin import auth as firebase_auth
    from firebase_admin import firestore
except Exception:
    firebase_auth = None
    firestore = None


CHIEF_OWNER_EMAIL = (
    os.getenv(
        "CHIEF_OWNER_EMAIL",
        "teamofchatbot.miai@gmail.com",
    )
    .strip()
    .lower()
)

CHIEF_OWNER_UID = os.getenv(
    "CHIEF_OWNER_UID",
    "",
).strip()

chief_owner_control = Blueprint(
    "chief_owner_control",
    __name__,
)


def utc_now():
    return datetime.now(timezone.utc)


def database():
    if firestore is None:
        raise RuntimeError(
            "Firebase Admin Firestore is unavailable."
        )

    return firestore.client()


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
        "token": decoded,
    }


def is_chief_owner(identity):
    if identity["email"] != CHIEF_OWNER_EMAIL:
        return False

    if (
        CHIEF_OWNER_UID
        and identity["uid"] != CHIEF_OWNER_UID
    ):
        return False

    return True


def require_chief_owner(function):
    @wraps(function)
    def protected(*args, **kwargs):
        try:
            identity = verify_identity()

            if not is_chief_owner(identity):
                create_security_alert(
                    "unauthorized_chief_owner_access",
                    identity,
                )

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


def register_chief_owner_control(app):
    if (
        "chief_owner_control"
        not in app.blueprints
    ):
        app.register_blueprint(
            chief_owner_control
        )