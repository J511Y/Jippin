-- CMP-DIRECT 관리자 콘솔 /users — 일반 회원(role='user')만 노출 + 전화번호 컬럼.
--
-- 운영자는 회원 관리에서 관리자 계정을 볼 필요가 없으므로 목록을 일반 회원으로
-- 한정한다. 역할 컬럼은 화면에서 제거하고 대신 본인확인된 전화번호를 노출한다.
-- 전화번호는 가입 시 서버가 app_metadata.phone 에 정규화(010-1234-5678) 저장한다
-- (apps/api supabase_admin.create_email_user). user_metadata 가 아니라
-- app_metadata 라 사용자가 임의로 바꿀 수 없는 신뢰값이다.
--
-- role 필터는 반드시 DB(WHERE)에서 적용해야 LIMIT/OFFSET 페이지네이션과
-- total_count(count(*) over ())가 일관된다 — 앱 레이어 후처리 필터는 페이지가
-- 깨진다.
--
-- 반환 TABLE 의 컬럼 구성을 바꾸므로(role 제거·phone 추가) create or replace 로는
-- 불가능하다 → drop 후 재생성한다.

drop function if exists public.admin_list_users(text, integer, integer);

create function public.admin_list_users(
  search text default null,
  page_limit integer default 20,
  page_offset integer default 0
)
returns table (
  id uuid,
  email text,
  display_name text,
  phone text,
  status text,
  provider text,
  last_sign_in_at timestamp with time zone,
  created_at timestamp with time zone,
  total_count bigint
)
language sql
stable
security definer
set search_path = public, pg_temp
as $$
  select
    au.id,
    au.email::text,
    coalesce(
      nullif(btrim(au.raw_user_meta_data ->> 'name'), ''),
      u.display_name
    ) as display_name,
    au.raw_app_meta_data ->> 'phone' as phone,
    u.status,
    au.raw_app_meta_data ->> 'provider' as provider,
    au.last_sign_in_at,
    au.created_at,
    count(*) over () as total_count
  from auth.users as au
  left join public.users as u on u.id = au.id
  where
    coalesce(au.is_anonymous, false) = false
    -- 일반 회원만(관리자 등 그 외 역할 제외). role 미설정 계정은 'user' 로 간주.
    and coalesce(au.raw_app_meta_data ->> 'role', u.role, 'user') = 'user'
    and (
      search is null
      or btrim(search) = ''
      or au.email ilike '%' || btrim(search) || '%'
      or u.display_name ilike '%' || btrim(search) || '%'
      or au.raw_user_meta_data ->> 'name' ilike '%' || btrim(search) || '%'
      or au.raw_app_meta_data ->> 'phone' ilike '%' || btrim(search) || '%'
    )
  order by au.created_at desc
  limit greatest(coalesce(page_limit, 20), 1)
  offset greatest(coalesce(page_offset, 0), 0);
$$;

-- 함수는 기본적으로 PUBLIC 에 EXECUTE 가 열리므로 명시적으로 회수한다.
revoke execute on function public.admin_list_users(text, integer, integer) from public, anon, authenticated;
grant execute on function public.admin_list_users(text, integer, integer) to service_role;
