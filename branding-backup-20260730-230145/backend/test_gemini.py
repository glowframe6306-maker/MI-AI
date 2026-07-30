from google import genai
import hashlib
import os
from pathlib import Path
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent
ENV_FILE = BACKEND_DIR / ".env"

load_dotenv(dotenv_path=ENV_FILE, override=False)


def clean_env_value(value):
    if value is None:
        return ""
    value = str(value).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1].strip()
    if value.startswith("GEMINI_API_KEY="):
        value = value.split("=", 1)[1].strip()
    return value


def secret_fingerprint(value):
    if not value:
        return None
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return digest[:8]


API_KEY = clean_env_value(os.getenv("GEMINI_API_KEY"))
MODEL = clean_env_value(os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))

print("Using backend/.env:", ENV_FILE.exists())
print("GEMINI_API_KEY present:", bool(API_KEY))
print("GEMINI_API_KEY length:", len(API_KEY))
print("GEMINI_API_KEY fingerprint:", secret_fingerprint(API_KEY))
print("GEMINI_MODEL:", MODEL)

if not API_KEY:
    print("No GEMINI_API_KEY found in environment. Set GEMINI_API_KEY to run this test.")
    raise SystemExit(1)

client = genai.Client(api_key=API_KEY)

try:
    response = client.models.generate_content(
        model=MODEL,
        contents="Reply with exactly: MI AI OK"
    )

    print("=" * 50)
    print("SUCCESS")
    print("=" * 50)
    text = getattr(response, 'text', '')
    print(f"Response length: {len(text)}")
    print(f"Response text: {text}")

except Exception as exc:
    import traceback

    status_code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    body = getattr(exc, "body", None)
    message = str(exc)

    sanitized_error = {
        "message": None,
        "code": None,
        "status": None,
    }
    if isinstance(body, dict):
        error_obj = body.get("error") or body
        if isinstance(error_obj, dict):
            sanitized_error["message"] = error_obj.get("message")
            sanitized_error["code"] = error_obj.get("code")
            sanitized_error["status"] = error_obj.get("status")
        else:
            sanitized_error["message"] = str(error_obj)
    else:
        sanitized_error["message"] = str(body) if body is not None else message

    print("=" * 50)
    print("ERROR")
    print("=" * 50)
    print("Exception type:", type(exc).__name__)
    print("Status code:", status_code)
    print("Error message:", message)
    print("Sanitized body:", sanitized_error)
    traceback.print_exc()
