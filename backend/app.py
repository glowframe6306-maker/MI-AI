import html
import hashlib
import json
import os
import re
import shutil
import tempfile
import traceback
import sys
import uuid
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from pprint import pprint

BACKEND_DIR = Path(__file__).resolve().parent
ENV_FILE = BACKEND_DIR / ".env"

try:
    from google import genai
    print("[BOOT] google-genai imported successfully")
    try:
        try:
            import importlib.metadata as importlib_metadata
            gg_version = importlib_metadata.version("google-genai")
        except Exception:
            try:
                import pkg_resources
                gg_version = pkg_resources.get_distribution("google-genai").version
            except Exception:
                gg_version = "unknown"
        print(f"[BOOT] Python executable: {sys.executable}")
        print(f"[BOOT] google-genai version: {gg_version}")
        print("[BOOT] Gemini SDK loaded successfully")
    except Exception:
        print("[BOOT] Could not determine google-genai version")
except Exception as import_error:
    print(f"[BOOT] Failed to import google-genai: {import_error}")
    import traceback as tb
    tb.print_exc()
    genai = None


def debug_gemini_direct():
    from dotenv import load_dotenv

    load_dotenv(dotenv_path=ENV_FILE, override=False)
    api_key = clean_env_value(os.getenv("GEMINI_API_KEY", ""))
    model = clean_env_value(os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))

    print("=== Direct Gemini environment ===")
    print("GEMINI_API_KEY length:", len(api_key))
    print("GEMINI_MODEL:", model)

    if not api_key or genai is None:
        print("Gemini client unavailable")
        return

    client = genai.Client(api_key=api_key)
    try:
        response = client.models.generate_content(
            model=model,
            contents="Say hello in one short sentence.",
        )
        print("=== Gemini generate_content ===")
        print(getattr(response, "text", ""))
    except Exception as exc:
        print("Gemini request failed")
        traceback.print_exc()
        print("status_code:", getattr(exc, "status_code", None))
        print("body:", getattr(exc, "body", None))


from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv


def _safe_console_text(value) -> str:
    if value is None:
        return ""
    text = str(value)
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        return text.encode(encoding, errors="replace").decode(encoding, errors="replace")
    except Exception:
        return text.encode("utf-8", errors="replace").decode("utf-8", errors="replace")


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


def _load_environment() -> list[str]:
    if ENV_FILE.exists():
        load_dotenv(dotenv_path=ENV_FILE, override=False)
        return [str(ENV_FILE)]
    return []


_load_environment()

try:
    import PyPDF2
except Exception:
    PyPDF2 = None

try:
    from docx import Document as DocxDocument
except Exception:
    DocxDocument = None

try:
    import pandas as pd
except Exception:
    pd = None

try:
    from pptx import Presentation
except Exception:
    Presentation = None

try:
    from PIL import Image
except Exception:
    Image = None

try:
    import pytesseract
except Exception:
    pytesseract = None

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

gemini_client = None
gemini_client_api_key = None


def _read_env_file_value(key: str):
    if not ENV_FILE.exists():
        return None
    try:
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if not line or line.strip().startswith("#"):
                continue
            parts = line.split("=", 1)
            if len(parts) != 2:
                continue
            name = parts[0].strip()
            if name == key:
                return clean_env_value(parts[1])
    except Exception:
        return None
    return None


def _get_gemini_api_key():
    """Read the Gemini API key from backend/.env or environment variables."""
    _load_environment()
    file_key = _read_env_file_value("GEMINI_API_KEY")
    if file_key:
        return file_key

    for env_name in ["GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GENAI_API_KEY"]:
        value = clean_env_value(os.getenv(env_name, ""))
        if value:
            return value
    return ""


def _get_gemini_model():
    _load_environment()
    file_model = _read_env_file_value("GEMINI_MODEL")
    if file_model:
        return file_model

    for env_name in ["GEMINI_MODEL", "GOOGLE_GEMINI_MODEL", "GOOGLE_API_MODEL", "MODEL"]:
        model = clean_env_value(os.getenv(env_name, ""))
        if model:
            return model
    return "gemini-2.5-flash"


def _get_available_models(client):
    """Fetch list of available models that support generateContent."""
    if client is None:
        print("Client is None, cannot fetch models")
        return []

    try:
        print("Fetching available models from Gemini API...")
        models = client.models.list()
        if models is None:
            print("Model list returned None")
            return []

        available = []
        for model in models:
            model_name = getattr(model, 'name', None) or str(model)
            model_id = model_name.replace('models/', '').strip()
            if not model_id:
                continue

            model_lower = model_id.lower()
            if any(tag in model_lower for tag in ['preview', 'tts', 'exp', 'beta', 'alpha']):
                continue

            supported_actions = getattr(model, 'supported_actions', None)
            if supported_actions is None:
                print(f"  Skipping {model_id} because supported_actions is unknown")
                continue

            if 'generateContent' in supported_actions:
                available.append(model_id)
                print(f"  {model_id}")

        print(f"Total models supporting generateContent: {len(available)}")
        return available
    except Exception as e:
        print(f"Error fetching models: {e}")
        traceback.print_exc()
        return []


def _select_best_model(client, requested_model=None):
    """Select the best available model, with priority order."""
    priority_models = ["gemini-2.5-flash"]
    if requested_model:
        requested_model = requested_model.replace('models/', '').strip()
        if requested_model and requested_model not in priority_models:
            priority_models.insert(0, requested_model)

    available_models = _get_available_models(client)

    if not available_models:
        print("Warning: Could not fetch available models from API")
        fallback = [m for m in priority_models if m != requested_model]
        return requested_model or "gemini-2.5-flash", fallback

    print(f"\nAvailable models: {available_models}")
    print(f"Priority order: {priority_models}")

    for model in priority_models:
        if model in available_models:
            fallback = [m for m in available_models if m != model]
            print(f"Selected model: {model}")
            print(f"Fallback models: {fallback}")
            return model, fallback

    selected = available_models[0]
    fallback = available_models[1:]
    print(f"No priority model available, using first available: {selected}")
    print(f"Selected model: {selected}")
    print(f"Fallback models: {fallback}")
    return selected, fallback


def _format_gemini_error_message(exc):
    """Format Gemini exception into user-friendly error message."""
    error_str = str(exc).lower()
    if "429" in str(exc) or "resource_exhausted" in error_str or "quota" in error_str or "rate_limit" in error_str:
        return "The Gemini service is temporarily unavailable because of quota or rate limits. Your free tier quota has been exceeded. Please wait a few hours or upgrade your plan."
    if "401" in str(exc) or "403" in str(exc):
        if "access_token_type_unsupported" in error_str or "expected oauth" in error_str or "oauth 2" in error_str:
            return "The Gemini authentication credential is not a supported API key type. Please verify GEMINI_API_KEY is a valid Gemini API key."
        return "The Gemini API key is invalid or not authorized. Please verify the key and permissions."
    if "invalid" in error_str or "authentication" in error_str:
        return "The Gemini API key is invalid or not authorized. Please verify the key and permissions."
    if "404" in str(exc) or "not_found" in error_str or "model_not_found" in error_str:
        return "The requested Gemini model is not available. Please try a supported model."
    if "500" in str(exc) or "503" in str(exc) or "server_error" in error_str or "internal_error" in error_str:
        return "The Gemini service is temporarily unavailable. Please try again shortly."
    exc_message = str(exc)
    if len(exc_message) < 200:
        return exc_message
    return "An error occurred with the Gemini service. Please try again."


def _get_gemini_client():
    global gemini_client, gemini_client_api_key
    _load_environment()
    api_key = _get_gemini_api_key()
    if not api_key or genai is None:
        gemini_client = None
        gemini_client_api_key = None
        return None

    if gemini_client is not None and gemini_client_api_key == api_key:
        return gemini_client

    try:
        print("=== Gemini environment ===")
        print("GEMINI_API_KEY length:", len(api_key))
        print("GEMINI_MODEL:", _get_gemini_model())
        print("Environment:", os.getcwd())
        gemini_client = genai.Client(api_key=api_key)
        gemini_client_api_key = api_key
        print("=== Gemini client initialized ===")
    except Exception as exc:
        gemini_client = None
        gemini_client_api_key = None
        print("Gemini client initialization failed")
        traceback.print_exc()
        print("Gemini init error:", exc)

    return gemini_client


def _build_gemini_contents(messages_payload):
    contents = []
    print(f"\n=== Building Gemini contents ===")
    print(f"Input messages: {len(messages_payload)}")
    for i, message in enumerate(messages_payload):
        role = (message.get("role") or "").lower()
        content = message.get("content", "") or ""
        print(f"Message {i}: role={role}, content_len={len(content)}")
        if not content:
            print(f"  -> Skipping empty content")
            continue
        if role == "system":
            mapped_role = "user"
            text = f"System instruction: {content}"
            print(f"  -> Mapped system to {mapped_role}")
            contents.append({"role": mapped_role, "parts": [{"text": text}]})
        elif role == "assistant":
            mapped_role = "model"
            text = content
            print(f"  -> Mapped assistant to {mapped_role}")
            contents.append({"role": mapped_role, "parts": [{"text": text}]})
        elif role in {"user", "model"}:
            print(f"  -> Using role as-is: {role}")
            contents.append({"role": role, "parts": [{"text": content}]})
        else:
            mapped_role = "user"
            print(f"  -> Mapped unknown role {role} to {mapped_role}")
            contents.append({"role": mapped_role, "parts": [{"text": content}]})
    print(f"Final contents: {len(contents)} items")
    return contents


def _generate_gemini_content(client, contents, model_name=None, config=None):
    if client is None:
        raise RuntimeError("Gemini client is not available")

    requested_model = (model_name or _get_gemini_model()).strip()
    selected_model = requested_model.replace("models/", "").strip()

    fallback_models = [
    "gemini-3.1-flash-lite",
    ]

    print("\n=== Gemini content generation ===")
    print(f"Requested model: {requested_model}")
    print(f"Selected model: {selected_model}")
    print(f"Fallback models: {fallback_models}")
    print(f"Contents: {len(contents)} messages")
    print(f"Config: {config}")

    fallback_models_to_try = [selected_model]

    last_error = None
    for candidate_model in fallback_models_to_try:
        try:
            print(f"\n>>> Trying model: {candidate_model}")
            response = client.models.generate_content(
                model=candidate_model,
                contents=contents,
                config=config,
            )
            print(f"<<< Model {candidate_model} succeeded")
            print(f"Response type: {type(response)}")
            print(f"Response attributes: {dir(response)}")
            return response
        except Exception as exc:
            last_error = exc
            status_code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
            body = getattr(exc, "body", None)
            error_message = str(exc)
            print(f"!!! Model {candidate_model} failed")
            print(f"Exception type: {type(exc).__name__}")
            print(f"Status code: {status_code}")
            print(f"Error message: {error_message}")
            print(f"Body: {body}")
            if isinstance(body, dict):
                error = body.get("error") or body
                code = (error.get("code") if isinstance(error, dict) else None) or ""
                error_type = (error.get("type") if isinstance(error, dict) else None) or ""
                message = (error.get("message") if isinstance(error, dict) else None) or ""
            else:
                code = ""
                error_type = ""
                message = ""
            is_quota_error = (
                status_code in {429, 500, 503} or
                code in {"resource_exhausted", "quota_exceeded", "rate_limit_exceeded", "insufficient_quota"} or
                error_type in {"resource_exhausted", "quota_exceeded", "rate_limit_exceeded", "insufficient_quota"} or
                "quota" in error_message.lower() or
                "rate_limit" in error_message.lower() or
                "resource_exhausted" in error_message.lower()
            )
            print(f"Is retryable (quota/rate limit): {is_quota_error}")
            if not is_quota_error:
                print("Non-retryable error, raising")
                raise
            if candidate_model == fallback_models_to_try[-1]:
                print("Last model in list, raising")
                raise
            print("Retrying with next model...")

    if last_error is not None:
        raise last_error
    raise RuntimeError("Gemini content generation failed")


SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

IS_VERCEL = bool(os.getenv("VERCEL"))

if IS_VERCEL:
    RUNTIME_DATA_DIR = Path(tempfile.gettempdir()) / "mi-ai"
else:
    RUNTIME_DATA_DIR = BACKEND_DIR

RUNTIME_DATA_DIR.mkdir(parents=True, exist_ok=True)

LOCAL_PERSISTENCE_FILE = RUNTIME_DATA_DIR / "local_persistence.json"

UPLOAD_DIR = RUNTIME_DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
FRONTEND_INDEX = FRONTEND_DIR / "index.html"


def _load_local_store():
    if LOCAL_PERSISTENCE_FILE.exists():
        try:
            return json.loads(LOCAL_PERSISTENCE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {"conversations": [], "messages": []}
    return {"conversations": [], "messages": []}


def _save_local_store(store):
    LOCAL_PERSISTENCE_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    LOCAL_PERSISTENCE_FILE.write_text(
        json.dumps(store, indent=2),
        encoding="utf-8",
    )


def _safe_file_name(name):
    safe = re.sub(r'[^A-Za-z0-9._-]+', '_', (name or 'upload').strip())
    return safe or 'upload'


def _allowed_file_type(filename, content_type):
    allowed_exts = {'.pdf', '.docx', '.doc', '.txt', '.xlsx', '.xls', '.csv', '.pptx', '.ppt', '.png', '.jpg', '.jpeg', '.webp'}
    allowed_mimes = {
        'application/pdf',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/msword',
        'text/plain',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'application/vnd.ms-excel',
        'text/csv',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.presentationml.presentation',
        'application/vnd.ms-powerpoint',
        'image/png',
        'image/jpeg',
        'image/webp',
    }
    ext = Path(filename or '').suffix.lower()
    return ext in allowed_exts and (not content_type or content_type in allowed_mimes or ext in {'.png', '.jpg', '.jpeg', '.webp'})


def _needs_live_web_search(text):
    if not text:
        return False
    lowered = text.lower()
    patterns = [
        r"\b(latest|current|today|now|live|breaking|recent|this week|this month|upcoming|tonight|weather|news|stock|price|forecast|schedule|result|score|release|latest news|what['’]?s happening|who won|what time|what day|when does|where is|how much is)\b",
        r"\b(what['’]?s the latest|what['’]?s happening|recent updates|up to date|today['’]?s|current status)\b",
        r"\b(search|find|look up|google|online|internet|official website|official docs|documentation|github|youtube|image|video|pdf|research|map|maps|restaurant|hotel|hospital|bank|mosque|temple|school|product|price|cheapest|compare|best product|buy|flight|hotel|shop|shopping|location|address)\b"
    ]
    return any(re.search(pattern, lowered) for pattern in patterns)


def _classify_search_intent(text):
    lowered = (text or "").lower()
    if any(keyword in lowered for keyword in ["image", "picture", "photo", "images", "show me a picture", "show me", "kaputa"]):
        return "images"
    if any(keyword in lowered for keyword in ["video", "tutorial", "interview", "documentary", "song", "gameplay", "movie trailer", "youtube"]):
        return "videos"
    if any(keyword in lowered for keyword in ["pdf", "research paper", "manual", "documentation", "user guide", "guide", "doc"]):
        return "documents"
    if any(keyword in lowered for keyword in ["price", "buy", "cheapest", "compare", "best product", "product", "shopping", "shop"]):
        return "shopping"
    if any(keyword in lowered for keyword in ["restaurant", "hotel", "hospital", "bank", "police", "mosque", "temple", "school", "nearest", "map", "maps", "location", "address"]):
        return "maps"
    if any(keyword in lowered for keyword in ["news", "latest", "breaking", "current events", "today", "tonight", "recent"]):
        return "news"
    if any(keyword in lowered for keyword in ["github", "npm", "pypi", "firebase", "supabase", "cloudflare", "vercel", "mdn", "stackoverflow", "official docs", "official website"]):
        return "developer"
    return "web"


def _fetch_web_search_results(query, limit=4):
    if not query:
        return []
    encoded_query = urllib.parse.quote(query)
    search_url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
    request = urllib.request.Request(
        search_url,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            html_text = response.read().decode("utf-8", "ignore")
    except Exception:
        return []

    results = []
    for match in re.finditer(r'<a rel="nofollow" class="result__a" href="(.*?)"(.*?)>(.*?)</a>', html_text, flags=re.S):
        href = html.unescape(match.group(1) or "")
        title = re.sub(r"<.*?\>", "", match.group(3) or "")
        title = html.unescape(re.sub(r"\s+", " ", title)).strip()
        if href and title:
            results.append({"title": title, "url": href})
        if len(results) >= limit:
            break
    return results


def _build_search_links(query, intent):
    encoded_query = urllib.parse.quote(query)
    if intent == "images":
        return [
            f"https://www.google.com/search?tbm=isch&q={encoded_query}",
            f"https://duckduckgo.com/?q={encoded_query}&iax=images&ia=images",
        ]
    if intent == "videos":
        return [
            f"https://www.youtube.com/results?search_query={encoded_query}",
            f"https://www.google.com/search?tbm=vid&q={encoded_query}",
        ]
    if intent == "maps":
        return [
            f"https://www.google.com/maps/search/{encoded_query}",
            f"https://www.google.com/search?q={encoded_query}+map",
        ]
    if intent == "news":
        return [
            f"https://news.google.com/search?q={encoded_query}",
            f"https://www.google.com/search?q={encoded_query}+news",
        ]
    if intent == "documents":
        return [
            f"https://www.google.com/search?q={encoded_query}+pdf",
            f"https://www.google.com/search?q={encoded_query}+documentation",
        ]
    if intent == "shopping":
        return [
            f"https://www.google.com/search?q={encoded_query}+price+official+store",
            f"https://www.google.com/search?q={encoded_query}+buy",
        ]
    if intent == "developer":
        return [
            f"https://www.google.com/search?q={encoded_query}+official+documentation",
            f"https://www.google.com/search?q={encoded_query}+github",
        ]
    return [
        f"https://www.google.com/search?q={encoded_query}",
        f"https://duckduckgo.com/?q={encoded_query}",
        f"https://en.wikipedia.org/wiki/Special:Search?search={encoded_query}",
    ]


def _build_live_search_context(user_message):
    if not _needs_live_web_search(user_message):
        return ""
    q = (user_message or "").strip()
    if not q:
        return ""
    results = _fetch_web_search_results(q, limit=4)
    if not results:
        return ""
    sections = []
    for idx, item in enumerate(results, 1):
        sections.append(f"{idx}. {item['title']} - {item['url']}")
    return "Live search results:\n" + "\n".join(sections)


def _build_real_time_context(user_message):
    return ""


def _get_session_id():
    payload = request.get_json(silent=True) or {}
    if isinstance(payload, dict) and payload.get("session_id"):
        return str(payload.get("session_id"))
    return request.args.get("session_id") or request.headers.get("X-Session-Id") or request.headers.get("X-User-Id") or "anonymous"


def _get_user_email():
    payload = request.get_json(silent=True) or {}
    if isinstance(payload, dict) and payload.get("user_email"):
        return str(payload.get("user_email"))
    return request.headers.get("X-User-Email") or request.headers.get("X-Email") or request.args.get("user_email") or ""


def _get_user_id():
    payload = request.get_json(silent=True) or {}
    if isinstance(payload, dict) and payload.get("user_id"):
        return str(payload.get("user_id"))
    return request.headers.get("X-User-Id") or request.args.get("user_id") or ""


def _get_user_scope():
    return {
        "user_id": _get_user_id(),
        "user_email": _get_user_email(),
        "session_id": _get_session_id(),
    }


def _get_chat_debug_context():
    return {
        "gemini_key_present": bool(_get_gemini_api_key()),
        "gemini_model": _get_gemini_model(),
        "provider": "gemini",
        "chat_route": "/chat",
    }


def _request_supabase(method, path, payload=None, params=None):
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be configured")

    url = f"{SUPABASE_URL}/rest/v1{path}"
    if params:
        separator = '&' if '?' in url else '?'
        query = urllib.parse.urlencode(params, doseq=True)
        url = f"{url}{separator}{query}"

    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }

    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            body = response.read().decode("utf-8")
            if not body:
                return []
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                return body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        raise RuntimeError(f"Supabase request failed: {exc.code} {body}") from exc


@app.route("/")
def home():
    if FRONTEND_INDEX.exists():
        return send_from_directory(str(FRONTEND_DIR), "index.html")
    return "MI AI Running 🚀"


@app.route("/debug/chat", methods=["GET"])
def debug_chat():
    env_file_exists = ENV_FILE.exists()
    key_value = _get_gemini_api_key()
    model_value = _get_gemini_model()
    file_value = _read_env_file_value("GEMINI_API_KEY") if env_file_exists else ""
    if file_value and file_value == key_value:
        key_source = "backend/.env"
    elif file_value and key_value and file_value != key_value:
        key_source = "backend/.env and process environment differ"
    elif key_value:
        key_source = "process environment"
    else:
        key_source = "none"

    return jsonify({
        "message": "python-backend",
        "provider": "gemini",
        "chat_route": "/chat",
        "gemini_key_present": bool(key_value),
        "gemini_key_length": len(key_value),
        "gemini_key_fingerprint": secret_fingerprint(key_value),
        "gemini_model": model_value,
        "env_file_exists": env_file_exists,
        "env_file_path": str(ENV_FILE) if env_file_exists else None,
        "key_source": key_source,
    })


@app.route("/api/conversations", methods=["GET", "POST"])
def conversations():
    session_id = _get_session_id()
    scope = _get_user_scope()

    if request.method == "GET":
        try:
            params = {"order": "created_at.desc"}
            if scope.get("user_id"):
                params["user_id"] = f"eq.{scope['user_id']}"
            elif session_id and session_id != "anonymous":
                params["session_id"] = f"eq.{session_id}"
            rows = _request_supabase("GET", "/conversations", params=params)
            conversations_list = []
            for row in rows or []:
                conversations_list.append({
                    "id": row.get("id"),
                    "title": row.get("title", "New chat"),
                    "created_at": row.get("created_at"),
                    "updated_at": row.get("updated_at") or row.get("created_at"),
                    "message_count": row.get("message_count") or 0,
                    "last_preview": row.get("last_preview") or "",
                })
            return jsonify({"conversations": conversations_list})
        except Exception as exc:
            store = _load_local_store()
            return jsonify({"conversations": store.get("conversations", []), "warning": str(exc)})

    payload = request.get_json(silent=True) or {}
    title = payload.get("title", "New chat")
    session_id = payload.get("session_id") or session_id or "anonymous"
    user_email = scope.get("user_email") or ""
    user_id = scope.get("user_id") or session_id

    try:
        row = _request_supabase("POST", "/conversations", payload={
            "title": title,
            "session_id": session_id,
            "user_id": user_id,
            "user_email": user_email,
        })
        if isinstance(row, list) and row:
            row = row[0]
        return jsonify({"conversation": row})
    except Exception as exc:
        store = _load_local_store()
        conversation = {
            "id": f"chat_{len(store.get('conversations', [])) + 1}",
            "title": title,
            "session_id": session_id,
            "user_id": user_id,
            "user_email": user_email,
        }
        store.setdefault("conversations", []).append(conversation)
        _save_local_store(store)
        return jsonify({"conversation": conversation, "warning": str(exc)})


@app.route("/api/conversations/<conversation_id>", methods=["PATCH", "DELETE"])
def conversation_detail(conversation_id):
    scope = _get_user_scope()
    user_id = scope.get("user_id")
    session_id = scope.get("session_id")

    if not user_id and session_id == "anonymous":
        return jsonify({"error": "Authentication required"}), 401

    try:
        existing_rows = _request_supabase("GET", f"/conversations?id=eq.{conversation_id}", params={"select": "id,user_id,session_id"})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    existing = (existing_rows or [{}])[0]
    if not existing:
        return jsonify({"error": "Conversation not found"}), 404

    if user_id and existing.get("user_id") and existing.get("user_id") != user_id:
        return jsonify({"error": "Forbidden"}), 403

    if request.method == "PATCH":
        payload = request.get_json(silent=True) or {}
        try:
            _request_supabase("PATCH", f"/conversations?id=eq.{conversation_id}", payload=payload)
            return jsonify({"ok": True})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    try:
        _request_supabase("DELETE", f"/conversations?id=eq.{conversation_id}")
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(str(UPLOAD_DIR), filename)

@app.route("/api/upload", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        return jsonify({
            "error": "No file uploaded"
        }), 400

    file = request.files["file"]

    if file.filename == "":
        return jsonify({
            "error": "No selected file"
        }), 400

    if not _allowed_file_type(file.filename, file.mimetype):
        return jsonify({
            "error": "File type not allowed"
        }), 400

    safe_name = _safe_file_name(file.filename)

    UPLOAD_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    destination = UPLOAD_DIR / safe_name
    file.save(destination)

    return jsonify({
        "ok": True,
        "filename": safe_name,
    })


@app.route("/api/conversations/<conversation_id>/attachments", methods=["GET"])
def conversation_attachments(conversation_id):
    return jsonify({
        "conversation_id": conversation_id,
        "attachments": [],
    })

@app.route("/api/messages", methods=["GET", "POST"])
def messages():
    if request.method == "GET":
        store = _load_local_store()
        return jsonify({"messages": store.get("messages", [])})

    payload = request.get_json(silent=True) or {}
    conversation_id = payload.get("conversation_id") or ""
    role = payload.get("role") or "ai"
    content = payload.get("content") or ""
    store = _load_local_store()
    store.setdefault("messages", []).append({
        "conversation_id": conversation_id,
        "role": role,
        "content": content,
    })
    _save_local_store(store)
    return jsonify({"ok": True})


@app.route("/api/messages/<message_id>", methods=["PATCH"])
def message_detail(message_id):
    return jsonify({"ok": True, "message_id": message_id})


def _extract_text_from_gemini_response(response):
    if response is None:
        return ""

    text = getattr(response, "text", None)
    if text:
        return text

    candidates = getattr(response, "candidates", None) or []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        parts = getattr(content, "parts", None) or []
        for part in parts:
            part_text = getattr(part, "text", None)
            if part_text:
                return part_text

    return str(response)


def _handle_chat_request():
    payload = request.get_json(silent=True) or {}
    user_message = str(payload.get("message") or payload.get("input") or payload.get("prompt") or "").strip()
    if not user_message:
        return jsonify({"response": "Please type a message.", "reply": "Please type a message."})

    history = payload.get("history") or payload.get("messages") or []
    if not isinstance(history, list):
        history = []

    normalized_messages = []
    for item in history:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "user").strip() or "user"
        content = item.get("content") or item.get("text") or ""
        if content:
            normalized_messages.append({"role": role, "content": str(content)})

    normalized_messages.append({"role": "user", "content": user_message})

    try:
        client = _get_gemini_client()
        if client is None:
            message = "The AI service is not configured. Please set a valid GEMINI_API_KEY or GOOGLE_API_KEY in Vercel."
            print("[CHAT] Missing Gemini client:", message)
            return jsonify({"response": message, "reply": message}), 503

        contents = _build_gemini_contents(normalized_messages)
        response = _generate_gemini_content(client, contents, model_name=_get_gemini_model())
        reply = _extract_text_from_gemini_response(response).strip() or "No response received from Gemini."
        return jsonify({"response": reply, "reply": reply})
    except Exception as exc:
        traceback.print_exc()
        status_code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
        body = getattr(exc, "body", None)
        error_message = _format_gemini_error_message(exc) or "The AI service is unavailable right now. Please try again."

        # Build sanitized provider details
        sanitized_details = None
        if isinstance(body, dict):
            error_obj = body.get("error") or body
            if isinstance(error_obj, dict):
                sanitized_details = error_obj.get("message") or str(error_obj)
            else:
                sanitized_details = str(error_obj)
        else:
            sanitized_details = str(body) if body is not None else str(exc)

        error_code = None
        if status_code in {400}:
            error_code = "GEMINI_BAD_REQUEST"
        elif status_code in {401, 403}:
            error_code = "GEMINI_AUTH_FAILED"
        elif status_code == 404:
            error_code = "GEMINI_MODEL_NOT_FOUND"
        elif status_code == 429:
            error_code = "GEMINI_RATE_LIMIT"
        else:
            error_code = "GEMINI_SERVICE_ERROR"

        print("[CHAT] Request failed:", exc)
        user_facing_error = "Gemini request failed."
        if error_code == "GEMINI_AUTH_FAILED":
            user_facing_error = "Gemini authentication failed."

        return jsonify({
            "response": user_facing_error,
            "reply": user_facing_error,
            "error": user_facing_error,
            "error_code": error_code,
            "details": sanitized_details,
            "status_code": status_code,
        }), 500


@app.route("/chat", methods=["POST"])
def chat():
    return _handle_chat_request()


@app.route("/api/chat", methods=["POST"])
def api_chat():
    return _handle_chat_request()


@app.route("/api/chat", methods=["GET"])
def api_chat_get():
    return jsonify({"response": "Method not allowed"}), 405


if __name__=="__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )