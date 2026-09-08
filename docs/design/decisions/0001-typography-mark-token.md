# 디자인 결정 0001 — 타입 스케일 `mark` 토큰(라벨 첨자 전용 10px)

- **상태**: **Accepted (2026-09-04)** — 운영자(사용자) 결정.
- **관련**: [`TYPOGRAPHY.md §2·§2.1`](../TYPOGRAPHY.md), [`DESIGN.md §4.7` 베타 표시](../DESIGN.md), `apps/web/lib/mantine-theme.ts`(`--jippin-fz-mark`), `apps/web/components/SiteShell.tsx`(`NavItem.badge`), PR #208.
- **영향 범위**: `DESIGN` · `DOCS` · `WEB`.

## 배경 / 문제

사전검토는 베타 운영 중이라 헤더 내비의 '사전검토' 항목에 베타 표시를 붙이기로 했다(운영자 지시, 2026-09-04).
시안 4종 — 아웃라인 배지 · 틴트 배지 · 텍스트 첨자 · 채움 배지 — 중 운영자는 **텍스트 첨자**를 골랐다.
필 배지 없이 라벨 뒤에 작은 대문자 `BETA` 만 붙이고, 툴팁은 두지 않는다.

첨자는 15px 라벨 옆에서 **10px** 이어야 첨자로 읽힌다. 그런데 타입 스케일에는 12px(`legal`) 미만 단계가 없었고,
`AGENTS.md §4.8.1` 은 컴포넌트에서 `fz` 로 새 크기를 발명하는 것을 금지한다. 하드코딩 `0.625rem` 은 PR 리뷰(Codex P1)에서
스케일 밖 크기로 지적됐다.

## 결정

| 항목 | 결정 |
|---|---|
| 토큰 | `mark` = `var(--jippin-fz-mark)` = `0.625rem`(10px), line-height 1, weight 600, uppercase 로마자 전용 |
| 용도 | **15px 이상 라벨 바로 옆에 붙는 첨자**(내비 `BETA`)에만. 문장·캡션·단독 라벨·한글에는 쓰지 않는다 |
| 스케일 위치 | 스케일에서 **유일한 12px 미만 단계**. `TYPOGRAPHY.md §2` 표에 행 추가, `§2.1` 에 사용 규칙 명문화 |
| 구현 | `mantine-theme.ts` resolver 변수로 노출. `SiteShell` `NavLink` 가 `fontSize: 'var(--jippin-fz-mark)'` 를 참조하고 `position: relative` 로 올려 라인 박스를 키우지 않는다(헤더 60px 불변, 로컬 계측 링크 높이 37px = 이웃 동일) |
| 접근성 | DOM 텍스트 `Beta` + CSS `text-transform: uppercase` → 링크 이름 `사전검토 Beta`. 색은 링크 색 상속(비활성 `brand.copy` / 활성 `brand.primary`)이라 상태 분기 없음 |

## 검토한 대안

- **`legal`(12px) 재사용** — 법적 고지 전용 토큰의 의미 오용. 15px 옆 12px 는 첨자가 아니라 두 번째 단어로 읽힌다. 기각.
- **`caption`(13px)** — 같은 이유로 기각.
- **필 배지(Mantine `Badge size="sm"`, 글자 10px)** — 배지 컴포넌트 자체가 이미 10px 글자를 쓰지만, 운영자가 배지 형태를 기각했다.
- **em 상대값(`0.667em`)** — 토큰 없는 크기 발명이라 `§4.8.1` 의 취지를 피하지 못한다. 기각.

## 결과

- 스케일 단계 +1(12px 미만 단계는 이 하나뿐). 남용 방지 규칙을 `TYPOGRAPHY.md §2.1` 에 명문화했다.
- 베타 해제는 `NAV_ITEMS` 의 `badge` 필드 제거만으로 끝난다. 토큰은 향후 같은 성격의 첨자(예: `NEW`)에 재사용할 수 있다.

## 후속

- `AGENTS.md §4.8.1` 의 허용 토큰 목록(`--jippin-fz-hero|display|legal`)은 `§7` 에 따라 **CEO 봉인 영역**이라 이 PR 에서 갱신하지 않았다.
  새 CEO 브리프 리비전에서 `mark` 를 목록에 추가한다. 그때까지 스케일 정본은 `AGENTS.md` 가 지정한 `TYPOGRAPHY.md §2` 다.
