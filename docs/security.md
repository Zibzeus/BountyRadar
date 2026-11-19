# Deployment trust boundaries

The web service authenticates local accounts with Argon2id. Short-lived sessions use random bearer cookies, with only a hash stored in the database. Mutations check the session CSRF token. Viewer access is read-only except for personal bookmarks and preferences. The API restricts team connection management and scheduling to administrators.

The credential store uses AES-GCM with a separate deployment key. Each ciphertext is bound to the connection ID. Changing the provider or endpoint requires a replacement key. Source jobs receive only a connection ID through Redis. Provider secrets are decrypted in the worker for the outbound request and are omitted from API responses, program snapshots, exports and source logs.

The upstream connector validates the whole feed before committing rows and cache validators together. Authenticated readers select public records and extract only the documented program fields. Missing data, parsing errors, blocked access and remote failures have distinct effects on source health. Automatic source data and manual imports have different verification labels.

Research workers treat all page content as untrusted text and accept only predefined policy-reading tools. The model cannot supply a shell command or destination URL. Public policy fetches require an operator-approved URL and access checks. Provider endpoints are resolved and pinned per request. Only administrators with deployment access can allow private network origins. Bind the optional Agent Reach reader to the internal Docker network.

SQLite is the single-machine launcher database. PostgreSQL, Redis, API, worker and scheduler run on the private Compose network. Only the Caddy listener is published on loopback. Place a TLS proxy or VPN in front for remote team access. Protect host access, backup files, deployment secrets, and account credentials. TLS termination, operating-system updates and external provider policies are operator responsibilities.

Scope verification indicates provenance, not permission to test. Follow the current original policy, including exclusions, reward eligibility, disclosure and timing constraints. Program data may be incomplete even after successful retrieval.

