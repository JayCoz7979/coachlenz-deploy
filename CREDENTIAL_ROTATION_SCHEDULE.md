# Credential Rotation Schedule

All secrets live **only** in Railway environment variables (per service). None are
in code, config files, or git history. Rotate on the cadence below; rotate
immediately on any suspected leak or staff offboarding.

Two categories, handled very differently:

- **External service keys** — the app just reads them from env and passes them to
  the provider. Rotation is operational: mint a new key in the provider dashboard,
  update the Railway variable, redeploy. No code change, no grace window needed
  (the app uses whatever value is in env).
- **App-owned crypto keys** (`SECRET_KEY`, `FERNET_KEY`) — rotating naively breaks
  production (all users logged out / encrypted data unreadable). The code supports
  a grace window so you can rotate safely; follow the procedures below.

## Cadence

| Secret | Service | Cadence | Category |
|---|---|---|---|
| `SECRET_KEY` (+ `SECRET_KEY_PREVIOUS`) | app JWT signing | 180 days | app-owned |
| `FERNET_KEY` (+ `FERNET_KEYS_PREVIOUS`) | app at-rest encryption | 180 days | app-owned |
| `ANTHROPIC_API_KEY` | Anthropic | 90 days | external |
| `STRIPE_SECRET_KEY` | Stripe | 90 days | external |
| `STRIPE_WEBHOOK_SECRET` | Stripe | on endpoint change / 90 days | external |
| `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` | Cloudflare R2 | 90 days | external |
| `RESEND_API_KEY` | Resend | 90 days | external |
| `TWILIO_AUTH_TOKEN` | Twilio | 90 days | external |
| `SENTRY_DSN` | Sentry | as needed | external |
| `ADMIN_PASSWORD` | app admin seed | **rotate now** (still defaults to `ChangeMeNow!`) | app-owned |

## Procedures

### External service keys (Anthropic, Stripe, R2, Resend, Twilio, Sentry)
1. Create a new key/token in the provider dashboard (keep the old one active).
2. Update the matching Railway variable on `coachlenz-backend` (and any worker
   service that uses it).
3. Redeploy; confirm the feature works (e.g. a test analysis, a Stripe test event).
4. Revoke the old key in the provider dashboard.

Stripe/R2 support overlapping keys, so there is no downtime. For
`STRIPE_WEBHOOK_SECRET`, roll the signing secret in the Stripe dashboard, then
update the env var; in-flight events use the secret they were signed with.

### `SECRET_KEY` — JWT signing (grace-window rotation, no forced logout)
`decode_token` verifies against `SECRET_KEY` first, then `SECRET_KEY_PREVIOUS`.
1. Generate a new key: `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
2. Set `SECRET_KEY_PREVIOUS` = the current `SECRET_KEY`.
3. Set `SECRET_KEY` = the new value. Redeploy.
   - New tokens are signed with the new key; tokens issued before the rotation
     still verify via `SECRET_KEY_PREVIOUS`.
4. After the refresh-token lifetime has fully elapsed (**30 days**, per
   `REFRESH_TOKEN_EXPIRE_DAYS`), clear `SECRET_KEY_PREVIOUS`. Redeploy. Any token
   still signed with the old key is now rejected.

To force a hard cutover instead (log everyone out immediately), skip
`SECRET_KEY_PREVIOUS` and just replace `SECRET_KEY`.

### `FERNET_KEY` — at-rest encryption (grace-window rotation, no data loss)
`get_fernet()` is a MultiFernet: it encrypts with `FERNET_KEY` and decrypts against
`FERNET_KEY` + every key in `FERNET_KEYS_PREVIOUS`.
1. Generate a new key: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
2. Move the current `FERNET_KEY` into `FERNET_KEYS_PREVIOUS` (comma-separated if
   more than one old key is still in play).
3. Set `FERNET_KEY` = the new value. Redeploy.
   - New writes use the new key; existing ciphertext (Hudl connection credentials,
     report summaries) still decrypts via the previous key.
4. Re-encrypt existing rows (rewrite `source_connections.encrypted_credentials`
   and `tendency_reports.summary_json` through `encrypt_json`), then remove the old
   key from `FERNET_KEYS_PREVIOUS`. Redeploy.

> Never rotate `FERNET_KEY` without moving the old key to `FERNET_KEYS_PREVIOUS`
> first — data encrypted with the old key would become permanently unreadable.

## Notes
- After any rotation, verify: sign in works (SECRET_KEY), a Hudl-connected org can
  still ingest (FERNET), an analysis runs (Anthropic), and a Stripe test event is
  accepted (Stripe).
- `SECRET_KEY` rotation pairs with refresh-token revocation (`token_version`): a
  compromised key plus a forced global logout closes a session-hijack incident.
