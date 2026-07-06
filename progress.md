# Progress

**What works**

- The Next.js app exposes the deployment routes for auth, chat, conversations, messages, and Supabase config.
- The frontend now initializes auth, loads chat history, and persists new messages through the signed-in user flow.
- The API route files now compile without the earlier TypeScript signature error.

**Not started / backlog**

- Full Supabase-backed sign-in and registration require valid environment variables in the deployment platform.

**Known issues**

- If Supabase credentials are not configured in Vercel, the app will return clear JSON error responses instead of failing with 404 or HTML responses.

_Keep bullets factual and small; link issues or PRs when useful._
