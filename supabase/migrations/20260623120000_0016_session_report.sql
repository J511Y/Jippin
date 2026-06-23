-- 0016 Session report — 사전검토 세션의 룰 판정 결과 영속화 (CMP-DIRECT).
--
-- 에이전트가 evaluate_rules 로 만든 rule-eval-result(verdict/required_facilities/
-- legal_basis/user_message 등)는 지금까지 chat_messages.judgment_snapshot 에만
-- 흩어져 있어 독립 리포트(GET /sessions/{id}/report)로 노출할 정본이 없었다.
-- 세션에 최종 판정을 단일 verdict 로 영속해 리포트의 source of truth 로 삼는다.
--
-- rule_eval_result: rule-eval-result 계약 그대로의 JSON(평가 시점 evaluated_at 포함).
-- rule_evaluated_at: 마지막으로 판정을 기록한 시각(리포트 신선도 표시용).
-- 이 컬럼이 NULL 이면 리포트 미준비(REPORT_NOT_READY).

alter table public.sessions
  add column if not exists rule_eval_result jsonb,
  add column if not exists rule_evaluated_at timestamp with time zone;
