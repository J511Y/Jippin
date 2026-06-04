-- CMP-575 Supabase SQL candidate for Alembic revision 0006_terms_consent_unique_key.

alter table public.terms_consents
  drop constraint uq_terms_consents_user_id_term_id_version_source;

alter table public.terms_consents
  add constraint uq_terms_consents_user_id_term_id_version
  unique (user_id, term_id, version);
