# Feature Status

Status distinguishes code observed in the repository from behavior verified
on the deployed website. A route or UI implementation alone does not establish
production readiness.

| Area | Source evidence | Verification status |
|---|---|---|
| Chat UI | Root `index.html`; composer and New Chat controls | Homepage shell observed; chat request not submitted |
| Chat generation | Flask `/api/chat` and Groq client/model selection in `backend/app.py` | Not exercised against production |
| Streaming | Flask `/api/chat/stream` | Route and stream implementation present; not exercised against production |
| Chat history | Firebase/Firestore conversation and message routes | Source implementation present; authenticated persistence not tested |
| Authentication | Browser Firebase SDK and Flask Firebase Admin verification | Source implementation present; sign-in not tested |
| Account settings and memory | Flask settings/memory routes | Source implementation present; not tested |
| Search/research | Tavily/search helper paths | Source integration present; credentials and live behavior not verified |
| Image features | AI Horde generation and image-search routes | Source integration present; not tested |
| Sharing and account messaging | Share-link, notification, and direct-message routes | Source implementation present; not tested |
| Administration | RBAC modules and admin routes; static RBAC tests | Source and static test coverage present; live authorization not tested |
| Localization | `locales/` and `frontend/locales/` contain English, Sinhala, and Tamil JSON | Files present; end-to-end language behavior not tested |
| Voice/live assistance | Live-assist routes and frontend code paths | Source paths present; provider availability and behavior not tested |

## Known Incompleteness

- Production AI, Firebase, Supabase, search, email, and image-service
  readiness was not established.
- The repository has parallel root and `frontend/` UI/backend sources. Vercel
  currently selects the root UI and `backend.app` API path.
- Automated coverage is limited relative to the number of integrations and
  route groups.
- The public browser snapshot showed the initial chat shell only; it did not
  establish logged-in, streaming, persistence, or advanced-feature behavior.
