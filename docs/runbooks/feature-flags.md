# Runbook — Feature Flags

Toggle product features on/off at runtime, no redeploy. Shipped in PR #190.

## TL;DR
**Admin → Feature Toggles** (platform-admin only). Flip a switch; it takes effect
across all workers within **~20 seconds**. That's it.

## How it works
- Each flag has an **env-var default** (shipped in Railway) and an optional **DB
  override** (the `feature_flags` table). The override wins; with no override, the
  env default is used.
- Flags are read at request time via `services.feature_flags.is_enabled(db, key)`
  with a ~20s per-worker cache, so a toggle propagates to all `--workers` within
  the TTL.
- **Fail-safe:** any DB error (or the row missing) falls back to the env default.
  A storage problem can never flip behavior unexpectedly or block startup.

## Current flags
| Key | What it does | Env default | Default state |
|-----|--------------|-------------|---------------|
| `rerun_confirmation` | Require confirmation + notify all team coaches before a 2nd billable analysis on already-analyzed film | `RERUN_CONFIRMATION_ENABLED` | **On** |
| `recruiting_consent` | Require a per-player directory-disclosure attestation before minting a public recruiting link | `RECRUITING_CONSENT_ENABLED` | **Off** |

> `recruiting_consent` is intentionally **off** until the attorney finalizes the
> attestation text in `services/legal.py` (`RECRUITING_DIRECTORY_VERSION`,
> currently `-draft`). Bump that version when the text is final, then turn the flag
> on.

## Toggle a flag (two ways)

**UI (preferred):** Admin → Feature Toggles → click the switch. The badge shows
`ON`/`OFF`, and `override` when it differs from the shipped default.

**API (scripting / no UI):**
```
GET  /admin/feature-flags            → { flags: [ { key, enabled, source, env_default, ... } ] }
PUT  /admin/feature-flags/{key}      body: { "enabled": true|false }
```
Both require a platform-admin bearer token.

## Change the shipped default (env var)
The DB override wins over the env var, so for a permanent baseline change also set
the env var on `coachlenz-backend` (this triggers a redeploy):
```
railway variables --set 'RERUN_CONFIRMATION_ENABLED=true'
```
If a DB override exists for that key, it will still win until you clear/flip it in
the panel.

## Gotchas
- **No "reset to default" / delete-override endpoint yet.** Once you toggle a flag,
  a `feature_flags` row exists and the flag reads `source: override` — even if you
  set it back to the env-default value (functionally identical, just labeled
  override). To truly remove an override, delete the row directly:
  `DELETE FROM feature_flags WHERE key = '<key>';`
- **~20s lag** across workers after a toggle — the per-worker cache TTL. Not
  instant; wait ~20s before concluding a toggle "didn't work."
- **Env change requires redeploy**; a UI/API toggle does not.

## Add a new flag
1. Add an entry to `FLAGS` in `backend/services/feature_flags.py`, naming its
   `env_default` settings attribute (add that bool to `config.py` too).
2. At the check site, call `await feature_flags.is_enabled(db, "<key>")` instead of
   reading `settings.<X>` directly.

It then appears in the Admin panel automatically, grouped by its `category`.

## Rollback
Turn the flag **off** in the panel (or `PUT ... {enabled:false}`). Effect within
~20s, no deploy. For the two current flags, "off" restores prior behavior exactly
(no rerun gate / no recruiting-consent gate).
