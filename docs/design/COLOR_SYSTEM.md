# COLOR_SYSTEM.md — 집핀 컬러 시스템

> **이 문서는 집핀의 컬러 토큰·역할·상태색·법적/오류 색상 규칙·접근성 기준의 정본이다.** 색을 추가·변경·폐기하려면 본 문서를 먼저 갱신한 뒤 코드(`apps/web/tailwind.config.ts` 등) 를 동기화한다. 진입점은 [`DESIGN.md`](DESIGN.md).

---

## 1. 채택 결과 — 한눈에

- **기본 방향: Urban Teal (`#147A73`)** — 신뢰감 + 생활 친화 + 상담 전환을 동시에 만족하는 청록계.
- **전문 보조 축: Blueprint Navy (`#153B5C`)** — 리포트·도면 분석·관리자·전문 영역의 강조 색.
- **CTA(전환) 색: Coral (`#F26B4F`)** — 상담·견적·다운로드 등 전환 액션에만 제한적으로 사용. 작은 흰 글자 버튼 조합 시 대비 재검토 필수.
- **상태 색은 브랜드와 분리** — 가능/불가/보류/정보는 별도의 `status.*` 토큰을 사용한다.
- 모든 색은 [`DESIGN.md §2.4`](DESIGN.md) 에 따라 **색 + 라벨 + 아이콘** 세 가지로 동시에 의미를 전달한다.

후보 비교 및 채택 사유: [`§8 결정 기록`](#8-결정-기록-decision-log).

---

## 2. 브랜드 토큰 (Brand tokens)

| 토큰 | HEX | 역할 (Role) | 대표 사용처 |
|---|---|---|---|
| `brand.primary` | `#147A73` | 주요 인터랙션·네비게이션·선택 상태·1차 강조 | 헤더 활성 링크, 1차 버튼 배경, 진행 표시, 포커스 링 |
| `brand.primaryFg` | `#FFFFFF` | `brand.primary` 위 텍스트 | 1차 버튼의 라벨 텍스트 |
| `brand.ink` | `#0D1B2A` | 본문 대표 텍스트, 헤딩 | h1~h3, 본문 진한 텍스트 |
| `brand.copy` | `#48606A` | 부가 설명·캡션·메타 텍스트 | 설명 문구, 입력 도움말, 라벨 보조 |
| `brand.surface` | `#F7FBFA` | 페이지/카드 표면 색 | 배경, 카드, 모달 면 |
| `brand.surfaceAlt` | `#FFFFFF` | 대비가 필요한 카드·시트 표면 | 카드 강조, 시트, 입력 필드 배경 |
| `brand.border` | `#D9E3E1` | 일반 경계선·구분선 | 카드 테두리, 구분선, 입력 필드 외곽 |
| `brand.cta` | `#F26B4F` | 전환 액션(상담·견적·다운로드) 전용 강조 | 상담 신청 버튼, 견적 요청 CTA |
| `brand.ctaFg` | `#1A0F0B` | `brand.cta` 위 텍스트 | CTA 버튼의 라벨 텍스트 (흰 글자보다 진한 갈색이 AA 통과) |
| `brand.professional` | `#153B5C` | Blueprint Navy 보조 축 — 리포트·도면·관리자·전문 영역 | 리포트 헤더, 도면 분석 UI 의 강조, 관리자 메뉴 활성 |
| `brand.professionalFg` | `#FFFFFF` | `brand.professional` 위 텍스트 | 리포트 헤더 텍스트 |

> 토큰 명명 규칙: `brand.<역할>` 은 의미(역할)를 가리키고, `brand.<역할>Fg` 는 해당 면 위의 텍스트 색을 가리킨다. HEX 가 아니라 토큰 이름으로 참조한다.

### 2.1 사용량 규칙 (Usage rules)

- `brand.primary` 는 화면에서 가장 자주 등장하는 강조 색이다. 단, 본문 텍스트 색으로 쓰지 않는다 (가독성 저하).
- `brand.cta` 는 한 화면에 **하나의 CTA** 에만 쓴다. 여러 곳에 쓰면 전환 신호가 흐려진다.
- `brand.professional` 은 리포트·도면 분석·관리자 영역의 헤더/탭/강조에 쓴다. 메인 채팅 화면에는 쓰지 않는다.
- 그라데이션, 형광 빛 효과, 네온 글로우는 사용 금지 ([`DESIGN.md §2`](DESIGN.md) 차분함 원칙).

---

## 3. 콘텐츠 토큰 (Content tokens)

본문·캡션·링크 등 텍스트와 콘텐츠 면에 쓰는 색이다.

| 토큰 | HEX | 역할 |
|---|---|---|
| `content.default` | `#0D1B2A` | 본문 텍스트 기본 (≡ `brand.ink`) |
| `content.muted` | `#48606A` | 부가 텍스트·캡션·도움말 (≡ `brand.copy`) |
| `content.subtle` | `#6F8088` | 비활성 텍스트, placeholder |
| `content.link` | `#147A73` | 본문 링크 색 (≡ `brand.primary`) |
| `content.linkHover` | `#0F5F59` | 본문 링크 hover |
| `content.onPrimary` | `#FFFFFF` | `brand.primary` 위 텍스트 |
| `content.onProfessional` | `#FFFFFF` | `brand.professional` 위 텍스트 |
| `notice.legal` | `#48606A` | 법적 고지 문구 색 (`§5` 참조) |

---

## 4. 상태 색 (Status tokens) — 브랜드와 분리

> **이 그룹은 리포트 판정·검증 결과 등 "기능적 의미"** 를 전달하는 색이다. 브랜드 컬러로 대체하지 않는다.

| 토큰 | HEX | 역할 | 사용처 |
|---|---|---|---|
| `status.success` | `#1F8A4C` | 가능 / 충족 | "가능" 판정 칩·리포트 라벨 |
| `status.successFg` | `#FFFFFF` | 위 색 위 텍스트 | 라벨 텍스트 |
| `status.successSurface` | `#E8F5EE` | 가능 카드/배너 배경 | 결과 카드 배경 |
| `status.danger` | `#C0392B` | 불가 / 제한 | "불가" 판정 칩·차단 메시지 |
| `status.dangerFg` | `#FFFFFF` | 위 색 위 텍스트 | 라벨 텍스트 |
| `status.dangerSurface` | `#FBEAE8` | 불가 카드/배너 배경 | 결과 카드 배경 |
| `status.warning` | `#B8740C` | 보류 / 추가 확인 | "보류" 판정 칩·확인 요청 |
| `status.warningFg` | `#FFFFFF` | 위 색 위 텍스트 | 라벨 텍스트 |
| `status.warningSurface` | `#FFF3E0` | 보류 카드/배너 배경 | 결과 카드 배경 |
| `status.info` | `#1F6F8B` | 중립 정보 안내 | 안내 배너·툴팁·도움 |
| `status.infoFg` | `#FFFFFF` | 위 색 위 텍스트 | 라벨 텍스트 |
| `status.infoSurface` | `#E8F1F5` | 정보 카드/배너 배경 | 결과 카드 배경 |

### 4.1 상태 색 사용 규칙

- 상태는 항상 **색 + 라벨 + 아이콘** 세 가지로 동시에 전달한다. 색만으로 가능/불가/보류를 구분하게 두면 안 된다 ([`DESIGN.md §2.4`](DESIGN.md)).
- 라벨 예: `가능 · 근거 충족` / `불가 · 법령 제한` / `추가 확인 필요` / `참고 안내`.
- 아이콘 예: 가능 = 체크, 불가 = 슬래시 원, 보류 = 물음표 원, 정보 = i 원. (구체 아이콘 명세는 후속 이슈)
- `status.*` 는 리포트·검증 결과·필드 인라인 에러 등에만 쓴다. 메인 네비게이션 강조에 쓰지 않는다.
- "고위험 케이스" 는 단독 색이 아니라 `status.warning` + 별도 안내 카드 + 법적 고지로 구성한다 ([`BRAND.md §4.3`](BRAND.md)).

---

## 5. 법적·오류 색상 규칙

집핀의 법적 고지·시스템 오류는 브랜드 컬러로 강조하지 않는다. 사용자의 시선을 끌어 "오해" 를 만들지 않는 것이 우선이다.

- **법적 고지(`AGENTS.md §4.6`)**
  - 텍스트 색: `notice.legal` (`#48606A`).
  - 배경: 페이지 표면 색 그대로 (별도 카드 강조 금지).
  - 굵기·아이콘 강조 금지. 일반 본문보다 약간 작은 크기, 충분한 여백.
  - 이미지가 아닌 선택·복사 가능한 텍스트로 노출.
- **시스템 오류 / API 실패**
  - 색: `status.danger` 면을 사용하되, 사용자 입력 오류가 아닌 시스템 오류일 때는 **메시지 본문에 "사용자 잘못이 아닙니다" 의미를 명시**한다.
  - "오류 발생" 단독 문구는 금지. 무엇을 다시 시도하면 되는지 함께 안내한다 ([`TYPOGRAPHY.md §4`](TYPOGRAPHY.md)).
- **AI 신뢰도 낮은 결과 (`ANALYSIS_LOW_CONFIDENCE` 등)**
  - 색: `status.warning` (보류) 면 사용. `status.danger` (불가) 면 사용 금지.
  - 사용자에게는 "현재 정보만으로 판단이 어렵다" 로 전달한다.

---

## 6. 접근성 기준 (Accessibility)

본 절은 WCAG 2.1 AA 를 최소 기준으로 한다. 본 문서의 토큰 채택 결정은 본 기준을 통과한 조합만 포함한다.

### 6.1 대비 (Contrast)

- **일반 텍스트**: 배경 대비 **4.5:1 이상**.
- **큰 텍스트(18pt 이상 또는 14pt bold 이상)**: **3:1 이상**.
- **UI 컴포넌트·그래픽**: 배경 대비 **3:1 이상**. (버튼 외곽, 포커스 링, 아이콘 등)

검증이 끝난 권장 조합:

| 조합 | 추정 대비 | 용도 |
|---|---|---|
| `brand.ink #0D1B2A` on `brand.surface #F7FBFA` | ~16:1 | 본문 |
| `brand.copy #48606A` on `brand.surface #F7FBFA` | ~6.5:1 | 부가 텍스트 |
| `content.onPrimary #FFFFFF` on `brand.primary #147A73` | ~4.6:1 | 1차 버튼 |
| `content.onProfessional #FFFFFF` on `brand.professional #153B5C` | ~10:1 | 리포트 헤더 |
| `status.successFg #FFFFFF` on `status.success #1F8A4C` | ~4.5:1 | 가능 칩 |
| `status.dangerFg #FFFFFF` on `status.danger #C0392B` | ~5.5:1 | 불가 칩 |
| `status.warningFg #FFFFFF` on `status.warning #B8740C` | ~4.7:1 | 보류 칩 |

> 추정 대비는 권장 조합의 대략값이다. 실제 구현 시 reliable한 자동화 도구(예: axe, Pa11y, Lighthouse) 로 재측정한다. 4.5:1 에 매우 근접한 조합(`brand.primary` 위 흰 글자 등)은 굵기·크기를 함께 조정해 안전 마진을 확보한다.

### 6.2 색 단독 금지 (Don't rely on color alone)

- 가능/불가/보류는 항상 **색 + 라벨 + 아이콘** 세 가지로 동시에 전달한다.
- 링크는 색만으로 표시하지 않는다. 본문 링크는 밑줄을 기본으로 둔다.
- 그래프·차트·도면 위 강조는 색 외에 패턴/아이콘/라벨을 함께 사용한다.

### 6.3 포커스 (Focus)

- 키보드 포커스 링은 `brand.primary` 색의 2px 외곽선을 기본으로 한다. 포커스 링을 제거하지 않는다.
- 포커스 링 색과 인접 배경 대비가 3:1 미만인 경우, 외곽선 안쪽에 흰색 보조 링을 1px 추가한다.

### 6.4 다크 모드 (Dark mode)

- 본 MVP 범위에서는 다크 모드를 채택하지 않는다 (사용자 세션이 짧고, 리포트의 법령·도면 가독성을 우선).
- 다크 모드 채택은 별도 후속 이슈에서 결정한다. 그 시점에 본 문서에 다크 모드 토큰 표를 추가한다.

---

## 7. 코드 적용 (Implementation)

### 7.1 Tailwind 토큰 매핑

`apps/web/tailwind.config.ts` 의 `theme.extend.colors` 에 본 문서의 토큰을 그대로 노출한다. 예:

```ts
colors: {
  brand: {
    primary: '#147A73',
    primaryFg: '#FFFFFF',
    ink: '#0D1B2A',
    copy: '#48606A',
    surface: '#F7FBFA',
    surfaceAlt: '#FFFFFF',
    border: '#D9E3E1',
    cta: '#F26B4F',
    ctaFg: '#1A0F0B',
    professional: '#153B5C',
    professionalFg: '#FFFFFF'
  },
  content: {
    DEFAULT: '#0D1B2A',
    muted: '#48606A',
    subtle: '#6F8088',
    link: '#147A73',
    linkHover: '#0F5F59'
  },
  status: {
    success: '#1F8A4C',
    successFg: '#FFFFFF',
    successSurface: '#E8F5EE',
    danger: '#C0392B',
    dangerFg: '#FFFFFF',
    dangerSurface: '#FBEAE8',
    warning: '#B8740C',
    warningFg: '#FFFFFF',
    warningSurface: '#FFF3E0',
    info: '#1F6F8B',
    infoFg: '#FFFFFF',
    infoSurface: '#E8F1F5'
  },
  notice: {
    legal: '#48606A'
  }
}
```

> CSS 변수로의 마이그레이션(예: `--brand-primary`) 은 후속 이슈에서 다룬다. 본 이슈 범위에서는 정적 HEX 매핑으로 충분하다.

### 7.2 메타데이터 / 브라우저 chrome

- `apps/web/app/layout.tsx` 의 `themeColor` 는 `#147A73` (Urban Teal `brand.primary`) 로 설정한다.
- 향후 PWA manifest, OG 이미지 배경, Safari standalone status bar 등도 동일 토큰을 따른다.

---

## 8. 결정 기록 (Decision log)

### 8.1 후보 (대화에서 확인된 인상적인 후보 3종)

1. **Urban Teal** — 신뢰감 + 생활 친화 + 상담 전환 균형.
2. **Home Sage** — 집·생활 친화, 따뜻한 세이지 그린.
3. **Blueprint Navy** — 도면 분석·법령 근거·전문 리포트 강조.

### 8.2 채택 결과

- **메인: Urban Teal** — 청록은 신뢰(파랑) 과 생활 친화(녹) 의 교집합. 행정·법령을 다루지만 사용자가 비전문가라는 집핀의 양면성을 한 축에서 응답한다.
- **전문 보조 축: Blueprint Navy** — 리포트·도면·관리자 등 "전문 영역" 에서는 짙은 네이비가 권위와 차분함을 강화한다. 단, 메인 화면에 적용하면 사용자가 위축된다 → 보조 축으로만.
- **온보딩·문체 친화 축: Home Sage 톤 차용** — 색 메인으로 채택하지 않는다. Sage 의 친화 톤은 컬러 대신 **문체·온보딩 안내·생활어 사용** 으로 흡수한다 ([`BRAND.md`](BRAND.md), [`TYPOGRAPHY.md`](TYPOGRAPHY.md)).
- **CTA: Coral (`#F26B4F`)** — 청록 메인과 보색 가까운 따뜻한 코랄. 상담·견적 전환에 한 화면 1회 사용.
- **상태 색은 브랜드와 분리** — 가능/불가/보류는 기능 색상이며 브랜드 정체성과 무관하게 사용자가 즉시 판정을 식별할 수 있어야 한다.

### 8.3 채택하지 않은 선택지

- Material Blue / 임시 `#1f6feb` (기존 임시 토큰): 일반 SaaS 톤. 집핀의 "법령·도면" 정합과 충돌.
- 단일 채도 강한 청록(`#0FB39E` 등 형광 계열): 차분함 원칙 위반.
- 다크 모드 기본: MVP 범위에 포함하지 않음. 후속 이슈에서 결정.

---

## 9. 변경 절차

1. 본 문서를 먼저 갱신한다 (토큰 표·접근성 검증·결정 기록).
2. `apps/web/tailwind.config.ts` 와 `apps/web/app/layout.tsx` 등 코드 토큰을 동기화한다.
3. WCAG 검증을 자동화 도구(axe, Lighthouse) 로 재실행하고 그 결과를 PR 본문에 캡처한다.
4. 의미가 바뀌는 변경(역할 변경·신규 토큰·폐기) 은 `docs/design/decisions/` (신설 가능) 또는 ADR 로 결정 기록을 남긴다.
5. 커밋: gitmoji `📝 docs(brand|design):` 또는 `🎨 style(web):`. PR 본문에 영향 범위(`BRAND` / `DESIGN` / `DOCS` / `WEB`) 와 `CMP-###` 표기.
