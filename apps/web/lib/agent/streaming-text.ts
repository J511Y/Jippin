/**
 * 스트리밍 본문 표시용 raw JSON 마스킹 (CMP-DIRECT 채팅 UX).
 *
 * 카드 UI 의 정본 채널은 message 이벤트의 `ui_components`(서버 emit_ui_component)다 —
 * 본문 텍스트에 JSON 이 실려 오는 것은 항상 오동작(모델 규칙 위반/내부 LLM 누수)이다.
 * 백엔드가 근원(translate_stream 필터)을 막지만, 잔여 누수가 스트리밍 중 raw JSON 으로
 * 보이지 않게 표시 직전에 가린다. **마스킹만** 한다 — 부분 JSON 을 파싱해 카드로 만들지
 * 않는다(서버 방출 카드와 중복/불일치 방지).
 *
 * 확정 메시지에는 적용하지 않는다(영속 본문은 서버 정본 그대로) — 스트리밍 프리뷰 전용.
 */

// JSON 덤프 시작 신호: ```json 코드펜스, 또는 여는 중괄호 뒤 따옴표 키(`{"`, `{ "`).
// 한국어 생활어 본문에는 나타나지 않는 패턴만 잡는다(과잉 마스킹 방지).
const JSON_START = /```json|\{\s*"/i;

/** 스트리밍 텍스트에서 JSON 덤프 시작 이후를 잘라낸 표시용 문자열을 돌려준다. */
export function maskStreamingJson(text: string): string {
  const match = JSON_START.exec(text);
  if (!match) return text;
  return text.slice(0, match.index).trimEnd();
}
