-- 0021 우리집 체크 — 사용자 신고 확장 입력 컬럼 (LLM 확장 대조).
-- 결정 정본: docs/adr/0008-home-check-building-register.md (home-check schema 1.2.0).
--
-- '우리집 체크'는 매수자·중개인이 신고한 확장·개조 부위가 건축물대장 변동사항(resChangeList)에
-- 등재돼 있는지 대조한다(services/home_check_extension.judge_extension). 그 판정 입력인
-- 사용자 신고를 잡 행에 보관한다. 둘 다 PII 아님 — reported_extension 은 확장 여부 불리언,
-- extended_areas 는 사용자가 자연어로 적은 확장 부위 텍스트(소유자/주민번호 등 PII 미포함).
--
--   * reported_extension: null=미응답, true=확장했음, false=확장 없음(→ 무조건 legal).
--   * extended_areas: 확장 부위 자유입력(예: '거실, 침실2'). 상한 500자(스키마와 정합).
--
-- 둘 다 nullable — 기존 잡/확장 판정 미사용(EXTENSION_JUDGE_ENABLED=false) 경로와 호환.

alter table public.home_checks
  add column if not exists reported_extension boolean,
  add column if not exists extended_areas text;

comment on column public.home_checks.reported_extension is
  'User-reported extension flag (LLM extension check input). null=unanswered, false=no extension (always legal).';
comment on column public.home_checks.extended_areas is
  'Free-text extended/renovated areas reported by the user (e.g. living room, bedroom). PII-free.';
