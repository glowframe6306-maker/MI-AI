# MI-AI Project Context

## Product

- Company: MI CORTEX X INC.
- Product: CORTEX CORE AI
- Public website: <https://mi-ai-assistant-of-mi.vercel.app/>
- Repository: <https://github.com/glowframe6306-maker/MI-AI>
- Local source root: `C:\Users\Administrator\MI-AI`

The public website is the product reference. Source changes do not update the
live site; production deployment requires explicit authorization.

## Current Repository Snapshot

- Inspected branch: `main`
- Inspected commit: `57cf614a4eda80e1367395587a74bb0b431cc606`
- Working tree at inspection: clean; branch tracked `origin/main`
- No deployment, database, external-service, or environment changes were made.
- The live site rendered a CORTEX CORE AI chat shell with New Chat, Customer
  Service, Login, and a message composer. A browser `pageError` event was also
  observed, but its details were not available in the page snapshot.

## Development Boundaries

- Never disclose environment-file contents, credentials, or tokens.
- Do not deploy, migrate or write production data, or alter external service
  settings without explicit authorization.
- Do not claim source changes are live unless a deployment has been authorized
  and verified.
- Preserve unrelated and uncommitted user work.

## Next Priorities

See [DEVELOPMENT_ROADMAP.md](./DEVELOPMENT_ROADMAP.md). The immediate technical
priority is to establish a safe, repeatable backend validation workflow and
document which runtime configuration is required, without reading or changing
secret values.
