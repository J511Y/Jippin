-- CMP-604 post-cutover cleanup.
-- Supabase Auth is the DB/Auth SSOT. The public schema keeps only Jippin
-- application profile and consent-audit data keyed by auth.users.id.

drop table if exists public.auth_identities;

drop table if exists public.external_sso_accounts;

drop index if exists public.ix_anonymous_users_last_seen_at;
drop table if exists public.anonymous_users;

alter table if exists public.terms_consents
  drop constraint if exists fk_terms_consents_user_id_users;

alter table if exists public.users
  drop column if exists email;

alter table if exists public.users
  alter column id drop default;

alter table if exists public.users
  drop constraint if exists fk_users_id_auth_users;

-- Legacy self-auth rows cannot satisfy the new Supabase Auth profile FK unless
-- their UUID already exists in auth.users. Drop orphan profile/consent rows
-- before adding validated constraints so the cleanup does not leave permanent
-- NOT VALID integrity gaps.
delete from public.terms_consents as terms
where not exists (
  select 1
  from auth.users as auth_user
  where auth_user.id = terms.user_id
);

delete from public.users as app_user
where not exists (
  select 1
  from auth.users as auth_user
  where auth_user.id = app_user.id
);

alter table if exists public.users
  add constraint fk_users_id_auth_users
  foreign key (id)
  references auth.users (id)
  on delete cascade;

alter table if exists public.terms_consents
  drop constraint if exists fk_terms_consents_user_id_auth_users;

alter table if exists public.terms_consents
  add constraint fk_terms_consents_user_id_auth_users
  foreign key (user_id)
  references auth.users (id)
  on delete cascade;

drop type if exists public.external_sso_provider;
