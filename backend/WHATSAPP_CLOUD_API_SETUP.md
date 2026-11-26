# WhatsApp Business Cloud API Setup

This backend endpoint is `/api/whatsapp/webhook`. It verifies Meta webhook signatures, routes supported inbound text messages to the existing CORTEX CORE AI chat handler, maintains bounded Firestore-backed context per customer and receiving business number, and sends replies through the matching Cloud API phone-number ID. It also validates and records summary-only metadata for four coexistence webhook fields; it does not implement Embedded Signup or display synchronized customer history.

## Number Eligibility

Meta distinguishes consumer WhatsApp accounts from WhatsApp Business Platform senders:

- **Numbers 1 and 2 (standard consumer WhatsApp accounts):** They cannot connect directly to the Cloud API as consumer accounts. A number already registered in either WhatsApp app generally must first be removed from WhatsApp before standard Cloud API registration. This can disconnect the existing account. Do not start that process without explicit approval; this project has not changed either number.
- **Number 3 (WhatsApp Business):** If this means an existing WhatsApp Business App number, coexistence with Cloud API may be possible through Meta Embedded Signup, but it is not an automatic/direct connection. Meta's current prerequisites include WhatsApp Business App version 2.24.17 or newer, an eligible Solution Partner or Tech Provider implementation, Embedded Signup session logging, Cloud API knowledge, and a webhook that can process required onboarding events. Meta's Embedded Signup v2/v3 deprecation date was October 15, 2026; use a currently supported version (v4 or newer). This backend now parses the four coexistence webhook fields into summary metadata, but it does not implement the Embedded Signup handoff, session logging, history/contact synchronization APIs, or customer-facing history display, so it is not by itself a complete coexistence onboarding solution. Coexistence also has feature/device limitations. If the number is already a registered, connected WhatsApp Business Platform sender, it may be usable after its IDs and access token are authorized for this app.
- **Three-number account cap:** Meta says new business portfolios initially have a two-number cap. A third number may require the portfolio to become verified or meet Meta's stated messaging-limit threshold before Meta raises the cap. Confirm the current limit in WhatsApp Manager before onboarding.

The software can route three approved sender IDs, but that does not make all three account types eligible for Cloud API. Numbers 1 and 2 require separate eligible business sender numbers or explicit owner-approved removal from their current consumer WhatsApp registrations before standard Cloud API registration. Number 3 can use Cloud API if already connected as a Platform sender; keeping it active in the Business App requires Meta's eligible coexistence flow and additional implementation work described above. Eligibility of the actual numbers cannot be determined from this repository. Meta must confirm ownership, account state, country/number support, Business Portfolio status, and coexistence eligibility. No number has been registered, migrated, disconnected, or modified by this implementation.

## Meta App and Sender Setup

1. Register as a Meta developer, create or select a Meta app with the WhatsApp use case, and connect the appropriate Meta Business Portfolio and WhatsApp Business Account (Messaging account).
2. In WhatsApp API Setup or WhatsApp Manager, add each approved business sender and complete Meta's ownership verification and Cloud API registration. A sender must be connected and have a display name. An existing app number may need deletion/removal before standard registration; stop and obtain explicit approval before taking that action.
3. If Number 3 is to remain active in WhatsApp Business App, use Meta's supported WhatsApp Business App Embedded Signup/coexistence flow and verify all current eligibility and app limitations with Meta. The local webhook parses subscribed coexistence event fields into summaries, but this repository does not implement the Embedded Signup partner flow, session logging, history/contact synchronization APIs, or customer-facing history display. Complete those requirements before attempting onboarding. Do not use this path for Numbers 1 and 2, which are standard personal accounts.
4. Record the **phone_number_id** for every registered Cloud API sender. It is the API ID shown in Meta, not the visible phone number. Only add IDs you control and have authorization to message from.
5. After deploying the backend route, configure the Meta app's WhatsApp webhook callback as `https://mi-ai-assistant-of-mi.vercel.app/api/whatsapp/webhook`. Confirm the deployed URL no longer returns 404 before asking Meta to verify it. Set a private verify token in both Meta and the backend. In the Meta App Dashboard, open **WhatsApp > Configuration**, set the callback URL and verify token, then subscribe the app to `messages`. An eligible coexistence app must also subscribe to `account_update`, `history`, `smb_app_state_sync`, and `smb_message_echoes`; the callback must digest every subscribed field. The local code only processes coexistence events matching the configured WABA ID and designated sender phone-number ID.
6. Configure the Meta app secret and create a secure system-user access token authorized for every sender that this service will use. Each sender may map to a distinct token; a shared token is acceptable only if Meta has authorized it for all mapped senders.
7. Test each approved sender independently with Meta's test recipient flow before enabling customer traffic. Do not use live customer traffic as the first test.

## Backend Configuration

Set these in the backend runtime secret manager. For local-only testing they may be in `backend/.env`, which must not be committed. Never place values in source, frontend files, command history, logs, API responses, or chat messages.

| Variable | Description |
| --- | --- |
| `WHATSAPP_VERIFY_TOKEN` | Private string matched during Meta's GET webhook verification. |
| `WHATSAPP_APP_SECRET` | Meta app secret used only for POST signature validation. |
| `WHATSAPP_ID_HMAC_KEY` | Stable private identifier key (minimum 32 UTF-8 bytes) for HMAC-derived Firestore IDs. For the first deployment over existing data, initialize it to the exact current `WHATSAPP_APP_SECRET` value to preserve existing IDs; keep it unchanged afterward. |
| `WHATSAPP_SENDERS_JSON` | JSON object mapping each approved numeric `phone_number_id` to its authorized access token. |
| `WHATSAPP_AWAY_PHONE_NUMBER_ID` | The single approved WhatsApp Business sender controlled by manual AVAILABLE/AWAY mode. It must also appear in `WHATSAPP_SENDERS_JSON`. |
| `WHATSAPP_CONTEXT_LIMIT` | Maximum stored/context messages per conversation (even number, 2–50; default `20`). |
| `WHATSAPP_HISTORY_RETENTION_DAYS` | Inactivity retention period for conversation history (1–3650 days; default `30`). |
| `WHATSAPP_WABA_ID` | The WhatsApp Business Account / Messaging Account ID for the designated Business sender. Required to accept coexistence events; never infer it from a phone-number ID. |
| `WHATSAPP_GRAPH_API_VERSION` | A currently supported Meta Graph API version, formatted as `vNN.N`. |
| `META_APP_ID` | Public Meta app ID used by the JavaScript SDK; it is not an app secret. |
| `META_EMBEDDED_SIGNUP_CONFIG_ID` | Facebook Login for Business configuration ID for the WhatsApp Embedded Signup flow. |
| `META_EMBEDDED_SIGNUP_VERSION` | Supported Embedded Signup version. Meta currently lists v5 as latest; v4 remains listed. |
| `META_EMBEDDED_SIGNUP_ENABLED` | Explicit opt-in flag; unset/false is disabled. Setting it true does not enable launch in this codebase. |
| Existing AI configuration | The existing CORTEX CORE AI provider configuration (for example `GROQ_API_KEY`). |

Use placeholders only in configuration templates, for example:

```dotenv
WHATSAPP_VERIFY_TOKEN=<private-verify-token>
WHATSAPP_APP_SECRET=<meta-app-secret>
WHATSAPP_ID_HMAC_KEY=<stable-private-id-key>
WHATSAPP_GRAPH_API_VERSION=v27.0
WHATSAPP_AWAY_PHONE_NUMBER_ID=<BUSINESS_PHONE_NUMBER_ID_3>
WHATSAPP_WABA_ID=<WHATSAPP_BUSINESS_ACCOUNT_ID>
WHATSAPP_SENDERS_JSON={"<PHONE_NUMBER_ID_1>":"<ACCESS_TOKEN_1>","<PHONE_NUMBER_ID_2>":"<ACCESS_TOKEN_2>","<PHONE_NUMBER_ID_3>":"<ACCESS_TOKEN_3>"}
META_APP_ID=<META_APP_ID>
META_EMBEDDED_SIGNUP_CONFIG_ID=<FACEBOOK_LOGIN_FOR_BUSINESS_CONFIG_ID>
META_EMBEDDED_SIGNUP_VERSION=v5
META_EMBEDDED_SIGNUP_ENABLED=false
```

Replace the example version with one currently supported by Meta. Replace all placeholder IDs/tokens with real values only in the backend secret manager. The previous single-sender variables `WHATSAPP_PHONE_NUMBER_ID` and `WHATSAPP_ACCESS_TOKEN` remain supported for transition, but the JSON map takes precedence when present.

## Manual Business Availability

Set `WHATSAPP_AWAY_PHONE_NUMBER_ID` to Number 3's verified Cloud API phone-number ID only after confirming that it is the intended Business sender and that it is included in `WHATSAPP_SENDERS_JSON`. Do not set it to either personal number. If it is unset or not approved in the sender map, the owner panel reports manual mode as unconfigured; other senders retain their existing behavior.

Meta Business App coexistence has not been verified for this specific account. An authorized business representative (and an adult representative if required by Meta or applicable law) must confirm eligibility and complete any required onboarding. This implementation does not initiate Embedded Signup or alter/disconnect the existing Business App.

After the backend is configured, the authenticated Chief Owner opens the existing Chief Owner panel in CORTEX CORE AI and uses **WhatsApp Business Availability**:

- **AVAILABLE** prevents AI generation and replies for the designated sender. Incoming supported message IDs are marked handled using server-side Firestore receipts (without storing message content), so later retries do not become replies after a mode change.
- **AWAY** enables the existing CORTEX CORE AI response path for that sender. Replies still use the same incoming phone-number ID and its authorized token.
- The webhook checks the saved mode before AI generation and transactionally checks it again in the same Firestore transaction that changes the receipt to `sending`. A mode change committed before that transaction prevents sending; a change committed after authorization cannot cancel the in-flight Cloud API request.
- **Save mode** updates the setting immediately in the existing Firebase Admin Firestore store; it does not require a deployment or process restart. The mode value is stored in the `whatsappManualAvailability` collection, one document per designated sender, and changes are audited.
- The protected mode API and panel show a sanitized latest account lifecycle label (for example, `partner_added_unverified` or `reconnected_needs_review`). These labels are observations only and are not proof that the phone number is connected.
- The API is protected by the existing `require_chief_owner` authentication, which verifies the Firebase ID token and configured Chief Owner identity. Firestore rules deny client access to this collection; the browser can change mode only through the protected backend API. Changes are recorded in the existing audit log when that store is available.
- If no mode document exists, its value is invalid, or the backend cannot read Firestore, the webhook fails closed to **AVAILABLE**. The panel reports when the state cannot be verified. A failed save is not treated as a successful mode change; verify the displayed mode before relying on it.
- After a matching account-update event, the backend keeps automatic replies at **AVAILABLE** and rejects attempts to set **AWAY** until the Chief Owner explicitly confirms a review. The dashboard asks the owner to independently verify `is_on_biz_app=true` and `platform_type=CLOUD_API` in Meta and review the latest event. This is a human attestation, not a server-side Meta verification; the dashboard continues to label the connection unverified.
- This is a manual control. It does not detect whether the owner is online, active in WhatsApp, or available on a device.

This task adds the code and tests only. It does not set the sender ID, write a production Firestore document, change Meta settings, or deploy the control. Once deployed, an authorized Chief Owner mode change will write the Firestore mode document.

## Persistent Conversation Memory, Delivery Safety, and Privacy

Incoming text and assistant replies are stored in Firestore after a successful send. The existing CORTEX CORE AI handler, system prompt, business context, and provider configuration remain unchanged.

### Stable identifiers and migration

- Conversation, receipt, rate-limit, concurrency-slot, and customer-preference document IDs use domain-separated HMAC-SHA256 identifiers derived from `WHATSAPP_ID_HMAC_KEY`, not the Meta webhook-signature secret.
- **Existing-data compatibility:** before deploying this version against an existing Firestore database, set `WHATSAPP_ID_HMAC_KEY` to the exact current `WHATSAPP_APP_SECRET` value (after the same whitespace trimming) so the pre-existing conversation and receipt document IDs remain addressable. The identifier key must be at least 32 UTF-8 bytes. If the current app secret does not meet that minimum, stop and plan a reviewed data migration; do not deploy with a different key and assume old records will be found.
- This initial compatibility step deliberately reuses the old key material to preserve document IDs; the HMAC namespace prefixes separate identifier purposes but do not make the underlying key independent during that initial migration. After this compatibility initialization, keep `WHATSAPP_ID_HMAC_KEY` stable while rotating `WHATSAPP_APP_SECRET` independently. Changing the identifier key changes all derived IDs and can orphan conversation, receipt, rate-limit, and preference records or bypass deduplication. There is no online dual-key rotation tool. A future identifier-key rotation requires a separately reviewed migration/dual-read plan and must not be done as a routine secret rotation.
- Never print either secret or put it in source control, logs, command history, frontend code, or support messages.

### Storage and limits

- `whatsappConversationMemory` stores bounded chronological user/assistant turns and timestamps. Context defaults to 20 messages (even number, configurable 2–50). Conversation history defaults to 30 days of inactivity (configurable 1–3650 days).
- `whatsappMessageReceipts` stores delivery and processing metadata, not message content. Receipts have an eight-day `expiresAt`; Firestore TTL must be configured separately for background deletion. The actual production TTL state is **NOT VERIFIED**.
- `whatsappCustomerRateLimits` enforces a transactional rolling limit of 10 accepted AI-eligible messages per customer per receiving business sender in any 60-second window. Duplicate webhook delivery of the same message ID does not consume quota again. A message that later fails during AI processing still consumes its accepted-message quota for the remaining window. Legacy fixed-window counts are carried forward conservatively during the first transactional update. The limiter uses application timestamps; clock synchronization and real multi-instance contention must be validated in a non-production Firestore project.
- `whatsappAiConcurrencySlots` provides 10 shared AI-processing slots per receiving business sender. Processing leases are five minutes, AI-slot leases are ten minutes, and a heartbeat attempts renewal every 60 seconds. Renewal failure prevents the worker from authorizing a send. Serverless suspension, process termination, or a prolonged Firestore outage can still cause overlapping AI provider work; the final send authorization is token/lease checked transactionally and stale workers cannot send after losing their claim.
- `whatsappCustomerPreferences` stores a hashed customer preference record. `STOP`, `STOP ALL`, `UNSUBSCRIBE`, `CANCEL`, `END`, or `QUIT` disables automated replies for that customer. `START`, `UNSTOP`, or `SUBSCRIBE` re-enables them. A STOP request is stored without sending a confirmation reply; START also does not send a separate confirmation. Opt-out records do not expire while opted out; an explicit START command is required to clear the state.
- Raw customer identifiers are not used as Firestore document IDs. Conversation content itself is stored in Firestore and must be covered by the organization's privacy notice, lawful basis/consent process, access controls, retention policy, and deletion procedure. This code does not itself provide legal consent, a privacy notice, or a complete customer-data erasure workflow. Those operational requirements remain **NOT VERIFIED**.

### Delivery state and recovery

- The processing receipt is claimed transactionally before AI work. A duplicate event, an active processing lease, a rate-limited event, or a receipt with `sending`/`delivery_unknown` status is not sent again automatically.
- Immediately before sending, one Firestore transaction verifies the processing receipt, conversation lock, AI slot, and (for the designated sender) current AWAY/manual-review state, then changes the receipt to `sending`. A mode change committed before this transaction prevents sending. A mode change after this transaction commits cannot cancel the already-authorized HTTP request.
- A definite Graph API 4xx rejection is marked `failed` and may be retried on a later Meta webhook redelivery. A network exception, timeout, Graph API 5xx, or post-send persistence failure is ambiguous and is marked `delivery_unknown`; if Firestore cannot persist that state, it remains `sending`. Neither state is automatically resent.
- This is an at-most-once bias, not exactly-once delivery. A valid reply can be lost if a worker stops after recording `sending` but before Meta accepts the message. A stale `sending` receipt is intentionally not reopened because the original worker might resume and send. It remains blocked until receipt expiry/TTL or other separately approved data-recovery action.
- A stale `delivery_unknown` receipt may be reconciled only by a local operator after checking the final delivery status in Meta. The local command requires an explicit decision, operator identifier, a 15-minute grace period, and a confirmation prompt. It never sends a message. `delivered` becomes terminal but does not reconstruct the missing conversation-history turn; `not-delivered` becomes retryable only if Meta later redelivers the original webhook (otherwise the customer must send a new message). Never choose `not-delivered` while Meta delivery remains uncertain.
- Local command example (run from the project root after configuring the local backend environment):
  `flask --app backend.app whatsapp-reconcile-delivery <64-character-receipt-id> --decision delivered --operator <operator-id>`
  Use `--decision not-delivered` only with conclusive Meta evidence. The receipt ID is an HMAC-derived internal identifier, not a customer phone number.

### Firestore rules and retention

The WhatsApp collections are server-only and the current Firestore rules deny browser/client access. Firebase Admin SDK access bypasses Firestore client security rules, so production service-account IAM scope must be checked separately. TTL policies for `whatsappConversationMemory`, `whatsappMessageReceipts`, `whatsappCustomerRateLimits`, and `whatsappCustomerPreferences` are external configuration and have not been verified or changed by this source package. Opted-out preference documents have a null expiry and remain until START or a separately approved deletion. Do not run TTL or IAM changes without separate approval.


## Embedded Signup Readiness UI

The existing Chief Owner panel includes a read-only readiness card backed by `GET /api/chief-owner/whatsapp-embedded-signup/readiness`. The endpoint uses the existing Firebase Chief Owner authorization and returns setting names plus sanitized status labels for local sender/webhook configuration, Meta eligibility, signup state, subscription verification, connection verification, and token-storage readiness. It never returns app-secret/token values or sender/WABA identifiers. Meta webhook subscription status and eligibility remain `unknown` until verified through authorized Meta account access.

The displayed **Launch unavailable** button is deliberately disabled and has no handler. This repository does not load the Meta SDK, launch `FB.login`, receive a session callback, exchange authorization codes, or store returned business tokens. `META_EMBEDDED_SIGNUP_ENABLED=true` does not override this protection. The control will remain disabled until a separately approved implementation provides secure callback validation, server-to-server code exchange, and an approved token-storage mechanism.

Any later callback implementation must validate the exact Meta message origin and event type, strictly validate the v5/v4 session object and numeric asset IDs, bind the response to a short-lived one-time server-created state/nonce associated with the authenticated Chief Owner session where the flow supports it, and reject replay, expiry, mismatch, or partial data. None of these callback checks exist yet because no callback is accepted today.

No secure Meta business-token storage adapter exists. A future server-only adapter should expose narrowly scoped `store(phone_number_id, waba_id, token)`, `get(phone_number_id)`, and `delete(phone_number_id)` operations; enforce the existing Chief Owner/backend authorization boundary; encrypt tokens at rest when the approved existing infrastructure supports it; and never return or log token values. The code-exchange path must fail closed if this adapter is unavailable. No storage product, collection, or schema has been selected or written.

## Coexistence Event Readiness

The webhook validates the same `X-Hub-Signature-256` HMAC before dispatching any field. Coexistence events are accepted only when both the configured `WHATSAPP_WABA_ID` and designated `WHATSAPP_AWAY_PHONE_NUMBER_ID` match the event envelope and the phone-number ID is approved in `WHATSAPP_SENDERS_JSON`. If either ID is missing or does not match, the event is acknowledged as ignored; no connection state is inferred.

| Field | Local behavior |
| --- | --- |
| `account_update` | Recognizes the lifecycle events `PARTNER_ADDED`, `PARTNER_APP_INSTALLED`, `PARTNER_APP_UNINSTALLED`, `PARTNER_REMOVED`, `ACCOUNT_DELETED`, `ACCOUNT_OFFBOARDED`, `ACCOUNT_RECONNECTED`, `ACCOUNT_RESTRICTION`, `ACCOUNT_VIOLATION`, and `DISABLED_UPDATE`. Stores only the event enum, a conservative review/status label, and a validated Unix event timestamp. Every matching account-update event (including an unrecognized event name) forces mode to AVAILABLE and requires manual review; unknown names are stored only as `UNRECOGNIZED`. `PARTNER_ADDED`/`PARTNER_APP_INSTALLED` are recorded as unverified, not connected. |
| `history` | Validates batch phase/chunk/progress, message IDs and timestamps, counts threads/messages, and captures numeric error codes. Stores only aggregate sync metadata. Historical message bodies, customer identities, and message IDs are discarded and never passed to AI. A declined or partial sync is not reported as complete. |
| `smb_app_state_sync` | Validates the state-sync array and timestamp/action fields; stores aggregate add/remove/other counts only. Contact names, phone numbers, usernames, and BSUIDs are discarded. |
| `smb_message_echoes` | Validates echo IDs/types/timestamps and stores aggregate counts only. Echo bodies, recipients, and message IDs are discarded. Echoes never invoke AI or the Cloud API send path, including when AWAY is selected. |

These handlers update aggregate fields on the existing `whatsappManualAvailability/<phone_number_id>` document. They introduce no new collection, Firestore rule, index, migration, or local production write. The document remains client-denied by the current default-deny Firestore rules; Admin SDK code writes it. Duplicate aggregate events are harmless/idempotent in effect, but there is no globally durable event-receipt ledger for coexistence events. Incoming `messages` use the separate persistent receipts and conversation storage described above.

### Coexistence Prerequisites and Limitations

Meta's current official coexistence onboarding requires, at minimum:

- An eligible Solution Partner or Tech Provider implementation and an authorized business representative to complete Meta's required onboarding and business/legal attestations. An adult representative must perform age-restricted actions when required.
- WhatsApp Business App version 2.24.17 or newer and Meta's currently supported Embedded Signup version. As of November 14, 2026, Meta lists v5 as the latest version (released October 20, 2026); v2/v3 were deprecated October 15, 2026. v5 enables Business App onboarding by default, uses `extras.version: "v5"`, and returns a fixed session-info object (`sessionInfoVersion` is ignored). v4 remains listed and uses `featureType: "whatsapp_business_app_onboarding"` where applicable.
- Embedded Signup session logging, a correctly configured public HTTPS webhook, and a working onboarding implementation. This repository does **not** implement or launch Embedded Signup/session logging.
- Subscription and handling for `messages` plus `account_update`, `history`, `smb_app_state_sync`, and `smb_message_echoes`. The local webhook now parses the four coexistence categories above but does not implement the Embedded Signup handoff, history/contact synchronization API calls, or customer-facing history display.
- A Business-type Meta app (or supported use case) with Facebook Login for Business and a WhatsApp Embedded Signup configuration ID. The app must have a Meta Business Portfolio; becoming a Tech Provider requires business verification and App Review.
- Advanced Access/App Review for `whatsapp_business_messaging` and `whatsapp_business_management` before onboarding external businesses in live mode. `business_management` may also be needed for business-integration system-user token management and Solution Partner credit-line operations; it is not a substitute for the two WhatsApp permissions.
- A connected Cloud API sender and Meta confirmation that the particular business number/account is eligible. Meta's coexistence flow can unlink companion devices (which must be relinked) and changes some Business App features. The Business App and Cloud API also have different customer-service-window behavior and Cloud API pricing.

### Official SDK and Callback Contract

Meta documents loading `https://connect.facebook.net/en_US/sdk.js`, initializing the Facebook JavaScript SDK with the public App ID and a supported Graph API version, then using `FB.login` with the Facebook Login for Business `config_id`, `response_type: "code"`, and `override_default_response_type: true`. For v5, pass `extras: { version: "v5" }`; Business App onboarding is on by default. For v4, use the appropriate Login-for-Business configuration and coexistence `featureType` per the v4 documentation. The version/configuration must be confirmed in Meta's Embedded Signup Builder; the readiness card does not load the SDK or call `FB.login`.

Embedded Signup uses two browser callbacks: the SDK login callback returns `response.authResponse.code`, and the session `message` event returns asset/session information. The official v5 completion object includes `data.phone_number_id`, `data.messaging_account_ids`, `data.is_on_biz_app`, `data.primary_waac_ids`, `type: "WA_EMBEDDED_SIGNUP"`, and an event such as `FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING`. v4 returns its documented session-info shape, including `waba_id`; do not assume the v4 and v5 shapes are interchangeable. The session event alone is not proof of API connection.

Meta says the exchangeable authorization code is returned to the SDK callback only when the user clicks Finish and expires after 30 seconds. The documented exchange is server-to-server at `GET https://graph.facebook.com/<GRAPH_API_VERSION>/oauth/access_token` with `client_id`, `client_secret`, and `code`. Never send the app secret to the browser or log the code/token. The project currently has no callback receiver, origin/state/session validation, code-exchange implementation, or secure token-vault adapter; therefore the local UI cannot start this flow or store its resulting business token.

To verify a future authorized coexistence connection, Meta documents querying the returned phone-number ID for `is_on_biz_app,platform_type`; only an official response with `is_on_biz_app=true` and `platform_type=CLOUD_API` is evidence for both app and Cloud API use. This repository has no Graph verification endpoint yet, and no verification request has been made.

The current webhook reports observed lifecycle statuses only; it cannot confirm the live phone-number connection. After authorized onboarding, confirm through Meta's documented phone-number status fields, including `is_on_biz_app=true` and `platform_type=CLOUD_API`, before treating coexistence as active. The Chief Owner review checkbox is only an explicit human confirmation; the service still reports the connection as unverified. This project has not performed that check.

### State and Storage Boundaries

The existing mode document retains only the latest per-category coexistence summary. History sync records bounded counts, phase/chunk/progress, numeric error codes, and event time; state sync records counts/time; echoes record counts/time; account events record a fixed event/status and event time. No raw webhook, contact list, historical content, echoed content, or customer identifier is stored by these parsers. There is no automatic expiration policy for those summary fields; they remain until overwritten or the mode document is deleted by an authorized backend administrator. No data deletion endpoint was added.

Persistent customer conversation history and durable message receipts are implemented as described in [Persistent Conversation Memory](#persistent-conversation-memory). This stores customer message content in Firestore and incurs database read/write and TTL-deletion costs. TTL policies remain an administrator-controlled setup step.

### Activation Stages

1. **Local code:** coexistence parsers and mocked tests are implemented. This does not mean Meta onboarding is supported end-to-end.
2. **Meta account eligibility:** not confirmed for this Business App/account.
3. **Embedded Signup:** not started or completed.
4. **Cloud API sender connection:** not verified.
5. **Live inbound/outbound operation:** not tested. No real messages have been sent.

Do not register, migrate, disconnect, or start Embedded Signup for the existing Business App number as part of local readiness work. For a deliberate rollback after a future authorized coexistence onboarding, first set the manual mode to AVAILABLE and stop webhook processing; an authorized business administrator must review Meta's current offboarding guidance before disconnecting Cloud API. The code does not disconnect or deregister numbers automatically.

## Behavior and Platform Rules

- GET verification checks `hub.mode=subscribe` and uses constant-time verify-token comparison before returning `hub.challenge`.
- POST requests require a valid HMAC-SHA256 `X-Hub-Signature-256` over the raw body using `WHATSAPP_APP_SECRET`.
- Only a configured phone-number ID is processed. Unknown IDs, status-only updates, and unsupported message types do not receive AI replies.
- Customer context is isolated by `(receiving phone_number_id, Meta customer identity)`. Meta's `from_user_id` (BSUID) is preferred when supplied; otherwise the sender's `from` value is used. Replies use the same originating business phone-number ID and the correct `to` or BSUID `recipient` field.
- Context is capped at the latest 20 messages by default and expires after 30 days of inactivity. Receipt IDs are HMAC-derived with the stable identifier key. Ambiguous sends are never automatically retried; see [Delivery state and recovery](#delivery-state-and-recovery).
- The webhook currently generates and sends synchronously. Firestore transactions coordinate receipt claims, a rolling per-customer rate limit, and ten shared AI concurrency slots per sender. These guarantees still require validation against real multi-instance Firestore; the tests use a fake transactional store. There is no durable queue decoupling webhook delivery from AI generation and sending.
- Before AI generation or delivery, the webhook requires a valid message timestamp within Meta's 24-hour customer-service window. Messages outside the window or dated in the future are acknowledged but ignored; messages without a timestamp are rejected. This endpoint does not send approved templates or bypass the window. STOP/START commands are supported, but the organization must still provide the required privacy notice and obtain/record any legally or policy-required opt-in before messaging.
- Replies are plain text and limited to 4096 characters. Image-generation requests are answered with a text-only notice because this endpoint does not send WhatsApp media.
- Meta webhook redelivery is deduplicated by the durable receipt ID. `processing` with a live lease returns a retry response; `sending` and `delivery_unknown` are acknowledged without another send; `failed` may be retried after a known pre-delivery failure or operator-confirmed not-delivered reconciliation. A stale `sending` receipt is intentionally not reopened. Eight-day receipt deletion still depends on the separately configured Firestore TTL policy.
- The manual mode, conversation history, and webhook receipts are persisted in Firestore and shared across backend instances. No process-local message-deduplication fallback is used if Firestore is unavailable. Coexistence summary events do not have a durable event-receipt ledger.

## WhatsApp OTP Authentication

The separate `/api/auth/whatsapp/request`, `/api/auth/whatsapp/resend`, and
`/api/auth/whatsapp/verify` routes provide an additional login path. They do
not replace Firebase SMS Phone Auth. The frontend uses the existing country
selector and server-side `phonenumbers` metadata validation.

An OTP is an eight-character numeric string, including leading zeroes. It is
generated with Python's `secrets` module, expires five minutes after activation,
allows at most five incorrect attempts, and can be resent after 60 seconds.
Firestore stores a keyed HMAC of the code, a protected phone lookup key, the
existing Firebase UID, timestamps, attempt count, status, and login purpose;
it never stores the phone number or plaintext code. Verification and single-use
consumption use Firestore transactions. A replacement invalidates the previous
active session only after the new delivery attempt is accepted or its outcome
is ambiguous.

Only a Firebase user whose Firebase Auth record already has the matching
verified phone number and who already has active membership in the configured
shared owner space is eligible. The endpoints do not create Firebase users,
link phone numbers, assign roles, or add owner members. The UID is resolved
server-side and never accepted from the request. Firebase Admin creates a
custom token only for that existing UID after OTP consumption and a second
phone-association check.

All valid requests return the same generic response shape and wording whether
or not the number is eligible. A 2xx Meta response with a message ID is treated
as accepted; timeouts and server errors have an unknown outcome and are not
retried automatically. The response never claims that a message was delivered.
The authentication template must be approved by Meta before use.

Configure these values only in the backend secret manager:

| Variable | Description |
| --- | --- |
| `WHATSAPP_OTP_ACCESS_TOKEN` | Server-only Meta token authorized to send from the dedicated OTP sender. |
| `WHATSAPP_OTP_PHONE_NUMBER_ID` | Numeric Cloud API ID of the approved OTP sender; not the visible phone number. |
| `WHATSAPP_OTP_TEMPLATE_NAME` | Name of the approved authentication template with a copy-code OTP button. |
| `WHATSAPP_OTP_TEMPLATE_LANGUAGE` | Approved template locale, such as `en_US`. |
| `WHATSAPP_OTP_HMAC_SECRET` | Random private key of at least 32 UTF-8 bytes for OTP and protected lookup HMACs. |
| `WHATSAPP_GRAPH_API_VERSION` | Existing Graph API version setting, which must be currently supported. |

The sending operation uses `/{phone-number-id}/messages`; it does not require
the WABA ID in the message request. Do not configure the active personal-style
WhatsApp Messenger number as the OTP sender. A separate Meta-approved Cloud API
sender and its approved authentication template are prerequisites. This
implementation does not set credentials, create templates, change Meta
settings, or send test messages.

OTP sessions, active-session pointers, and rate-limit records are stored in the
server-only `whatsappOtpSessions`, `whatsappOtpActiveSessions`, and
`whatsappOtpRateLimits` collections. Existing Firestore rules deny browser
access; Admin SDK access is server-side. Configure Firestore TTL on each
collection's `expiresAt` field for cleanup. Expiration is always checked by the
backend and does not rely on TTL deletion. No Firestore rules or TTL settings
are changed by this source implementation.

Initial durable hourly limits are five requests per phone, 30 requests per IP,
500 total requests, five send attempts per phone, 20 send attempts per IP, and
100 total send attempts. Verification also has the five-attempt session limit,
plus 30 attempts per phone and 60 per IP per hour. Vercel's overwritten
`X-Forwarded-For` header is used as the client IP source; do not put an
untrusted proxy in front of this deployment without reviewing its IP-header
handling.

Users must explicitly request a WhatsApp code and be told that it will be sent
to the number they enter. Obtain and retain any additional opt-in required by
Meta or applicable law before enabling customer traffic.

## Local Tests

Run the backend tests with:

```powershell
py -m pytest -q backend/tests
```

All WhatsApp tests mock AI and Graph API calls. They do not contact Meta or send messages.

## Official Meta References

- [Cloud API Get Started](https://developers.facebook.com/documentation/business-messaging/whatsapp/get-started)
- [Business phone numbers and registration](https://developers.facebook.com/documentation/business-messaging/whatsapp/business-phone-numbers/phone-numbers)
- [Onboard WhatsApp Business App users (Coexistence)](https://developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup/onboarding-business-app-users)
- [Account update webhook reference](https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/reference/account_update)
- [Business App coexistence history, state sync, and echo payloads](https://developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup/onboarding-business-app-users)
- [Messages webhook reference](https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/reference/messages)
- [Create a webhook endpoint](https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/create-webhook-endpoint)
- [Send messages and customer-service windows](https://developers.facebook.com/documentation/business-messaging/whatsapp/messages/send-messages)
- [Facebook Login for Business](https://developers.facebook.com/docs/facebook-login/facebook-login-for-business/)
- [Embedded Signup implementation](https://developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup/implementation)
- [Embedded Signup versions](https://developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup/versions)