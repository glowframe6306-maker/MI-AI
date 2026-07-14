# Active context

**Current focus** (one short paragraph):

The Flask backend now uses the Groq SDK for chat requests and loads local environment values automatically so the live chat path can activate in both local development and Vercel.

**In progress**:

- [x] Verify that the Flask app exposes the required chat and conversation routes for deployment.
- [x] Add regression coverage for the Groq-backed chat path.
- [ ] Confirm the live Vercel deployment with GROQ_API_KEY and GROQ_MODEL values set in the Vercel dashboard.

**Decisions (recent)**:

- The production entrypoint remains [api/index.py](api/index.py), and Vercel routes all traffic through it.
- The backend chat path now uses the Groq SDK through the shared helper functions in [backend/app.py](backend/app.py).

**Open questions**:

- The live Vercel deployment still needs the real GROQ_API_KEY, GROQ_MODEL, and GROQ_FALLBACK_MODEL values configured in Vercel for runtime chat responses.

_Update when the task or branch focus changes._
