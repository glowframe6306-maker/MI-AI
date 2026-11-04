# Development Roadmap

Priorities below are based on source inspection only. Production behavior,
configuration, and data were not examined beyond loading the public homepage.

## 1. Make Backend Validation Safe and Repeatable

- Review the Python tests before execution. One existing test writes and
  restores `backend/.env`; do not run it in a workflow that could overwrite
  existing user data.
- Separate environment-loading tests from repository files using isolated
  temporary paths and ensure restoration is reliable.
- Add focused coverage for Firebase authorization, conversation ownership,
  provider failures, and streaming errors.
- Keep validation offline and avoid production writes.

## 2. Establish Runtime Readiness Without Disclosing Secrets

- Document required environment-variable names and which service consumes
  each; never document values.
- Add safe health checks or operational guidance that reports readiness
  without returning exception details or secret material.
- Verify service availability only with explicit authorization and safe,
  read-only methods.

## 3. Clarify and Reduce Duplicate Runtime Paths

- Determine whether root `app.py` and `frontend/index.html` are still needed.
- Identify their unique behavior and tests before consolidating or removing
  anything.
- Keep changes limited to the configured Vercel entry points unless a verified
  requirement calls for another path.

## 4. Validate User-Facing Flows

- Exercise login, chat, streaming, history, settings, and memory with test
  accounts and non-production data.
- Add coverage for English, Sinhala, and Tamil UI behavior.
- Investigate the browser `pageError` observed during the homepage inspection
  using a reproducible error report.

## 5. Production Verification

- Use the public website for read-only behavioral checks when available.
- Do not deploy, migrate, write production data, or change external settings
  without explicit authorization.
- Report source validation and live deployment status separately.
