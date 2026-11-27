import io
from importlib import import_module

import requests
import pytest


@pytest.fixture
def report_context(monkeypatch):
    app_module = import_module("backend.app")
    sent_requests = []
    saved_records = []

    def send(url, *, data, files=None, timeout):
        sent_requests.append(
            {
                "url": url,
                "data": data,
                "files": files,
                "timeout": timeout,
            }
        )
        return TelegramResponse()

    monkeypatch.setattr(
        app_module,
        "customer_service_identity",
        lambda: (
            {
                "uid": "verified-user-id",
                "email": "user@example.com",
                "username": "verified-user",
                "display_name": "Verified User",
            },
            None,
        ),
    )
    monkeypatch.setattr(app_module, "CUSTOMER_SERVICE_BOT", "test-token")
    monkeypatch.setattr(app_module, "CUSTOMER_SERVICE_CHAT_ID", "test-chat-id")
    monkeypatch.setattr(app_module.requests, "post", send)
    monkeypatch.setattr(
        app_module,
        "customer_service_save",
        lambda kind, reference, record: saved_records.append(
            (kind, reference, record)
        ),
    )
    return app_module, sent_requests, saved_records


class TelegramResponse:
    status_code = 200

    def __init__(self, payload=None, status_code=200):
        self.payload = payload or {"ok": True, "result": {"message_id": 1}}
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError("Telegram API rejected the request.")

    def json(self):
        return self.payload


def report_form(**overrides):
    values = {
        "name": "Example User",
        "whatsapp": "+94771234567",
        "reason": "Technical Issue",
        "description": "The chat page does not load.",
    }
    values.update(overrides)
    return values


def submit_report(app_module, data=None):
    return app_module.app.test_client().post(
        "/api/customer-service/reports",
        data=data if data is not None else report_form(),
        headers={"Authorization": "Bearer verified-test-token"},
    )


def test_valid_report_is_sent_to_telegram_before_success(report_context):
    app_module, sent_requests, saved_records = report_context

    response = submit_report(app_module)

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["notification_status"] == "sent"
    assert payload["reference"].startswith("CCA-RP-")
    assert len(sent_requests) == 1
    assert sent_requests[0]["data"]["chat_id"] == "test-chat-id"
    assert sent_requests[0]["data"]["parse_mode"] == "HTML"
    assert "verified-user-id" in sent_requests[0]["data"]["text"]
    assert "The chat page does not load." in sent_requests[0]["data"]["text"]
    assert saved_records[0][1] == payload["reference"]


@pytest.mark.parametrize(
    "missing_variable",
    ["CUSTOMER_SERVICE_BOT", "CUSTOMER_SERVICE_CHAT_ID"],
)
def test_missing_telegram_configuration_fails_without_sending(
    report_context, monkeypatch, missing_variable
):
    app_module, sent_requests, _ = report_context
    constant = (
        "CUSTOMER_SERVICE_BOT"
        if missing_variable == "CUSTOMER_SERVICE_BOT"
        else "CUSTOMER_SERVICE_CHAT_ID"
    )
    monkeypatch.setattr(app_module, constant, "")

    response = submit_report(app_module)

    assert response.status_code == 503
    assert response.get_json()["success"] is False
    assert sent_requests == []


@pytest.mark.parametrize(
    "response",
    [
        TelegramResponse({"ok": False, "error_code": 401}, 200),
        TelegramResponse({"ok": False, "error_code": 400}, 200),
    ],
)
def test_telegram_rejection_never_returns_success(
    report_context, monkeypatch, response
):
    app_module, sent_requests, saved_records = report_context
    monkeypatch.setattr(app_module.requests, "post", lambda *args, **kwargs: response)

    result = submit_report(app_module)

    assert result.status_code == 503
    assert result.get_json()["success"] is False
    assert saved_records == []


def test_telegram_http_failure_never_returns_success(report_context, monkeypatch):
    app_module, _, saved_records = report_context
    failed_response = TelegramResponse(status_code=500)
    monkeypatch.setattr(
        app_module.requests, "post", lambda *args, **kwargs: failed_response
    )

    response = submit_report(app_module)

    assert response.status_code == 503
    assert response.get_json()["success"] is False
    assert saved_records == []


def test_telegram_timeout_never_returns_success(report_context, monkeypatch):
    app_module, _, _ = report_context

    def timeout(*args, **kwargs):
        raise requests.Timeout("private request details")

    monkeypatch.setattr(app_module.requests, "post", timeout)

    response = submit_report(app_module)

    assert response.status_code == 503
    assert response.get_json()["success"] is False
    assert "private request details" not in response.get_data(as_text=True)


@pytest.mark.parametrize("description", ["", "   ", "\n\t "])
def test_empty_description_is_rejected_without_telegram(
    report_context, description
):
    app_module, sent_requests, _ = report_context

    response = submit_report(
        app_module, report_form(description=description)
    )

    assert response.status_code == 400
    assert sent_requests == []


def test_report_html_escapes_user_content(report_context):
    app_module, sent_requests, _ = report_context
    description = "<script>alert('x')</script> & more"

    response = submit_report(
        app_module, report_form(description=description)
    )

    assert response.status_code == 200
    rendered = sent_requests[0]["data"]["text"]
    assert "&lt;script&gt;" in rendered
    assert "&amp; more" in rendered
    assert "<script>" not in rendered


def test_long_description_is_delivered_in_complete_html_messages(report_context):
    app_module, sent_requests, _ = report_context
    description = ("Long report & <details>. " * 400).strip()

    response = submit_report(
        app_module, report_form(description=description)
    )

    assert response.status_code == 200
    assert len(sent_requests) > 1
    assert all(
        request["data"]["parse_mode"] == "HTML"
        and len(request["data"]["text"]) <= 4096
        for request in sent_requests
    )
    joined = "\n".join(request["data"]["text"] for request in sent_requests)
    assert joined.count("Long report") > 1
    assert "&lt;details&gt;" in joined
    assert len(sent_requests) == len(
        [
            request
            for request in sent_requests
            if request["data"]["chat_id"] == "test-chat-id"
        ]
    )


def test_attachment_is_sent_only_after_report_message(report_context):
    app_module, sent_requests, _ = report_context
    data = report_form()
    data["attachment"] = (io.BytesIO(b"test attachment"), "issue <log>.txt")

    response = submit_report(app_module, data)

    assert response.status_code == 200
    assert len(sent_requests) == 2
    assert sent_requests[0]["data"]["parse_mode"] == "HTML"
    assert sent_requests[1]["files"]["document"][0] == "issue-log-.txt"
    assert sent_requests[1]["url"].endswith("/sendDocument")


def test_report_delivery_does_not_depend_on_firestore(report_context, monkeypatch):
    app_module, sent_requests, _ = report_context

    def firestore_unavailable(*args, **kwargs):
        raise RuntimeError("Firestore unavailable")

    monkeypatch.setattr(app_module, "customer_service_save", firestore_unavailable)

    response = submit_report(app_module)

    assert response.status_code == 200
    assert response.get_json()["notification_status"] == "sent"
    assert sent_requests


def test_report_requires_existing_verified_authentication():
    app_module = import_module("backend.app")
    response = app_module.app.test_client().post(
        "/api/customer-service/reports",
        data=report_form(),
    )

    assert response.status_code == 401
    assert response.get_json()["success"] is False


def test_oversized_description_is_rejected_without_telegram(report_context):
    app_module, sent_requests, _ = report_context

    response = submit_report(
        app_module,
        report_form(description="x" * 20001),
    )

    assert response.status_code == 400
    assert sent_requests == []


def test_report_frontend_prevents_duplicates_and_requires_delivery_confirmation():
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[2] / "index.html"
    ).read_text(encoding="utf-8")
    submit_start = source.index("const submit = async form =>", source.index("/* CUSTOMER SUPPORT */"))
    submit_end = source.index('box.addEventListener("click"', submit_start)
    submit_handler = source[submit_start:submit_end]

    assert 'box.dataset.submitting === "true"' in submit_handler
    assert 'payload.notification_status !== "sent"' in submit_handler
    assert "REPORT SUBMIT RESPONSE:" not in submit_handler
