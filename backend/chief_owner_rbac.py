"""Secure Firebase-backed RBAC system for MI AI.

Security rules:
- Firebase ID tokens are verified server-side.
- Frontend role/permission claims are never trusted.
- Staff authority is loaded from Firestore.
- The permanent Chief Owner is protected from lower-level changes.
- Sensitive actions are audited.
"""

from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable, Dict, Iterable, Optional, Set, Tuple

from flask import Blueprint, jsonify, request

try:
    import firebase_admin
    from firebase_admin import auth, firestore
except Exception as exc:  # pragma: no cover
    firebase_admin = None
    auth = None
    firestore = None
    FIREBASE_IMPORT_ERROR = exc
else:
    FIREBASE_IMPORT_ERROR = None


CHIEF_OWNER_EMAIL = os.getenv(
    "CHIEF_OWNER_EMAIL",
    "teamofchatbot.miai@gmail.com",
).strip().lower()

ROLE_ORDER = [
    "chief_owner",
    "sub_owner",
    "chief_director",
    "sub_director",
    "chief_manager",
    "sub_manager",
    "chief_developer",
    "sub_developer",
    "admin",
    "support_agent",
    "moderator",
    "normal_user",
]

ROLE_LABELS = {
    "chief_owner": "Chief Owner",
    "sub_owner": "Sub Owner",
    "chief_director": "Chief Director",
    "sub_director": "Sub Director",
    "chief_manager": "Chief Manager",
    "sub_manager": "Sub Manager",
    "chief_developer": "Chief Developer",
    "sub_developer": "Sub Developer",
    "admin": "Admin",
    "support_agent": "Support Agent",
    "moderator": "Moderator",
    "normal_user": "Normal User",
}

ALL_PERMISSIONS: Set[str] = {
    "users.view", "users.search", "users.edit", "users.suspend",
    "users.block", "users.unblock", "users.delete", "users.restore",
    "users.force_logout", "users.view_sessions", "users.revoke_sessions",
    "chats.view_reported", "chats.view_all", "chats.search",
    "chats.moderate", "chats.delete_content",
    "messages.view_reported", "messages.view_all",
    "staff.view", "staff.create", "staff.edit", "staff.suspend",
    "staff.remove", "staff.promote", "staff.demote",
    "roles.view", "roles.assign", "roles.remove",
    "roles.create_template", "roles.edit_template",
    "permissions.view", "permissions.request", "permissions.approve",
    "permissions.reject", "permissions.grant", "permissions.revoke",
    "support.view", "support.assign", "support.reply",
    "support.close", "support.escalate",
    "moderation.view", "moderation.warn", "moderation.restrict",
    "moderation.suspend", "moderation.remove_content",
    "analytics.view_basic", "analytics.view_advanced", "analytics.export",
    "audit.view_own", "audit.view_department", "audit.view_all", "audit.export",
    "ai.view", "ai.manage_models", "ai.manage_prompts", "ai.manage_limits",
    "api.view_status", "api.manage_configuration", "api.rotate_credentials",
    "system.view_status", "system.manage_settings", "system.manage_features",
    "system.maintenance_mode", "system.manage_branding",
    "system.manage_announcements", "system.backup", "system.restore",
    "security.view_alerts", "security.manage_sessions",
    "security.manage_devices", "security.block_device",
    "security.manage_ip_rules",
    "ownership.view", "ownership.transfer",
}

DEFAULT_ROLE_PERMISSIONS: Dict[str, Set[str]] = {
    "chief_owner": set(ALL_PERMISSIONS),
    "sub_owner": set(ALL_PERMISSIONS) - {
        "ownership.transfer",
        "api.rotate_credentials",
        "system.restore",
    },
    "chief_director": {
        "users.view", "users.search", "staff.view", "staff.create",
        "staff.edit", "staff.promote", "staff.demote", "roles.view",
        "roles.assign", "permissions.view", "permissions.approve",
        "permissions.reject", "moderation.view", "support.view",
        "analytics.view_basic", "analytics.view_advanced",
        "audit.view_department", "system.view_status",
        "system.manage_announcements",
    },
    "sub_director": {
        "users.view", "users.search", "staff.view", "staff.edit",
        "roles.view", "permissions.view", "permissions.approve",
        "permissions.reject", "moderation.view", "support.view",
        "analytics.view_basic", "audit.view_department",
    },
    "chief_manager": {
        "users.view", "users.search", "users.suspend", "staff.view",
        "staff.edit", "roles.view", "roles.assign", "permissions.view",
        "permissions.approve", "permissions.reject", "support.view",
        "support.assign", "support.reply", "support.close",
        "moderation.view", "moderation.warn", "moderation.restrict",
        "analytics.view_basic", "audit.view_department",
    },
    "sub_manager": {
        "users.view", "users.search", "support.view", "support.assign",
        "support.reply", "support.close", "support.escalate",
        "moderation.view", "moderation.warn", "moderation.restrict",
        "analytics.view_basic", "audit.view_department",
    },
    "chief_developer": {
        "staff.view", "staff.edit", "roles.view", "roles.assign",
        "permissions.view", "permissions.approve", "permissions.reject",
        "ai.view", "ai.manage_models", "ai.manage_prompts",
        "ai.manage_limits", "api.view_status", "api.manage_configuration",
        "system.view_status", "system.manage_features",
        "system.maintenance_mode", "security.view_alerts",
        "audit.view_department",
    },
    "sub_developer": {
        "ai.view", "api.view_status", "system.view_status",
        "audit.view_department",
    },
    "admin": {
        "users.view", "users.search", "users.suspend",
        "chats.view_reported", "messages.view_reported",
        "support.view", "support.reply", "support.escalate",
        "moderation.view", "moderation.warn", "moderation.restrict",
        "analytics.view_basic", "audit.view_own",
    },
    "support_agent": {
        "users.view", "support.view", "support.reply",
        "support.close", "support.escalate", "audit.view_own",
    },
    "moderator": {
        "users.view", "chats.view_reported", "messages.view_reported",
        "chats.moderate", "moderation.view", "moderation.warn",
        "moderation.restrict", "moderation.remove_content",
        "audit.view_own",
    },
    "normal_user": set(),
}

HIGH_RISK_PERMISSIONS = {
    "ownership.transfer",
    "api.rotate_credentials",
    "system.restore",
    "system.maintenance_mode",
    "staff.remove",
    "users.delete",
}

rbac_bp = Blueprint("mi_rbac", __name__)


class AuthorizationError(Exception):
    def __init__(self, message: str, status: int = 403, code: str = "forbidden"):
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _firebase_ready() -> None:
    if FIREBASE_IMPORT_ERROR is not None:
        raise RuntimeError(f"firebase-admin is unavailable: {FIREBASE_IMPORT_ERROR}")
    if not firebase_admin._apps:
        raise RuntimeError(
            "Firebase Admin is not initialized. Initialize it once in backend/app.py "
            "before registering the RBAC blueprint."
        )


def db():
    _firebase_ready()
    return firestore.client()


def normalize_email(value: Any) -> str:
    return str(value or "").strip().lower()


def normalize_role(value: Any) -> str:
    role = str(value or "").strip().lower().replace(" ", "_")
    if role not in ROLE_ORDER:
        raise AuthorizationError("Invalid role.", 400, "invalid_role")
    return role


def role_rank(role: str) -> int:
    try:
        return ROLE_ORDER.index(role)
    except ValueError:
        return len(ROLE_ORDER)


def safe_permissions(values: Iterable[Any]) -> Set[str]:
    return {str(item) for item in values if str(item) in ALL_PERMISSIONS}


def effective_permissions(staff_record: Dict[str, Any]) -> Set[str]:
    role = staff_record.get("role", "normal_user")
    defaults = DEFAULT_ROLE_PERMISSIONS.get(role, set())
    grants = safe_permissions(staff_record.get("customPermissions", []))
    revokes = safe_permissions(staff_record.get("revokedPermissions", []))
    return (set(defaults) | grants) - revokes


def request_metadata() -> Dict[str, Any]:
    forwarded = request.headers.get("X-Forwarded-For", "")
    ip_address = forwarded.split(",")[0].strip() if forwarded else request.remote_addr
    user_agent = request.headers.get("User-Agent", "")[:500]
    request_id = (
        request.headers.get("X-Request-ID")
        or request.headers.get("X-Vercel-ID")
        or secrets.token_hex(10)
    )
    session_source = request.headers.get("X-Session-ID", "")
    session_id = hashlib.sha256(session_source.encode("utf-8")).hexdigest()[:32] if session_source else None
    return {
        "ipAddress": ip_address,
        "deviceInfo": user_agent,
        "requestId": request_id,
        "sessionId": session_id,
    }


def create_audit_log(
    *,
    actor: Dict[str, Any],
    action: str,
    target_type: str,
    target_id: str,
    reason: str,
    previous_value: Any = None,
    new_value: Any = None,
    success: bool = True,
    error_message: Optional[str] = None,
) -> None:
    metadata = request_metadata()
    payload = {
        "actorUserId": actor.get("uid"),
        "actorName": actor.get("name") or actor.get("email"),
        "actorEmail": actor.get("email"),
        "actorRole": actor.get("role"),
        "action": action,
        "targetType": target_type,
        "targetId": target_id,
        "previousValue": previous_value,
        "newValue": new_value,
        "reason": reason,
        "timestamp": firestore.SERVER_TIMESTAMP,
        "success": bool(success),
        "errorMessage": error_message,
        **metadata,
    }
    db().collection("auditLogs").add(payload)


def _extract_bearer_token() -> str:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise AuthorizationError("Authentication required.", 401, "authentication_required")
    token = header[7:].strip()
    if not token:
        raise AuthorizationError("Authentication required.", 401, "authentication_required")
    return token


def _load_staff_record(uid: str) -> Optional[Dict[str, Any]]:
    snap = db().collection("staffAccounts").document(uid).get()
    if not snap.exists:
        return None
    data = snap.to_dict() or {}
    data["uid"] = uid
    return data


def _ensure_chief_owner(decoded: Dict[str, Any]) -> Dict[str, Any]:
    uid = decoded["uid"]
    email = normalize_email(decoded.get("email"))
    if email != CHIEF_OWNER_EMAIL:
        raise AuthorizationError("Chief Owner identity mismatch.", 403, "owner_identity_mismatch")

    owner_ref = db().collection("systemSettings").document("ownership")
    staff_ref = db().collection("staffAccounts").document(uid)
    transaction = db().transaction()

    @firestore.transactional
    def apply(transaction):
        owner_snap = owner_ref.get(transaction=transaction)
        owner_data = owner_snap.to_dict() if owner_snap.exists else {}

        existing_uid = owner_data.get("chiefOwnerUid")
        existing_email = normalize_email(owner_data.get("chiefOwnerEmail"))

        if existing_uid and existing_uid != uid:
            raise AuthorizationError(
                "A different protected Chief Owner UID is already configured.",
                409,
                "chief_owner_conflict",
            )
        if existing_email and existing_email != CHIEF_OWNER_EMAIL:
            raise AuthorizationError(
                "Protected Chief Owner email mismatch.",
                409,
                "chief_owner_email_conflict",
            )

        transaction.set(
            owner_ref,
            {
                "chiefOwnerUid": uid,
                "chiefOwnerEmail": CHIEF_OWNER_EMAIL,
                "protected": True,
                "updatedAt": firestore.SERVER_TIMESTAMP,
            },
            merge=True,
        )
        transaction.set(
            staff_ref,
            {
                "uid": uid,
                "email": CHIEF_OWNER_EMAIL,
                "fullName": decoded.get("name") or "Chief Owner",
                "role": "chief_owner",
                "roleLabel": ROLE_LABELS["chief_owner"],
                "department": "Ownership",
                "position": "Chief Owner",
                "status": "active",
                "isStaff": True,
                "protected": True,
                "permanent": True,
                "customPermissions": [],
                "revokedPermissions": [],
                "updatedAt": firestore.SERVER_TIMESTAMP,
                "createdAt": firestore.SERVER_TIMESTAMP,
            },
            merge=True,
        )

    apply(transaction)
    record = _load_staff_record(uid) or {}
    record["uid"] = uid
    return record


def load_actor() -> Dict[str, Any]:
    _firebase_ready()
    decoded = auth.verify_id_token(_extract_bearer_token(), check_revoked=True)
    uid = decoded.get("uid")
    if not uid:
        raise AuthorizationError("Invalid authentication token.", 401, "invalid_token")

    email = normalize_email(decoded.get("email"))
    if email == CHIEF_OWNER_EMAIL:
        staff = _ensure_chief_owner(decoded)
    else:
        staff = _load_staff_record(uid)

    if not staff:
        raise AuthorizationError("Staff access required.", 403, "staff_required")

    status = str(staff.get("status", "inactive")).lower()
    if status != "active":
        raise AuthorizationError(
            f"Staff account is {status}.",
            403,
            "staff_inactive",
        )

    expires_at = staff.get("expiresAt")
    if expires_at and hasattr(expires_at, "timestamp"):
        if expires_at.timestamp() <= utc_now().timestamp():
            raise AuthorizationError("Staff access has expired.", 403, "staff_expired")

    authoritative_email = normalize_email(staff.get("email"))
    if authoritative_email != email:
        raise AuthorizationError("Staff identity mismatch.", 403, "identity_mismatch")

    role = normalize_role(staff.get("role"))
    permissions = effective_permissions(staff)

    return {
        "uid": uid,
        "email": email,
        "name": staff.get("fullName") or decoded.get("name") or email,
        "role": role,
        "roleLabel": ROLE_LABELS[role],
        "permissions": permissions,
        "department": staff.get("department"),
        "record": staff,
    }


def require_staff(permission: Optional[str] = None, chief_owner: bool = False):
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                actor = load_actor()
                if chief_owner and actor["role"] != "chief_owner":
                    raise AuthorizationError(
                        "Chief Owner permission required.",
                        403,
                        "chief_owner_required",
                    )
                if permission and permission not in actor["permissions"]:
                    raise AuthorizationError(
                        f"Missing permission: {permission}",
                        403,
                        "permission_required",
                    )
                return func(actor, *args, **kwargs)
            except AuthorizationError as exc:
                return jsonify({"ok": False, "error": exc.code, "message": exc.message}), exc.status
            except Exception as exc:
                return jsonify({
                    "ok": False,
                    "error": "authorization_failed",
                    "message": "Authorization could not be completed securely.",
                }), 500
        return wrapper
    return decorator


def validate_target_authority(actor: Dict[str, Any], target: Dict[str, Any], new_role: Optional[str] = None) -> None:
    target_role = normalize_role(target.get("role", "normal_user"))
    target_email = normalize_email(target.get("email"))
    target_uid = str(target.get("uid") or "")

    if target_email == CHIEF_OWNER_EMAIL or target_role == "chief_owner" or target.get("protected"):
        if actor["role"] != "chief_owner" or actor["uid"] == target_uid:
            raise AuthorizationError(
                "The protected Chief Owner record cannot be modified by this action.",
                403,
                "chief_owner_protected",
            )
        raise AuthorizationError(
            "Use the dedicated Ownership Transfer workflow.",
            403,
            "ownership_transfer_required",
        )

    if actor["role"] != "chief_owner":
        if role_rank(actor["role"]) >= role_rank(target_role):
            raise AuthorizationError(
                "You cannot modify an equal or higher role.",
                403,
                "target_authority_denied",
            )
        if new_role and role_rank(actor["role"]) >= role_rank(new_role):
            raise AuthorizationError(
                "You cannot grant a role equal to or higher than your own.",
                403,
                "grant_authority_denied",
            )


def public_staff(record: Dict[str, Any]) -> Dict[str, Any]:
    role = normalize_role(record.get("role", "normal_user"))
    return {
        "uid": record.get("uid"),
        "fullName": record.get("fullName"),
        "email": normalize_email(record.get("email")),
        "role": role,
        "roleLabel": ROLE_LABELS[role],
        "department": record.get("department"),
        "position": record.get("position"),
        "status": record.get("status"),
        "isStaff": bool(record.get("isStaff")),
        "protected": bool(record.get("protected")),
        "customPermissions": sorted(safe_permissions(record.get("customPermissions", []))),
        "revokedPermissions": sorted(safe_permissions(record.get("revokedPermissions", []))),
        "effectivePermissions": sorted(effective_permissions(record)),
        "expiresAt": record.get("expiresAt"),
        "updatedAt": record.get("updatedAt"),
    }


@rbac_bp.get("/api/rbac/me")
@require_staff()
def rbac_me(actor):
    return jsonify({
        "ok": True,
        "staff": {
            "uid": actor["uid"],
            "email": actor["email"],
            "name": actor["name"],
            "role": actor["role"],
            "roleLabel": actor["roleLabel"],
            "department": actor["department"],
            "permissions": sorted(actor["permissions"]),
            "isChiefOwner": actor["role"] == "chief_owner",
        },
    })


@rbac_bp.get("/api/rbac/roles")
@require_staff("roles.view")
def list_roles(actor):
    assignable = []
    for role in ROLE_ORDER:
        if role == "chief_owner":
            continue
        if actor["role"] == "chief_owner" or role_rank(actor["role"]) < role_rank(role):
            assignable.append({
                "value": role,
                "label": ROLE_LABELS[role],
                "defaultPermissions": sorted(DEFAULT_ROLE_PERMISSIONS[role]),
            })
    return jsonify({
        "ok": True,
        "roles": assignable,
        "allPermissions": sorted(ALL_PERMISSIONS)
        if "permissions.view" in actor["permissions"]
        else [],
    })


@rbac_bp.get("/api/rbac/staff")
@require_staff("staff.view")
def list_staff(actor):
    limit = min(max(int(request.args.get("limit", 100)), 1), 250)
    records = []
    for snap in db().collection("staffAccounts").limit(limit).stream():
        item = snap.to_dict() or {}
        item["uid"] = snap.id
        target_role = item.get("role", "normal_user")
        if actor["role"] != "chief_owner" and role_rank(actor["role"]) >= role_rank(target_role):
            continue
        records.append(public_staff(item))
    records.sort(key=lambda item: (role_rank(item["role"]), item.get("fullName") or ""))
    return jsonify({"ok": True, "staff": records})


@rbac_bp.post("/api/rbac/staff/assign")
@require_staff("roles.assign")
def assign_staff(actor):
    payload = request.get_json(silent=True) or {}
    email = normalize_email(payload.get("email"))
    requested_role = normalize_role(payload.get("role"))
    full_name = str(payload.get("fullName") or "").strip()
    department = str(payload.get("department") or "General").strip()[:120]
    position = str(payload.get("position") or ROLE_LABELS[requested_role]).strip()[:120]
    reason = str(payload.get("reason") or "").strip()
    custom_permissions = safe_permissions(payload.get("customPermissions") or [])

    if not email or "@" not in email:
        raise AuthorizationError("A valid email is required.", 400, "invalid_email")
    if not reason:
        raise AuthorizationError("A written reason is required.", 400, "reason_required")
    if email == CHIEF_OWNER_EMAIL or requested_role == "chief_owner":
        raise AuthorizationError(
            "Chief Owner can only be managed through Ownership Transfer.",
            403,
            "chief_owner_protected",
        )
    if actor["role"] != "chief_owner" and role_rank(actor["role"]) >= role_rank(requested_role):
        raise AuthorizationError(
            "You cannot grant this role.",
            403,
            "grant_authority_denied",
        )
    if not custom_permissions.issubset(actor["permissions"]) and actor["role"] != "chief_owner":
        raise AuthorizationError(
            "You cannot grant permissions you do not possess.",
            403,
            "permission_grant_denied",
        )
    if HIGH_RISK_PERMISSIONS.intersection(custom_permissions) and actor["role"] != "chief_owner":
        raise AuthorizationError(
            "High-risk permissions require Chief Owner approval.",
            403,
            "chief_owner_approval_required",
        )

    try:
        user_record = auth.get_user_by_email(email)
    except auth.UserNotFoundError:
        raise AuthorizationError(
            "This email must first have a verified MI AI account.",
            404,
            "user_not_found",
        )

    if not user_record.email_verified:
        raise AuthorizationError(
            "The account email must be verified before staff access is granted.",
            400,
            "email_not_verified",
        )

    target_ref = db().collection("staffAccounts").document(user_record.uid)
    previous_snap = target_ref.get()
    previous = previous_snap.to_dict() if previous_snap.exists else None
    if previous:
        previous["uid"] = user_record.uid
        validate_target_authority(actor, previous, requested_role)

    record = {
        "uid": user_record.uid,
        "email": email,
        "fullName": full_name or user_record.display_name or email.split("@")[0],
        "role": requested_role,
        "roleLabel": ROLE_LABELS[requested_role],
        "department": department,
        "position": position,
        "status": "active",
        "isStaff": True,
        "protected": False,
        "permanent": True,
        "customPermissions": sorted(custom_permissions),
        "revokedPermissions": [],
        "reasonForAccess": reason,
        "createdBy": actor["uid"],
        "createdByEmail": actor["email"],
        "updatedAt": firestore.SERVER_TIMESTAMP,
    }
    if not previous:
        record["createdAt"] = firestore.SERVER_TIMESTAMP

    target_ref.set(record, merge=True)

    create_audit_log(
        actor=actor,
        action="staff.role_assigned" if not previous else "staff.role_changed",
        target_type="staffAccount",
        target_id=user_record.uid,
        reason=reason,
        previous_value=public_staff(previous) if previous else None,
        new_value={
            "email": email,
            "role": requested_role,
            "customPermissions": sorted(custom_permissions),
            "department": department,
        },
    )

    saved = target_ref.get().to_dict() or record
    saved["uid"] = user_record.uid
    return jsonify({
        "ok": True,
        "message": f"{ROLE_LABELS[requested_role]} access granted to {email}.",
        "staff": public_staff(saved),
    })


@rbac_bp.post("/api/rbac/staff/<target_uid>/status")
@require_staff("staff.suspend")
def update_staff_status(actor, target_uid):
    payload = request.get_json(silent=True) or {}
    status = str(payload.get("status") or "").strip().lower()
    reason = str(payload.get("reason") or "").strip()
    if status not in {"active", "suspended", "disabled"}:
        raise AuthorizationError("Invalid staff status.", 400, "invalid_status")
    if not reason:
        raise AuthorizationError("A written reason is required.", 400, "reason_required")

    ref = db().collection("staffAccounts").document(target_uid)
    snap = ref.get()
    if not snap.exists:
        raise AuthorizationError("Staff account not found.", 404, "staff_not_found")
    target = snap.to_dict() or {}
    target["uid"] = target_uid
    validate_target_authority(actor, target)

    previous_status = target.get("status")
    ref.set({
        "status": status,
        "statusReason": reason,
        "updatedBy": actor["uid"],
        "updatedAt": firestore.SERVER_TIMESTAMP,
    }, merge=True)

    if status != "active":
        try:
            auth.revoke_refresh_tokens(target_uid)
        except Exception:
            pass

    create_audit_log(
        actor=actor,
        action=f"staff.status_{status}",
        target_type="staffAccount",
        target_id=target_uid,
        reason=reason,
        previous_value={"status": previous_status},
        new_value={"status": status},
    )
    return jsonify({"ok": True, "message": f"Staff account is now {status}."})


@rbac_bp.post("/api/rbac/staff/<target_uid>/remove")
@require_staff("staff.remove")
def remove_staff(actor, target_uid):
    payload = request.get_json(silent=True) or {}
    reason = str(payload.get("reason") or "").strip()
    if not reason:
        raise AuthorizationError("A written reason is required.", 400, "reason_required")

    ref = db().collection("staffAccounts").document(target_uid)
    snap = ref.get()
    if not snap.exists:
        raise AuthorizationError("Staff account not found.", 404, "staff_not_found")
    target = snap.to_dict() or {}
    target["uid"] = target_uid
    validate_target_authority(actor, target)

    previous = public_staff(target)
    ref.set({
        "role": "normal_user",
        "roleLabel": ROLE_LABELS["normal_user"],
        "status": "disabled",
        "isStaff": False,
        "customPermissions": [],
        "revokedPermissions": [],
        "removedBy": actor["uid"],
        "removedReason": reason,
        "removedAt": firestore.SERVER_TIMESTAMP,
        "updatedAt": firestore.SERVER_TIMESTAMP,
    }, merge=True)
    try:
        auth.revoke_refresh_tokens(target_uid)
    except Exception:
        pass

    create_audit_log(
        actor=actor,
        action="staff.removed",
        target_type="staffAccount",
        target_id=target_uid,
        reason=reason,
        previous_value=previous,
        new_value={"role": "normal_user", "isStaff": False, "status": "disabled"},
    )
    return jsonify({"ok": True, "message": "Staff access removed and sessions revoked."})


@rbac_bp.post("/api/rbac/permissions/request")
@require_staff()
def create_permission_request(actor):
    payload = request.get_json(silent=True) or {}
    requested_permissions = safe_permissions(payload.get("permissions") or [])
    reason = str(payload.get("reason") or "").strip()
    business_purpose = str(payload.get("businessPurpose") or "").strip()
    duration = str(payload.get("duration") or "permanent").strip()

    if not requested_permissions:
        raise AuthorizationError("Select at least one permission.", 400, "permission_required")
    if not reason or not business_purpose:
        raise AuthorizationError(
            "Reason and business purpose are required.",
            400,
            "request_details_required",
        )

    request_ref = db().collection("permissionRequests").document()
    request_ref.set({
        "requestId": request_ref.id,
        "requestingUserId": actor["uid"],
        "requestingEmail": actor["email"],
        "currentRole": actor["role"],
        "requestedPermissions": sorted(requested_permissions),
        "reason": reason,
        "businessPurpose": business_purpose,
        "requestedDuration": duration,
        "status": "pending",
        "dateSubmitted": firestore.SERVER_TIMESTAMP,
        "auditHistory": [{
            "action": "submitted",
            "actorUid": actor["uid"],
            "actorEmail": actor["email"],
            "timestamp": utc_now().isoformat(),
        }],
    })
    create_audit_log(
        actor=actor,
        action="permission_request.created",
        target_type="permissionRequest",
        target_id=request_ref.id,
        reason=reason,
        new_value={"permissions": sorted(requested_permissions), "duration": duration},
    )
    return jsonify({"ok": True, "requestId": request_ref.id})


@rbac_bp.get("/api/rbac/health")
def rbac_health():
    return jsonify({
        "ok": True,
        "service": "mi-ai-secure-rbac",
        "chiefOwnerEmailConfigured": bool(CHIEF_OWNER_EMAIL),
        "roleCount": len(ROLE_ORDER),
        "permissionCount": len(ALL_PERMISSIONS),
    })


def register_rbac(app) -> None:
    if "mi_rbac" not in app.blueprints:
        app.register_blueprint(rbac_bp)