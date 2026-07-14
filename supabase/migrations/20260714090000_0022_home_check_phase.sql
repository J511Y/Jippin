-- 0022 우리집 체크 — 진행 phase 컬럼 (대기 화면 실시간 단계 표시).
-- 결정 정본: docs/adr/0008-home-check-building-register.md (home-check schema 1.3.0).
--
-- phase 는 백그라운드 파이프라인(services/home_check)이 기록하는 **정보성** 진행 단계다.
-- 판정에 쓰이지 않으며(status 가 상태 기계 정본), 프론트 대기 화면이 status=pending|querying
-- 일 때만 읽는다. 알려진 값:
--   received → issuing_registers → judging → saving_report
-- 워커 통합/세분화 시 값이 추가될 수 있어 CHECK 를 두지 않는다 — 클라이언트는 미지의 값을
-- 일반 대기 문구로 폴백해야 한다(계약 1.3.0 명시). 터미널 상태에선 마지막 값이 남는다(운영
-- 진단용). nullable + default 없음 — 기존 행은 null 로 남고, 새 행은 insert 가 received 를 준다.

alter table public.home_checks
  add column if not exists phase text;

comment on column public.home_checks.phase is
  'Informational pipeline phase written by the background job. Known values: '
  'received | issuing_registers | judging | saving_report. Not a state machine '
  '(status is); no CHECK on purpose so new phases deploy without a migration. '
  'Frontend reads it only while status is pending/querying.';
