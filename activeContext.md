# Active context

**Current focus**: Finalizing the repaired auth and chat flow across the static frontend and the Next.js API routes.

**In progress**:

- [x] Repaired the frontend auth handlers and chat history persistence for signed-in users.
- [x] Aligned the API requests with the existing /api/conversations, /api/messages, and /chat routes.
- [x] Verified the route source files are compiling correctly after the API signature fix.

**Decisions (recent)**:

- The frontend now uses bearer-authenticated requests for conversation and message persistence once a Firebase session token is present.
- Missing Supabase credentials return clear JSON errors instead of falling through to 404 or HTML responses.

**Open questions**:

- Whether the deployment environment will provide Supabase credentials for full registration/sign-in functionality.

_Update when the task or branch focus changes._
