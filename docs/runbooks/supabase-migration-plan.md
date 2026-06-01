# Supabase SQL Migration Plan

- Issue: CMP-575
- Status: first conversion candidate
- Scope: local file conversion only. Do not apply these migrations to a real Supabase project until the board approves the source-of-truth switch.

## Decision

Use `supabase/migrations/*.sql` as the database schema source of truth after the switch. Keep SQLAlchemy models as application ORM models that must match the SQL schema, not as the primary DB definition. Alembic should be retired for forward migrations once Supabase CI/deploy jobs are in place.

Recommended transition:

1. Land the SQL candidates in this issue for review.
2. Add a CI job that applies `supabase/migrations` to a disposable Supabase or Postgres database and runs schema checks.
3. Stop creating new Alembic revisions after the cutover PR is approved.
4. Keep `apps/api/migrations` temporarily as historical reference for one release window.
5. Remove Alembic workflow steps only after Supabase migration CI and deploy automation are active.

Do not run both Alembic and Supabase SQL as independent forward-migration authorities. That would create schema drift because GitHub/Supabase automation reads SQL files while the current API CI reads Alembic revisions.

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

Temporary compatibility plan:

- Keep `apps/api/tests/test_models_metadata.py` because it protects the OAuth-only user model, no-password invariant, and consent constraints.
- Replace `apps/api/tests/test_alembic_revision.py` with a Supabase migration-order/static-schema test after the cutover.
- Replace `.github/workflows/ci.yml` `migrate-check` and `.github/workflows/neon-pr-branch.yml` Alembic steps with Supabase SQL application checks.

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

- DevOps: replace Alembic CI/deploy migration steps with Supabase SQL migration checks.
- Backend: add a static test that `supabase/migrations` order and final table/constraint names match expected ORM metadata.
- Architecture/DB owner: approve the exact cutover point and decide whether to squash the historical probe create/drop pair before first production Supabase apply.
