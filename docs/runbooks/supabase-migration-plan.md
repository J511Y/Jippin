# Supabase SQL Migration Plan

- Issues: CMP-575 (SQL conversion candidates), CMP-603 (CI/CD cutover), CMP-604 (public auth cleanup)
- Status: forward migration SSOT switched to `supabase/migrations/*.sql` (CMP-603 cutover). Alembic demoted to historical reference.
- Scope: this document covers the conversion inventory + post-cutover guard. Direct schema edits in the Supabase Console SQL editor are prohibited (`db pull` / `migration repair` required if it happens — see Console hygiene below).

## Decision

Use `supabase/migrations/*.sql` as the database schema source of truth. SQLAlchemy models in `apps/api/src/models/` are application ORM models that must match the SQL schema; they are no longer the primary DB definition. Alembic is retired for forward migrations as of the CMP-603 cutover and is kept only as historical reference.

Post-cutover transition (CMP-603):

1. Forward DB migration SSOT is `supabase/migrations/*.sql`.
2. Application of those files is owned by **Supabase GitHub Integration**: `dev` push → development branch, `main` push → production branch. PR preview branches get the same files via Automatic Branching (Supabase-changes-only mode).
3. CI guard: `.github/workflows/ci.yml::migrate-check` fails when a PR touches `apps/api/src/models/**/*.py` without adding a matching `supabase/migrations/*.sql` file. Static diff guard, no Neon / Alembic dependency. Definition: `docs/runbooks/supabase-branching.md` §6.3.2.
4. `apps/api/migrations/` (Alembic revisions) is preserved as a historical reference for one release window. Do not create new Alembic revisions.
5. Do not run both Alembic and Supabase SQL as independent forward-migration authorities. That would create schema drift because Supabase GitHub Integration reads SQL files only.

Console hygiene (MUST):

- Do not edit remote schema via the Supabase Console SQL editor / Table editor. Direct edits diverge from repo migrations and break `supabase db push` with `local migration files and remote migration history are out of sync`.
- If a direct edit happens by accident: run `supabase db pull` (to bring the remote diff into a new local migration) or `supabase migration repair --status reverted|applied <timestamp>` to realign history. Document the recovery in the same PR.

## Inventory

| Alembic revision | File | Schema effect | Supabase SQL candidate |
|---|---|---|---|
| `0001_baseline` | `20260528_0533_0001_baseline.py` | No application schema. Alembic version baseline only. | `supabase/migrations/20260528053300_0001_alembic_baseline.sql` comment-only no-op. |
| `0002_deployment_probe_temp` | `20260528_0645_0002_deployment_probe_temp.py` | Creates `deployment_probe_temp(id, created_at, marker)`. Historical deployment probe. | `20260528064500_0002_deployment_probe_temp.sql`. |
| `0003_drop_deployment_probe_temp` | `20260528_0655_0003_drop_deployment_probe_temp.py` | Drops `deployment_probe_temp`; no net final schema. | `20260528065500_0003_drop_deployment_probe_temp.sql`. |
| `0004_request_logs` | `20260528_0905_0004_request_logs.py` | Creates `request_logs` plus indexes on `created_at`, `request_id`, `response_code`, and `(user_id, created_at desc)`. | `20260528090500_0004_request_logs.sql`. |
| `0005_auth_skeleton` | `20260529_1200_0005_auth_skeleton.py` | Historical self-auth skeleton: enum `external_sso_provider`, tables `users`, `external_sso_accounts`, `anonymous_users`, `terms_consents`, and `ix_anonymous_users_last_seen_at`. | `20260529120000_0005_auth_skeleton.sql`, followed by CMP-604 cleanup. |
| `0006_terms_consent_unique_key` | `20260529_1330_0006_terms_consent_unique_key.py` | Changes `terms_consents` uniqueness from `(user_id, term_id, version, source)` to `(user_id, term_id, version)`. | `20260529133000_0006_terms_consent_unique_key.sql`. |

## Current Final Schema

Final schema after CMP-604 cleanup:

- `request_logs`
- `users` — app profile/RBAC table keyed by `auth.users.id`
- `terms_consents` — consent audit table keyed by `auth.users.id`

The temporary `deployment_probe_temp` table is intentionally absent after the sequence completes. The legacy `external_sso_accounts`, `anonymous_users`, `auth_identities`, and `external_sso_provider` objects are intentionally absent after CMP-604.

## Supabase Auth Impact

| Current public table | Supabase Auth adoption impact | Recommendation |
|---|---|---|
| `users` | Supabase `auth.users` is identity SSOT. | Keep as `public.users(id references auth.users(id))` for Jippin profile/RBAC only. Do not store email/provider subject/password columns. |
| `anonymous_users` | Supabase Anonymous Sign-In (`auth.users.is_anonymous`) replaces it. | Drop through CMP-604 forward migration. |
| `external_sso_accounts` | Supabase `auth.identities` replaces it. | Drop through CMP-604 forward migration. |
| `auth_identities` | Supabase JWT `sub` maps directly to `auth.users.id`. | Drop through CMP-604 forward migration if present. |
| `terms_consents` | Supabase Auth does not replace Jippin's consent audit requirement. | Keep in `public`; `user_id` references `auth.users(id)`. |

## Alembic Keep/Remove Recommendation

Recommended: switch DB source of truth to Supabase SQL, then demote Alembic to historical reference and remove it in a later cleanup.

Reasoning:

- Supabase GitHub integration applies SQL migrations from `supabase/migrations`.
- Keeping Alembic as an active migration authority duplicates the schema ledger.
- SQLAlchemy models are still valuable for FastAPI ORM access and model metadata tests, but they should be checked against SQL, not used to generate production DDL after cutover.

Compatibility plan (post-cutover, CMP-603):

- Keep `apps/api/tests/test_models_metadata.py` because it protects the Supabase-profile model, no-password/no-shadow-email invariant, and consent constraints.
- `apps/api/tests/test_alembic_revision.py` is now historical-only (Alembic is retired for forward migrations). A Supabase migration-order/static-schema test is a follow-up item.
- `.github/workflows/ci.yml::migrate-check` is now the Supabase SQL migration drift guard (model-only PR static check). `.github/workflows/_archive/neon-pr-branch.yml.archived` is no longer loaded by GitHub Actions. `.github/workflows/deploy.yml::release-migrate` was removed entirely — DB migration is owned by Supabase GitHub Integration.

## Static Verification Notes

Local verification performed in CMP-575:

- Confirmed all current Alembic revision files under `apps/api/migrations/versions`.
- Confirmed ORM tables under `apps/api/src/models`.
- Added SQL files sorted by Supabase timestamp filename convention.
- Preserved existing public schema names and constraint/index names from SQLAlchemy/Alembic naming conventions.

Known limitations before applying to a real Supabase project:

- No real Supabase connection string was available, so migrations were not applied.
- `gen_random_uuid()` assumes the Supabase/Postgres project exposes that function. Supabase projects normally do, but the apply job should verify it before cutover.
- Pre-CMP-604 SQL candidates preserve Alembic exactly. CMP-604 intentionally diverges forward schema from historical Alembic to remove self-auth tables and align public FKs to `auth.users(id)`.

## Follow-up Work

- DevOps: ✅ done (CMP-603) — Neon preview workflow archived, `deploy.yml::release-migrate` removed, `ci.yml::migrate-check` rewired to Supabase SQL drift guard, `supabase-status.yml` wrapper added.
- Backend: add a static test that `supabase/migrations` order and final table/constraint names match expected ORM metadata (pending follow-up issue).
- Architecture/DB owner: approve the exact cutover point and decide whether to squash the historical probe create/drop pair before first production Supabase apply.
- Operator: register `supabase-status` and `ci-status` as required checks on `dev` / `main` branch protection. Register `SUPABASE_INTEGRATION_CHECK_NAME` repository variable after the first `supabase/**` PR reveals the actual Supabase integration check context (`docs/runbooks/supabase-branching.md` §6.3.1).
