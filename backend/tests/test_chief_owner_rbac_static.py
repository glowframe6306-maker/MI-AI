from pathlib import Path
import ast
import re
from importlib import import_module, reload

import pytest

ROOT = Path(__file__).resolve().parents[2]
RBAC = ROOT / "backend" / "chief_owner_rbac.py"
APP = ROOT / "backend" / "app.py"
INDEX = ROOT / "frontend" / "index.html"


def read(path):
    return path.read_text(encoding="utf-8")


def test_rbac_python_syntax():
    ast.parse(read(RBAC))


def test_chief_owner_email_configuration_is_shared():
    identity = import_module("backend.chief_owner_identity")
    app = import_module("backend.app")
    control = import_module("backend.chief_owner_control")
    rbac = import_module("backend.chief_owner_rbac")

    assert app.CHIEF_OWNER_EMAIL == identity.CHIEF_OWNER_EMAIL
    assert app.MI_CHIEF_OWNER_EMAIL == identity.CHIEF_OWNER_EMAIL
    assert app.MI_AI_CHIEF_OWNER_EMAIL == identity.CHIEF_OWNER_EMAIL
    assert control.CHIEF_OWNER_EMAIL == identity.CHIEF_OWNER_EMAIL
    assert rbac.CHIEF_OWNER_EMAIL == identity.CHIEF_OWNER_EMAIL
    assert rbac.CHIEF_OWNER_UID == app.CHIEF_OWNER_UID
    assert app.CHIEF_OWNER_UID == control.CHIEF_OWNER_UID
    assert app.CHIEF_OWNER_UID == app.MI_AI_CHIEF_OWNER_UID
    assert app.CHIEF_OWNER_UID_CONFIGURED == control.CHIEF_OWNER_UID_CONFIGURED
    assert app.CHIEF_OWNER_UID_CONFIGURED == rbac.CHIEF_OWNER_UID_CONFIGURED
    assert app.CHIEF_OWNER_UID_CONFIG_VALID == control.CHIEF_OWNER_UID_CONFIG_VALID
    assert app.CHIEF_OWNER_UID_CONFIG_VALID == rbac.CHIEF_OWNER_UID_CONFIG_VALID


def test_chief_owner_uid_configuration_resolves_and_fails_closed():
    identity = import_module("backend.chief_owner_identity")

    assert identity.resolve_chief_owner_uid({}) == ("", False, True)
    assert identity.resolve_chief_owner_uid({
        "CHIEF_OWNER_UID": " owner-uid ",
    }) == ("owner-uid", True, True)
    for invalid_uid in ("", "   ", "owner uid", "x" * 129, "owner\nuid"):
        assert identity.resolve_chief_owner_uid({
            "CHIEF_OWNER_UID": invalid_uid,
        }) == ("", True, False)


@pytest.mark.parametrize(
    "invalid_uid",
    [
        "\x00owner",
        "owner\x1f",
        "owner\x7f",
        "owner\u0080",
        "owner\u0085",
        "owner\u009f",
    ],
)
def test_chief_owner_uid_rejects_ascii_and_unicode_control_characters(
    invalid_uid,
):
    identity = import_module("backend.chief_owner_identity")

    assert identity.normalize_chief_owner_uid(invalid_uid) == ""


def test_chief_owner_uid_preserves_trimming_and_valid_values():
    identity = import_module("backend.chief_owner_identity")

    assert identity.normalize_chief_owner_uid("  owner-uid  ") == "owner-uid"
    assert identity.normalize_chief_owner_uid("owner uid") == ""
    assert identity.normalize_chief_owner_uid("") == ""
    assert identity.normalize_chief_owner_uid("x" * 129) == ""
    assert identity.normalize_chief_owner_uid("firebase-owner-123") == (
        "firebase-owner-123"
    )
    assert identity.normalize_chief_owner_uid("uid-é-用户") == "uid-é-用户"


def test_persisted_owner_identity_validation_supports_legacy_email_omission():
    identity = import_module("backend.chief_owner_identity")

    assert identity.validate_persisted_chief_owner_record(
        {
            "chiefOwnerUid": "owner-uid",
            "chiefOwnerEmail": " Owner@Example.com ",
        },
        configured_email="owner@example.com",
    ) == "owner-uid"
    assert identity.validate_persisted_chief_owner_record(
        {"chiefOwnerUid": "owner-uid"},
        configured_email="owner@example.com",
    ) == "owner-uid"


@pytest.mark.parametrize(
    "owner_record",
    [
        {"chiefOwnerUid": "owner-uid", "chiefOwnerEmail": "admin@example.com"},
        {"chiefOwnerUid": "owner-uid", "chiefOwnerEmail": ""},
        {"chiefOwnerUid": "owner-uid", "chiefOwnerEmail": "invalid"},
        {"chiefOwnerEmail": "owner@example.com"},
        {"chiefOwnerUid": ""},
        {"chiefOwnerUid": "owner uid"},
        [],
    ],
)
def test_malformed_persisted_owner_identity_fails_closed(owner_record):
    identity = import_module("backend.chief_owner_identity")

    with pytest.raises(
        identity.PersistedChiefOwnerIdentityError,
    ):
        identity.validate_persisted_chief_owner_record(
            owner_record,
            configured_email="owner@example.com",
        )


def test_chief_owner_uid_is_captured_from_environment(monkeypatch):
    identity = import_module("backend.chief_owner_identity")
    monkeypatch.setenv("CHIEF_OWNER_UID", "loaded-test-uid")

    try:
        reload(identity)
        assert identity.CHIEF_OWNER_UID == "loaded-test-uid"
        assert identity.CHIEF_OWNER_UID_CONFIGURED is True
        assert identity.CHIEF_OWNER_UID_CONFIG_VALID is True
    finally:
        monkeypatch.undo()
        reload(identity)


def test_shared_owner_identity_policy_requires_config_or_persisted_uid():
    identity = import_module("backend.chief_owner_identity")

    def is_owner(email, uid, persisted_uid, environment):
        configured_uid, configured, valid = identity.resolve_chief_owner_uid(
            environment
        )
        return identity.is_chief_owner_identity(
            email,
            uid,
            persisted_uid=persisted_uid,
            email_verified=True,
            configured_email="owner@example.com",
            configured_uid=configured_uid,
            uid_configured=configured,
            uid_config_valid=valid,
        )

    configured = {"CHIEF_OWNER_UID": "owner-uid"}
    assert is_owner("owner@example.com", "owner-uid", None, configured)
    assert not is_owner("owner@example.com", "admin-uid", None, configured)
    assert not is_owner("admin@example.com", "owner-uid", None, configured)
    assert not is_owner("owner@example.com", "", None, configured)

    assert not is_owner("owner@example.com", "owner-uid", None, {})
    assert is_owner(
        "owner@example.com",
        "owner-uid",
        "owner-uid",
        {},
    )
    assert not is_owner(
        "owner@example.com",
        "admin-uid",
        "owner-uid",
        {},
    )

    for invalid_uid in ("", "  ", "owner uid", "x" * 129):
        assert not is_owner(
            "owner@example.com",
            "owner-uid",
            "owner-uid",
            {"CHIEF_OWNER_UID": invalid_uid},
        )


def test_dotenv_loading_precedes_identity_module_imports():
    source = read(APP)
    configuration_block = source.index("# Resolve configuration")
    env_path_loop = source.index(
        "for env_path in _candidate_env_paths():",
        configuration_block,
    )
    env_refresh = source.index("_refresh_local_env()", env_path_loop)
    for import_line in (
        "from backend.chief_owner_identity import",
        "from backend.chief_owner_rbac import",
        "from backend.chief_owner_control import",
    ):
        assert env_refresh < source.index(import_line)


def test_chief_owner_email_override_normalizes_and_fails_closed(monkeypatch):
    identity = import_module("backend.chief_owner_identity")

    monkeypatch.setenv("CHIEF_OWNER_EMAIL", "  Owner@Example.COM  ")
    monkeypatch.setenv("MI_CHIEF_OWNER_EMAIL", "ignored@example.com")
    assert identity.resolve_chief_owner_email() == "owner@example.com"

    for invalid_email in ("", "not-an-email", "owner@@example.com"):
        monkeypatch.setenv("CHIEF_OWNER_EMAIL", invalid_email)
        assert identity.resolve_chief_owner_email() == ""

    monkeypatch.delenv("CHIEF_OWNER_EMAIL", raising=False)
    monkeypatch.setenv("MI_CHIEF_OWNER_EMAIL", "  Legacy@Example.COM ")
    assert identity.resolve_chief_owner_email() == "legacy@example.com"

    monkeypatch.delenv("MI_CHIEF_OWNER_EMAIL", raising=False)
    assert identity.resolve_chief_owner_email() == ""


def test_unconfigured_owner_checks_fail_closed(monkeypatch):
    app = import_module("backend.app")
    control = import_module("backend.chief_owner_control")
    rbac = import_module("backend.chief_owner_rbac")

    monkeypatch.setattr(app, "CHIEF_OWNER_EMAIL", "")
    monkeypatch.setattr(app, "MI_CHIEF_OWNER_EMAIL", "")
    monkeypatch.setattr(app, "MI_AI_CHIEF_OWNER_EMAIL", "")
    monkeypatch.setattr(control, "CHIEF_OWNER_EMAIL", "")
    monkeypatch.setattr(rbac, "CHIEF_OWNER_EMAIL", "")

    assert not app.is_configured_chief_owner("owner@example.com", "owner-uid")
    assert not app._mi_owner_access_from_token({
        "email": "",
        "uid": "owner-uid",
    })["isChiefOwner"]
    assert not app.mi_ai_is_chief_owner({
        "email": "",
        "uid": "owner-uid",
    })
    assert not control.is_chief_owner({
        "email": "owner@example.com",
        "uid": "owner-uid",
        "email_verified": True,
    })
    with pytest.raises(rbac.AuthorizationError, match="identity mismatch"):
        rbac._ensure_chief_owner({"uid": "admin-uid", "email": ""})


def test_chief_owner_uid_checks_remain_required(monkeypatch):
    from types import SimpleNamespace

    app = import_module("backend.app")
    control = import_module("backend.chief_owner_control")
    rbac = import_module("backend.chief_owner_rbac")
    monkeypatch.setattr(app, "CHIEF_OWNER_EMAIL", "owner@example.com")
    monkeypatch.setattr(app, "CHIEF_OWNER_UID", "owner-uid")
    monkeypatch.setattr(control, "CHIEF_OWNER_EMAIL", "owner@example.com")
    monkeypatch.setattr(control, "CHIEF_OWNER_UID", "owner-uid")
    monkeypatch.setattr(rbac, "CHIEF_OWNER_EMAIL", "owner@example.com")
    monkeypatch.setattr(rbac, "CHIEF_OWNER_UID", "owner-uid")
    monkeypatch.setattr(app, "CHIEF_OWNER_UID_CONFIGURED", True)
    monkeypatch.setattr(app, "CHIEF_OWNER_UID_CONFIG_VALID", True)
    monkeypatch.setattr(control, "CHIEF_OWNER_UID_CONFIGURED", True)
    monkeypatch.setattr(control, "CHIEF_OWNER_UID_CONFIG_VALID", True)
    monkeypatch.setattr(rbac, "CHIEF_OWNER_UID_CONFIGURED", True)
    monkeypatch.setattr(rbac, "CHIEF_OWNER_UID_CONFIG_VALID", True)

    assert app.is_configured_chief_owner(
        "owner@example.com", "owner-uid", email_verified=True
    )
    assert not app.is_configured_chief_owner(
        "owner@example.com", "admin-uid", email_verified=True
    )
    assert control.is_chief_owner({
        "email": "owner@example.com",
        "uid": "owner-uid",
        "email_verified": True,
    })
    assert not control.is_chief_owner({
        "email": "owner@example.com",
        "uid": "admin-uid",
        "email_verified": True,
    })

    monkeypatch.setattr(rbac, "_firebase_ready", lambda: None)
    monkeypatch.setattr(
        rbac,
        "auth",
        SimpleNamespace(
            verify_id_token=lambda *args, **kwargs: {
                "uid": "admin-uid",
                "email": "owner@example.com",
                "email_verified": True,
            }
        ),
    )
    monkeypatch.setattr(
        rbac,
        "db",
        lambda: pytest.fail("UID mismatch must be rejected before database access."),
    )
    with app.app.test_request_context(
        headers={"Authorization": "Bearer test-id-token"}
    ):
        with pytest.raises(rbac.AuthorizationError, match="identity mismatch"):
            rbac.load_actor()


def test_ordinary_admin_cannot_use_chief_owner_staff_record(monkeypatch):
    from types import SimpleNamespace

    rbac = import_module("backend.chief_owner_rbac")
    monkeypatch.setattr(rbac, "CHIEF_OWNER_EMAIL", "owner@example.com")
    monkeypatch.setattr(rbac, "_firebase_ready", lambda: None)
    monkeypatch.setattr(
        rbac,
        "auth",
        SimpleNamespace(
            verify_id_token=lambda *args, **kwargs: {
                "uid": "admin-uid",
                "email": "admin@example.com",
            }
        ),
    )
    monkeypatch.setattr(
        rbac,
        "_load_staff_record",
        lambda uid: {
            "uid": uid,
            "email": "admin@example.com",
            "role": "chief_owner",
            "status": "active",
        },
    )

    app = import_module("backend.app")
    with app.app.test_request_context(
        headers={"Authorization": "Bearer test-id-token"}
    ):
        with pytest.raises(rbac.AuthorizationError, match="identity mismatch"):
            rbac.load_actor()


def test_frontend_role_is_not_authoritative():
    source = read(RBAC)
    assert "verify_id_token" in source
    assert "_load_staff_record" in source
    assert "effective_permissions" in source


def test_chief_owner_is_protected():
    source = read(RBAC)
    for token in [
        "chief_owner_protected",
        "ownership_transfer_required",
        "A different protected Chief Owner UID is already configured",
    ]:
        assert token in source


def test_lower_roles_cannot_grant_higher_roles():
    source = read(RBAC)
    assert "role_rank(actor[\"role\"]) >= role_rank(requested_role)" in source
    assert "You cannot grant this role." in source


def test_permission_grant_is_bounded():
    source = read(RBAC)
    assert "custom_permissions.issubset(actor[\"permissions\"])" in source
    assert "High-risk permissions require Chief Owner approval." in source


def test_role_actions_are_audited():
    source = read(RBAC)
    assert source.count("create_audit_log(") >= 5
    assert '"staff.role_assigned"' in source
    assert '"staff.removed"' in source


def test_staff_status_revokes_tokens():
    source = read(RBAC)
    assert "auth.revoke_refresh_tokens(target_uid)" in source


def test_blueprint_is_registered():
    source = read(APP)
    assert "MI_AI_SECURE_RBAC_IMPORT" in source
    assert "MI_AI_SECURE_RBAC_REGISTER" in source
    assert "register_rbac(app)" in source


def test_owner_ui_is_present():
    source = read(INDEX)
    assert "MI_AI_CHIEF_OWNER_RBAC_START" in source
    assert "Chief Owner Permissions" in source
    assert "/api/rbac/staff/assign" in source


def test_owner_visibility_requires_authoritative_backend_status():
    source = read(INDEX)
    rescue_start = source.index("CORTEX CORE AI CHIEF OWNER BUTTON RESCUE START")
    rescue_end = source.index("CORTEX CORE AI OWNER LOADING FIX END", rescue_start)
    rescue_script = source[rescue_start:rescue_end]
    assert "emailMatch" not in rescue_script
    assert "email === OWNER_EMAIL" not in rescue_script
    assert "showOwnerOverlayImmediately" not in rescue_script
    assert "miOwnerFallbackMetadata" not in rescue_script
    assert "window.__miOwnerUiVisibility" in rescue_script
    assert "requestId !== visibilityState.requestId" in rescue_script
    assert "data.authenticated === true" in rescue_script
    assert "data.isChiefOwner === true" in rescue_script
    assert '"/api/admin/me"' in source


def test_no_plaintext_password_field_in_staff_flow():
    source = read(INDEX).lower()
    block = source[source.index("mi_ai_chief_owner_rbac_start"):source.index("mi_ai_chief_owner_rbac_end")]
    assert 'type="password"' not in block
    assert "create password" not in block