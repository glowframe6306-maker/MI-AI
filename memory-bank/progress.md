# Progress

**What works**

- Added a Vercel-compatible Python entrypoint at [api/index.py](api/index.py) and routed all requests through it.
- Verified the backend exposes chat and conversation routes required by the frontend.
- Added a regression test for the /api/chat route in [backend/tests/test_api_routes.py](backend/tests/test_api_routes.py).

**Not started / backlog**

- Complete the live Vercel redeploy and confirm runtime chat responses after setting environment variables.

**Known issues**

- The live deployment still needs real GROQ environment variables configured in Vercel for successful chat responses.

_Keep bullets factual and small; link issues or PRs when useful._
