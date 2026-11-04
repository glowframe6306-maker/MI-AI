# Architecture

## Production Request Path

The checked-in Vercel configuration declares:

1. `/` and other non-API paths serve the root `index.html`.
2. `/api/*` routes to `api/index.py`, which imports and exports the Flask
   application from `backend.app`.
3. Static assets are served from configured static paths such as `public/`
   and `vendor/`.

The repository also contains `frontend/index.html` and a separate root
`app.py`. They are not the entry points selected by the current
`vercel.json`; keep this distinction in mind when validating or changing the
production path.

## Components

- **Browser UI:** Large HTML/CSS/vanilla-JavaScript pages, locale JSON files
  (`en`, `si`, `ta`), and browser-side Firebase SDK integration.
- **API runtime:** Python 3.13-compatible Flask application, exposed to Vercel
  through `api/index.py`.
- **Authentication and data:** Firebase client SDK and Firebase Admin
  integration, with Firestore persistence and `firestore.rules`.
- **AI and integrations:** Groq chat/model API; source also includes Tavily
  search, AI Horde image-generation, SMTP, and Supabase integration paths.
- **Deployment:** Vercel Python/static builds and route configuration in
  `vercel.json`.

The source contains both Firebase and Supabase account/data paths. Their
respective production use and readiness were not verified during inspection.
The deployment configuration and source should be treated as authoritative
over older reports and backup snapshots.

## Main API Areas

The Flask source defines routes for chat and streaming, conversation/message
persistence, authentication, account settings and memory, customer-service
requests, sharing/direct messages, image generation/search, live assistance,
and administration/RBAC. Route presence is not proof that each integration is
configured or functioning in production.

## Source Layout

- `api/`: Vercel Python entry point.
- `backend/`: Flask application, AI/search helpers, RBAC and tests.
- `frontend/`, root `index.html`, and root `app.py`: current and legacy/alternate
  UI/backend sources; verify the configured entry point before editing.
- `public/`, `vendor/`, `assets/`, `locales/`: static assets and translations.
- `tests/`, `scripts/`: browser-DOM smoke test and inline-JavaScript validator.
- Root also contains dated backups, diagnostic reports, and implementation
  reports; these are not the active deployment path.
