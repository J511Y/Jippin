# DESIGN.md — 집핀 디자인 SSOT 진입점

> **이 문서가 집핀(Jippin)의 디자인 시스템 정본(Single Source of Truth)의 진입점이다.**
> UI·문구·리포트·법적 고지 관련 작업을 시작하기 전에 반드시 이 문서와 그 하위 문서들을 먼저 읽는다. 임의로 색·폰트·문체·법적 고지 문구를 바꾸지 않는다.

- 상위 가이드: [`AGENTS.md §1`](../../AGENTS.md) 우선순위 1번 다음 단계로 본 문서를 읽는다.
- 정본 4종: [`BRAND.md`](BRAND.md) · [`COLOR_SYSTEM.md`](COLOR_SYSTEM.md) · [`TYPOGRAPHY.md`](TYPOGRAPHY.md) · 본 문서(원칙·인덱스)
- 현재 적용 위치: [`apps/web/tailwind.config.ts`](../../apps/web/tailwind.config.ts) · [`apps/web/app/layout.tsx`](../../apps/web/app/layout.tsx)

---

## 1. 우리는 누구를 위해 디자인하는가

집핀의 사용자는 **공동주택에 살고 있고, 비내력벽 철거(발코니 확장 등) 행위허가를 처음 마주하는 비전문가**다. 이 사람은:

- 평면도·구조도를 처음 본다. 도면 용어를 모른다.
- 행정 절차(관할 기관·신청 양식·필요 서류)에 익숙하지 않다.
- 인테리어 업체 견적이 합리적인지 판단할 기준이 없다.
- "지금 이게 가능한 거냐 아니냐"만 빠르게 알고 싶어 하면서도, 잘못 결정해 공사가 중단·원상복구되는 상황을 두려워한다.

이 사용자에 대한 우리의 응답은 **"차분한 전문가가 생활어로 사전검토를 설명해주는 경험"** 이다. 그 외 모든 시각/언어 선택은 이 응답을 강화하거나 약화시킨다.

---

## 2. 디자인 원칙 (Design Principles)

본 원칙은 모든 디자인·문구·컬러·폰트 결정의 상위 기준이다. 하위 문서(BRAND/COLOR_SYSTEM/TYPOGRAPHY)는 본 원칙에서 파생된 규칙이다.

### 2.1 근거가 보이게(Show your work)

- 판정에는 **근거(법령·고시 조항·도면 위치)** 가 함께 보인다.
- 결과 화면은 "가능/불가/보류"의 결론과 그 근거를 같은 시야에 배치한다.
- 근거가 부족할 때는 결론을 만들지 않고 "추가 확인 필요"로 멈춘다. 확신을 위조하지 않는다.

### 2.2 생활어 우선(Plain-Korean first)

- 전문 용어를 그대로 쓰지 않는다. 첫 등장 시 생활어로 설명하고, 정식 명칭은 괄호/툴팁으로 부기한다.
- 예: "비내력벽(건물 무게를 직접 받지 않는 벽)" / "행위허가(공동주택에서 구조 변경 시 받아야 하는 허가)".
- 자세한 문체 규칙은 [`TYPOGRAPHY.md §4 문체 가이드`](TYPOGRAPHY.md) 참조.

### 2.3 과장 금지·확정 금지(No false certainty)

- 집핀은 **사전검토**이지 행위허가 자체가 아니다. "확정", "보장", "100%", "통과" 같은 표현을 단독으로 쓰지 않는다.
- 모든 결과 화면·다운로드 산출물에는 [`AGENTS.md §4.6`](../../AGENTS.md) 의 법적 고지 문구가 반드시 포함된다.
- 색·강조·아이콘 어느 것도 법적 효력을 시사해서는 안 된다.

### 2.4 색은 의미를 강화하되 단독 전달은 금지(Color reinforces, never alone)

- 브랜드 색과 상태 색을 분리한다. 상세는 [`COLOR_SYSTEM.md`](COLOR_SYSTEM.md).
- 가능/불가/보류 상태는 **색 + 라벨 + 아이콘** 세 가지로 동시에 전달한다. (WCAG 색맹·저시력 사용자 대응)

### 2.5 모바일·짧은 세션 우선(Mobile-first, short-session-first)

- 사용자는 한 번의 채팅 세션에서 판정-근거-다음 행동을 모두 본다.
- 히어로 카피·과도한 마케팅 헤더는 쓰지 않는다. 화면의 1순위는 항상 "지금 사용자가 답을 받고 있는 질문"이다.

### 2.6 전문성은 보조 축으로(Professional accent, not primary face)

- 리포트·도면 분석·관리자 화면 같은 전문 영역에는 Blueprint Navy 보조 축을 쓴다. 메인 화면을 전문가용처럼 어둡고 무겁게 만들지 않는다.

---

## 3. 정본 문서 인덱스

| 문서 | 무엇을 정한다 | 누가 갱신하는가 |
|---|---|---|
| [`BRAND.md`](BRAND.md) | 브랜드 약속·사용자 감정·성격 축·톤앤매너·금지 톤 | Frontend Lead + CEO 승인 |
| [`COLOR_SYSTEM.md`](COLOR_SYSTEM.md) | 브랜드 컬러 토큰·상태색·법적/오류 색상 규칙·WCAG 접근성 기준 | Frontend Lead (React Engineer 보조) |
| [`TYPOGRAPHY.md`](TYPOGRAPHY.md) | 한국어 우선 폰트 스택·타입스케일·문체 규칙·좋은/나쁜 예 | Frontend Lead |
| 본 문서 | 디자인 원칙·문서 인덱스·변경 절차 | Frontend Lead |

> 모순이 있으면 우선순위: **(이슈 본문) > (CEO 브리프) > (본 DESIGN.md 원칙) > (BRAND.md) > (COLOR_SYSTEM.md / TYPOGRAPHY.md)**. 모순 자체는 PR 또는 후속 이슈로 보고한다.

---

## 4. 작업 가이드 — 에이전트·사람 공통

### 4.1 색을 바꾸려는가

1. [`COLOR_SYSTEM.md`](COLOR_SYSTEM.md) 의 토큰 표를 먼저 갱신한다.
2. `apps/web/tailwind.config.ts` 와 `apps/web/app/layout.tsx` 의 적용 위치를 동기화한다.
3. WCAG AA 4.5:1 (일반 텍스트) / 3:1 (UI 컴포넌트) 대비를 새 조합으로 다시 검증한다.
4. 의미가 바뀌는 변경(예: brand.cta 도입/폐기, status 색 매핑 변경)은 별도 ADR 또는 디자인 결정 기록을 남긴다.

### 4.2 문구를 바꾸려는가

1. [`TYPOGRAPHY.md §4 문체 가이드`](TYPOGRAPHY.md) 와 [`BRAND.md §4 톤앤매너`](BRAND.md) 를 동시에 확인한다.
2. 법적 고지 문구(`AGENTS.md §4.6`) 는 어떤 화면·문서에서도 단독으로 변경하지 않는다. 변경이 필요하면 CEO/Security Lead 가 함께 검토하는 별도 이슈를 연다.

### 4.3 폰트·타입스케일을 바꾸려는가

1. [`TYPOGRAPHY.md`](TYPOGRAPHY.md) 정본을 먼저 갱신한다.
2. 한국어 가독성(특히 리포트의 숫자·법령 조항·도면 좌표)에 회귀가 없는지 확인한다.

### 4.4 브랜드 자체를 재정의하려는가

- 본 문서와 `BRAND.md` 의 §1 브랜드 약속은 **CEO 봉인 영역**이다. 변경하려면 새 CEO 브리프 리비전이 필요하다.
- 색·폰트 등 표현 영역은 ADR 또는 디자인 결정 기록(`docs/design/decisions/` 신설 가능) 으로 변경한다.

### 4.5 레이아웃 컨테이너 폭 (sm vs lg) — 기본은 lg

`SiteShell` 의 `mainContainerSize` 가 라우트별 메인 컨테이너 폭을 정한다. 폭을 자꾸 `sm` 으로 잡는 혼동을 막기 위한 정본 규칙:

- **기능 페이지는 헤더와 같은 `lg` 를 쓴다.** 목록·상세·리포트·결과 화면, 우리집 체크(`/home-check/**`) **입력 폼 포함** 전반이 `lg` 다. 새 사용자 대면 기능을 추가하면 기본은 `lg` (= `SiteShell` 의 `WIDE_ROUTE_PREFIXES` 에 prefix 등록).
- **`sm` 은 "단일 입력 폼" 한정 예외다.** 좁은 폭이 입력 가독성에 분명히 유리한 경우(예: `/sessions/new`)만 `NARROW_FORM_PREFIXES` 에 **명시적으로** 넣는다. "폼이니까 sm" 을 기본값으로 적용하지 않는다.
- 새 라우트를 어디에도 등록하지 않으면 기본 `sm` 으로 떨어진다. 따라서 사용자 대면 페이지를 추가할 때는 `WIDE_ROUTE_PREFIXES` 등록을 빠뜨리지 않는다(누락 = 의도치 않은 sm).

---

## 5. 본 문서의 변경 절차

- 본 SSOT 4종(`DESIGN.md` / `BRAND.md` / `COLOR_SYSTEM.md` / `TYPOGRAPHY.md`) 의 변경은 gitmoji `📝 docs(brand|design):` 커밋과 PR 본문의 영향 범위(`BRAND` / `DESIGN` / `DOCS` / 필요 시 `WEB`) 명시로만 진행한다.
- PR 본문에 Paperclip 이슈 ID(`CMP-###`) 와 변경 사유를 적는다.
- 색·폰트·문구의 "의미" 가 바뀌는 경우(역할 변경, 새 토큰 도입, 톤 재정의)는 ADR 또는 `docs/design/decisions/` 결정 기록을 함께 남긴다.
