# WhatsApp staging preparation

This runbook is preparation only. No Firebase project, Meta app or number,
Vercel setting, deployment, or database has been created or changed.

## Discovery status

- Firebase CLI and Google Cloud CLI are not installed, and this runbook does
  not authenticate to Firebase. The intended staging ID supplied by the owner
  is `mi-ai-whatsapp-staging`; its remote existence and configuration are not
  independently verified here.
- The repository has no `.firebaserc` project aliases. `firebase.json` declares
  Firestore rules only; no Firestore indexes file or database ID configuration
  was found.
- The authenticated Vercel CLI lists the project named `mi-ai-assistant-of-mi`,
  but a Preview deployment query returned zero deployments. Its recent listed
  deployments were Production. Preview environment-variable separation was not
  verified. The local `.vercel/project.json` does not identify a linked project.
- No Meta configuration was verified. Required names and procedures are
  documented in [the WhatsApp Cloud API setup guide](./backend/WHATSAPP_CLOUD_API_SETUP.md),
  but the app, test number, webhook, and permissions remain account-owner work.

## Isolation gates

1. Never point a staging process at a production project, credential, Meta
   sender, access token, or Vercel Production environment.
2. Set `MI_FIREBASE_ENVIRONMENT=staging` and
   `FIREBASE_PROJECT_ID=mi-ai-whatsapp-staging`. Staging mode requires that
   exact project ID and fails initialization if it is missing or different;
   it never falls back to `GOOGLE_CLOUD_PROJECT` or the legacy project
   fallback. The legacy selector behavior remains for non-staging runs, so
   never launch a staging process without the staging selector.
3. The backend searches `backend/.env` and the repository-root `.env`. Run the
   staging process with `PYTHON_DOTENV_DISABLED=1` and explicitly supplied
   staging variables so missing values cannot fall through to local files.
4. Both `FIREBASE_SERVICE_ACCOUNT_JSON` and
   `GOOGLE_APPLICATION_CREDENTIALS` are supported. The runtime validates the
   credential's project ID against the selected project without logging
   credential contents. Use a staging-only service account in either mode.
5. Do not start the backend with placeholder credentials in
   `.env.staging.example`. Do not send messages during preparation.

## Firebase owner checklist

1. In Firebase Console, verify that the supplied staging project
   `mi-ai-whatsapp-staging` exists and is distinct from production
   `mi-ai-b3a57`. This runbook did not access either remote project.
2. Only in the verified staging project, review the Firestore location and
   configure its default database. The backend does not select a named
   database. Review and apply Firestore rules only after confirming the target
   is staging. This repository has `firestore.rules`, but no
   `firestore.indexes.json`; verify query/index requirements before creating
   any indexes.
3. Create or select a dedicated staging service account with the minimum
   Firestore permissions needed. Firebase Admin access bypasses Firestore
   client rules, so rules alone do not isolate server credentials.
4. Configure and verify TTL policies separately. The setup guide documents
   receipt and conversation retention requirements and says actual TTL/IAM
   state has not been verified. Do not apply a blanket TTL policy to opted-out
   preference records.

## Meta test checklist

An authorized account owner must use Meta Developer Dashboard to:

1. Select or create a separate test developer app and add the WhatsApp product.
2. Select an eligible WhatsApp test number and record its Phone Number ID and
   WABA ID in the staging secret store. Register only approved test recipients.
3. Configure the staging callback
   `https://<staging-host>/api/whatsapp/webhook`, a staging-only verify token,
   the test app secret, a test access token, and a currently supported Graph
   API version.
4. Subscribe and grant the required access for `messages`, and, if testing
   coexistence summaries, `account_update`, `history`, `smb_app_state_sync`, and
   `smb_message_echoes`. The guide documents the required WhatsApp permissions.
5. Do not treat this implementation as complete Business App coexistence
   onboarding: Embedded Signup, session exchange, and history/contact
   synchronization are not implemented.

No Meta dashboard action or API call was performed for this runbook.

## Vercel Preview checklist

1. An owner must verify the Vercel project and a Preview deployment before
   treating it as staging. The current read-only query found no Preview
   deployment for the project matching the deployed app name.
2. Configure values only in the Vercel Preview environment. Do not edit
   Production variables, promote a Preview deployment, or use `vercel --prod`.
3. Set Preview-only `MI_FIREBASE_ENVIRONMENT=staging` and
   `FIREBASE_PROJECT_ID=mi-ai-whatsapp-staging`; verify the other Preview
   variables use staging-only credentials, sender/token, verify token, app
   secret, Graph version, HMAC key, and AI-provider key. Variable names alone
   do not prove that configured values are independent.
   The backend accepts `FIREBASE_SERVICE_ACCOUNT_JSON` for a Vercel-hosted
   service account; store only the staging credential in the Preview secret
   scope. The runtime also accepts a `GOOGLE_APPLICATION_CREDENTIALS` file
   path, but use it only if the staging credential file is available to that
   runtime.
4. A Preview deployment was not created. Confirm plan/cost implications and
   obtain approval before any deployment or paid usage.

## Local-only procedure after owner verification

1. Copy `.env.staging.example` to an ignored local `.env.staging` file and
   replace placeholders only with staging values. Keep service-account files
   outside version control.
2. Keep `MI_FIREBASE_ENVIRONMENT=staging` and
   `FIREBASE_PROJECT_ID=mi-ai-whatsapp-staging`; verify that the selected
   staging credential's project ID matches. The example file is ignored by
   `.gitignore`; it is not automatically loaded by production code.
3. With the `dotenv` CLI available, launch only with:

   ```powershell
   dotenv -f .env.staging run -- .\.venv\Scripts\python.exe backend\app.py
   ```

   `PYTHON_DOTENV_DISABLED=1` prevents the backend from loading repository
   `.env` files. If the CLI is unavailable or the staging values are incomplete,
   stop rather than launching from the normal repository environment.
4. Do not send any WhatsApp message as part of this preparation. A later
   controlled test must use only the Meta test number and an enrolled test
   recipient, after separate approval and staging verification.
