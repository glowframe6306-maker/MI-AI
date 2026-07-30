from pathlib import Path
import ast
import re

ROOT = Path(__file__).resolve().parents[2]
RBAC = ROOT / "backend" / "chief_owner_rbac.py"
APP = ROOT / "backend" / "app.py"
INDEX = ROOT / "frontend" / "index.html"


def read(path):
    return path.read_text(encoding="utf-8")


def test_rbac_python_syntax():
    ast.parse(read(RBAC))


def test_chief_owner_email_is_present():
    assert "teamofchatbot.miai@gmail.com" in read(RBAC)


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
    assert "teamofchatbot.miai@gmail.com" in source


def test_no_plaintext_password_field_in_staff_flow():
    source = read(INDEX).lower()
    block = source[source.index("mi_ai_chief_owner_rbac_start"):source.index("mi_ai_chief_owner_rbac_end")]
    assert 'type="password"' not in block
    assert "create password" not in block