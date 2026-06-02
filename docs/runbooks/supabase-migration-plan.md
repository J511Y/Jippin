# Supabase SQL Migration Plan

- Issues: CMP-575 (SQL conversion candidates), CMP-603 (CI/CD cutover)
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
| `0005_auth_skeleton` | `20260529_1200_0005_auth_skeleton.py` | Creates enum `external_sso_provider`, tables `users`, `external_sso_accounts`, `anonymous_users`, `terms_consents`, and `ix_anonymous_users_last_seen_at`. | `20260529120000_0005_auth_skeleton.sql`. |
| `0006_terms_consent_unique_key` | `20260529_1330_0006_terms_consent_unique_key.py` | Changes `terms_consents` uniqueness from `(user_id, term_id, version, source)` to `(user_id, term_id, version)`. | `20260529133000_0006_terms_consent_unique_key.sql`. |

## Current Final Schema

Final schema after the converted sequence:

- `request_logs`
- `users`
- `external_sso_accounts`
- `anonymous_users`
- `terms_consents`
- enum `external_sso_provider`

The temporary `deployment_probe_temp` table is intentionally absent after the sequence completes.

## Supabase Auth Impact

| Current public table | Supabase Auth adoption impact | Recommendation |
|---|---|---|
| `users` | Supabase also has `auth.users`. Do not modify or shadow it. `public.users` can remain the application profile/account table. | Keep `public.users` for Jippin user metadata. If Supabase Auth becomes the identity provider, add a nullable `auth_user_id uuid references auth.users(id)` in a new migration and ADR. |
| `anonymous_users` | Anonymous pre-review sessions are product-specific and not provided by Supabase Auth. | Keep in `public`. Later add RLS policies only when client-side direct table access is introduced. |
| `external_sso_accounts` | Supabase Auth stores provider identities internally when using Supabase Auth. The current table is still needed while FastAPI owns OAuth. | Keep while FastAPI OAuth remains canonical. If Supabase Auth owns OAuth, migrate this table to an audit/linking table or retire it through a dedicated data migration. |
| `terms_consents` | Supabase Auth does not replace Jippin's consent audit requirement. | Keep in `public` and preserve the current unique key `(user_id, term_id, version)`. |

## Alembic Keep/Remove Recommendation

Recommended: switch DB source of truth to Supabase SQL, then demote Alembic to historical reference and remove it in a later cleanup.

Reasoning:

- Supabase GitHub integration applies SQL migrations from `supabase/migrations`.
- Keeping Alembic as an active migration authority duplicates the schema ledger.
- SQLAlchemy models are still valuable for FastAPI ORM access and model metadata tests, but they should be checked against SQL, not used to generate production DDL after cutover.

Compatibility plan (post-cutover, CMP-603):

- Keep `apps/api/tests/test_models_metadata.py` because it protects the OAuth-only user model, no-password invariant, and consent constraints.
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
- The SQL candidates preserve Alembic exactly. They do not add new foreign-key indexes beyond current Alembic. A follow-up performance pass should evaluate `anonymous_users.converted_user_id` after access patterns are known.

## Follow-up Work

- DevOps: ✅ done (CMP-603) — Neon preview workflow archived, `deploy.yml::release-migrate` removed, `ci.yml::migrate-check` rewired to Supabase SQL drift guard, `supabase-status.yml` wrapper added.
- Backend: add a static test that `supabase/migrations` order and final table/constraint names match expected ORM metadata (pending follow-up issue).
- Architecture/DB owner: approve the exact cutover point and decide whether to squash the historical probe create/drop pair before first production Supabase apply.
- Operator: register `supabase-status` and `ci-status` as required checks on `dev` / `main` branch protection. Register `SUPABASE_INTEGRATION_CHECK_NAME` repository variable after the first `supabase/**` PR reveals the actual Supabase integration check context (`docs/runbooks/supabase-branching.md` §6.3.1).
