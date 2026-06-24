/**
 * 에이전트가 보내는 UI 컴포넌트를 json-render `Spec` 으로 변환한다.
 *
 * LLM 출력은 형태가 흔들리므로 관용적으로 여러 모양을 복구한다:
 *  1) 완전한 spec: `{ root, elements }` — 그대로 사용.
 *  2) 레거시 `{ kind, payload }` — kind→타입 매핑으로 단일 element 로 감쌈.
 *  3) 래퍼 누락 elements 맵: `{ "<id>": { type, props } }` — 첫 키를 root 로 감쌈.
 *  4) 단일 element: `{ type, props }`(id 없음) — el 로 감쌈.
 * 어느 것에도 안 맞으면 null(호출부가 raw JSON 폴백).
 */

import type { Spec } from '@json-render/core';

import { A2UI_TYPE_BY_KIND } from './jsonrender';

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** json-render spec 형태인지(root 문자열 + elements 객체) 확인. */
function isSpec(value: Record<string, unknown>): boolean {
  return typeof value.root === 'string' && isPlainObject(value.elements);
}

/** json-render element 형태인지(type 문자열 보유) 확인. */
function isElement(value: unknown): value is { type: string } {
  return isPlainObject(value) && typeof value.type === 'string';
}

export function toSpec(component: unknown): Spec | null {
  if (!isPlainObject(component)) return null;

  // 1) 완전한 spec.
  if (isSpec(component)) {
    return component as unknown as Spec;
  }

  // 2) 레거시 {kind, payload}.
  const kind = typeof component.kind === 'string' ? component.kind : undefined;
  if (kind) {
    const type = A2UI_TYPE_BY_KIND[kind];
    if (!type) return null;
    const props = isPlainObject(component.payload) ? component.payload : {};
    return { root: 'el', elements: { el: { type, props } } };
  }

  // 3) 래퍼(root/elements) 누락 elements 맵 — 값이 전부 element 면 첫 키를 root 로 감싼다.
  const entries = Object.entries(component);
  const first = entries[0];
  if (first && entries.every(([, v]) => isElement(v))) {
    return {
      root: first[0],
      elements: component as unknown as Spec['elements']
    };
  }

  // 4) 단일 element 그 자체({ type, props }).
  if (typeof component.type === 'string') {
    const props = isPlainObject(component.props) ? component.props : {};
    return { root: 'el', elements: { el: { type: component.type, props } } };
  }

  return null;
}
