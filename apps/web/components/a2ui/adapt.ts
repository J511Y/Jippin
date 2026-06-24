/**
 * 에이전트가 보내는 UI 컴포넌트를 json-render `Spec` 으로 변환한다.
 *
 * 두 포맷을 받는다(백엔드 배포 과도기 하위호환):
 *  1) json-render spec: `{ root, elements }` — 그대로 사용.
 *  2) 자체 레거시: `{ kind, payload }` — kind→타입 매핑으로 단일 element spec 으로 감쌈.
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

export function toSpec(component: unknown): Spec | null {
  if (!isPlainObject(component)) return null;
  if (isSpec(component)) {
    return component as unknown as Spec;
  }
  const kind = typeof component.kind === 'string' ? component.kind : undefined;
  if (!kind) return null;
  const type = A2UI_TYPE_BY_KIND[kind];
  if (!type) return null;
  const props = isPlainObject(component.payload) ? component.payload : {};
  return { root: 'el', elements: { el: { type, props } } };
}
