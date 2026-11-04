# Security Notes

## Boundaries

- Never place secrets in source or documentation.
- Do not inspect or disclose `.env` contents.
- Do not use production writes, migrations, deployment, or external
  configuration changes without explicit authorization.
- Firebase browser configuration is client-side configuration; server
  credentials and provider secrets must remain server-side.

## Inspection Findings

- Firestore rules default-deny paths outside the explicitly declared user and
  owner data structures.
- Firebase ID-token verification, owner checks, and RBAC modules are present in
  the backend source. Their production configuration and end-to-end enforcement
  were not tested.
- Firebase and Supabase code paths coexist; confirm each route's intended
  identity and authorization source before changing access control.
- The repository working directory contains a file named
  `serviceAccountKey.json`. It was not opened. Git reports it as ignored and
  untracked. Treat it as sensitive, keep it outside shared or backed-up
  locations, and assess/rotate the credential if exposure is suspected.
- `.env` and `.env.local` filenames are present locally; their contents were
  not read.
- A backend health route returns Firebase initialization-error text when
  initialization is unavailable. Review whether that detail should be exposed
  publicly before relying on the endpoint in production.

## Validation Limits

No security audit or production authorization test was performed. These notes
are inspection observations, not a security certification.
