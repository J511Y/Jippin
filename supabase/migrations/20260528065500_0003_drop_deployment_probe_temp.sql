-- CMP-575 Supabase SQL candidate for Alembic revision 0003_drop_deployment_probe_temp.
-- Keeps the converted history faithful; final schema has no deployment_probe_temp table.

drop table public.deployment_probe_temp;
