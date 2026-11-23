import os
import re
import unicodedata


_EMAIL_PATTERN = re.compile(r"[^@\s]+@[^@\s.]+(?:\.[^@\s.]+)+")
_UID_MAX_LENGTH = 128


def normalize_chief_owner_email(value):
    email = str(value or "").strip().lower()
    if len(email) > 254 or not _EMAIL_PATTERN.fullmatch(email):
        return ""
    return email


def resolve_chief_owner_email(environ=None):
    environment = os.environ if environ is None else environ
    if "CHIEF_OWNER_EMAIL" in environment:
        configured_email = environment.get("CHIEF_OWNER_EMAIL")
    else:
        configured_email = environment.get("MI_CHIEF_OWNER_EMAIL")
    return normalize_chief_owner_email(configured_email)


def normalize_chief_owner_uid(value):
    if not isinstance(value, str):
        return ""
    if any(unicodedata.category(character) == "Cc" for character in value):
        return ""
    uid = value.strip()
    if (
        not uid
        or len(uid) > _UID_MAX_LENGTH
        or any(character.isspace() for character in uid)
    ):
        return ""
    return uid


def resolve_chief_owner_uid(environ=None):
    environment = os.environ if environ is None else environ
    configured = "CHIEF_OWNER_UID" in environment
    if not configured:
        return "", False, True

    uid = normalize_chief_owner_uid(environment.get("CHIEF_OWNER_UID"))
    return uid, True, bool(uid)


def is_chief_owner_candidate(
    email,
    uid,
    email_verified,
    configured_email=None,
    configured_uid=None,
    uid_configured=None,
    uid_config_valid=None,
):
    configured_email = (
        CHIEF_OWNER_EMAIL if configured_email is None else configured_email
    )
    configured_uid = (
        CHIEF_OWNER_UID if configured_uid is None else configured_uid
    )
    uid_configured = (
        CHIEF_OWNER_UID_CONFIGURED or bool(configured_uid)
        if uid_configured is None
        else uid_configured
    )
    uid_config_valid = (
        CHIEF_OWNER_UID_CONFIG_VALID
        if uid_config_valid is None
        else uid_config_valid
    )

    normalized_email = normalize_chief_owner_email(email)
    normalized_uid = normalize_chief_owner_uid(uid)
    normalized_configured_uid = normalize_chief_owner_uid(configured_uid)

    if (
        not configured_email
        or normalized_email != configured_email
        or not email_verified
        or not normalized_uid
        or not uid_config_valid
    ):
        return False

    if uid_configured:
        return bool(normalized_configured_uid) and (
            normalized_uid == normalized_configured_uid
        )

    return True


def is_chief_owner_identity(
    email,
    uid,
    persisted_uid=None,
    email_verified=False,
    configured_email=None,
    configured_uid=None,
    uid_configured=None,
    uid_config_valid=None,
):
    uid_configured = (
        CHIEF_OWNER_UID_CONFIGURED or bool(configured_uid)
        if uid_configured is None
        else uid_configured
    )
    if not is_chief_owner_candidate(
        email,
        uid,
        email_verified,
        configured_email=configured_email,
        configured_uid=configured_uid,
        uid_configured=uid_configured,
        uid_config_valid=uid_config_valid,
    ):
        return False

    normalized_uid = normalize_chief_owner_uid(uid)
    if persisted_uid is not None:
        normalized_persisted_uid = normalize_chief_owner_uid(persisted_uid)
        return bool(normalized_persisted_uid) and (
            normalized_uid == normalized_persisted_uid
        )

    return bool(uid_configured)


class PersistedChiefOwnerIdentityError(ValueError):
    """Raised when an existing ownership record is malformed or conflicts."""


def validate_persisted_chief_owner_record(
    owner_record,
    configured_email=None,
):
    """Validate ownership data, allowing legacy UID-only records."""
    if owner_record is None:
        return None
    if not isinstance(owner_record, dict):
        raise PersistedChiefOwnerIdentityError(
            "Persisted Chief Owner identity is malformed."
        )

    if "chiefOwnerUid" not in owner_record:
        raise PersistedChiefOwnerIdentityError(
            "Persisted Chief Owner UID is missing."
        )

    uid = normalize_chief_owner_uid(owner_record.get("chiefOwnerUid"))
    if not uid:
        raise PersistedChiefOwnerIdentityError(
            "Persisted Chief Owner UID is invalid."
        )

    if "chiefOwnerEmail" in owner_record:
        expected_email = normalize_chief_owner_email(
            CHIEF_OWNER_EMAIL if configured_email is None else configured_email
        )
        persisted_email = normalize_chief_owner_email(
            owner_record.get("chiefOwnerEmail")
        )
        if not expected_email or persisted_email != expected_email:
            raise PersistedChiefOwnerIdentityError(
                "Persisted Chief Owner email conflicts with configuration."
            )

    return uid


def read_persisted_chief_owner_uid(database, configured_email=None):
    if database is None:
        raise RuntimeError("Persisted Chief Owner identity is unavailable.")
    snapshot = (
        database.collection("systemSettings")
        .document("ownership")
        .get()
    )
    if not snapshot.exists:
        return None

    return validate_persisted_chief_owner_record(
        snapshot.to_dict(),
        configured_email=configured_email,
    )


CHIEF_OWNER_EMAIL = resolve_chief_owner_email()
(
    CHIEF_OWNER_UID,
    CHIEF_OWNER_UID_CONFIGURED,
    CHIEF_OWNER_UID_CONFIG_VALID,
) = resolve_chief_owner_uid()
