# jippin-seumteo-worker

세움터(eais.go.kr) 건축물대장 발급 자동화 워커. **CODEF 대체**(ADR-0009).
Playwright headless Chromium 으로 로그인·발급·CLIP 리포트 추출·PDF 저장을 수행하고,
CODEF 와 동형(同型)인 결과를 apps/api(jippin)에 돌려준다.

- apps/api 는 화면 진입 시 Flycast(`http://jippin-seumteo-worker.flycast/healthz`)로
  scale-to-zero worker를 깨우고, ready 확인 뒤 `.internal:8080`으로 발급 잡을 직결한다.
- 세움터 계정은 운영자 합의로 **분리하지 않고 단일 계정**(`<세움터-계정ID>`)만 사용한다. 로그인은
  아이디/비밀번호(인증서·간편인증·보안문자 없음 — 발급 정찰로 확인).
- 발급된 PDF 는 결과의 `original_pdf_base64` 로 반환되며, apps/api 의 기존
  `home_check._store_pdfs` 가 Supabase Storage(`home-check-docs`)에 그대로 저장한다.

## 아키텍처 / 왜 별도 앱인가

apps/api(jippin) 본체는 shared-cpu-1x **1GB** 이고 gunicorn·langgraph·WeasyPrint 가 이미
상주한다. 헤드리스 Chromium(단일 페이지 렌더 ~0.5–1GB)을 같은 머신에 올리면 OOM 이므로,
**프로세스가 격리된 별도 Fly 앱**(2GB + swap)으로 분리한다. app 이름이 다르면 Machine·secrets·
IP·릴리즈가 완전히 독립이다.

```
apps/api (app="jippin")                     apps/seumteo-worker (app="jippin-seumteo-worker")
 home_check → healthz(warm-up) ──flycast──▶  scale-to-zero 기동 + browser ready
 home_check → POST /jobs/building-register ──.internal──▶    로그인 → 발급 → CLIP 추출 → PDF
   (services/seumteo/client.py)
   결과 = ExclusivePartResult/BuildingHeadingResult ◀────────  결과(JSON, CODEF 동형) + pdf_base64
```

## 발급 플로우 (실측 엔드포인트 계약)

`<세움터-계정ID>` 계정으로 「여의대방로43나길 25 104동 504호」를 끝까지 발급하며 네트워크를 캡처해 도출.
2~8 은 로그인 세션 위 in-page fetch(JSON), 1(로그인)과 9(발급)만 DOM 상호작용(리포트 뷰어 param 이 클라이언트측 AES).

**로그인은 능동 인증 확인 기반이다** (SPA 폼 유무 휴리스틱 폐지 — 2026-07-09 수정):

1. 세션 유효성은 in-page fetch `POST /cba/CBAAZA02R01` (세션 확인 엔드포인트) 로 **능동 검증**한다. 유효하면 로그인 생략(storage_state 재사용 포함).
2. 무효면 로그인 페이지(`eais_login_path` = `/moct/awp/abb01/AWPABB01F13`)로 `goto` → Nuxt CSR hydrate 를 `#membId` `wait_for_selector` 로 대기(`login_form_timeout_ms`, 기본 8s — 폼 부재를 "이미 로그인"으로 오판하던 버그의 핵심 수정) → 폼 입력 + 버튼 클릭 → 다시 `/cba/CBAAZA02R01` 로 성공 확인.
3. keep-alive 슈퍼바이저가 `seumteo_session_keepalive_seconds`(기본 1500s) 주기로 세션을 능동 검증해 ~60분 TTL 만료를 예방한다 (0 = 비활성).

| # | 단계 | 엔드포인트 | 요지 |
|---|---|---|---|
| 1 | 로그인 | 로그인 페이지 `goto` + DOM 폼(`#membId`/`#pwd`) → 검증 `POST /cba/CBAAZA02R01` | 캡차·인증서 없음. 위 절차 참조 |
| 2 | 주소검색 | `POST search.eais.go.kr/bldrgstmst/_search` (ES) | `multi_match(jibunAddr, roadAddr^3)` → `mgmUpperBldrgstPk` |
| 3 | 동목록 | `POST search.eais.go.kr/bldrgsttitle/_search` | `filter mgmUpperBldrgstPk` → 표제부PK |
| 4 | 호목록 | `POST search.eais.go.kr/bldrgstexpos/_search` | `filter 표제부PK` → 전유부PK, recapTitlePk |
| 5 | 조회 | `POST /bci/BCIAAA02R01`·`/bci/BCIAAA02R04` | 위치코드(sigunguCd/bjdongCd/mnnm/slno)·전유면적 |
| 6 | 담기 | `POST /bci/BCIAAA02C01` | `regstrKindCd`(4전유/3표제)+loc*+**`ownrYn:"N"`**(소유자 미표시) |
| 7 | 장바구니 | `POST /bci/BCIAAA02R05` | `pbsvcResveDtlsSeqno` |
| 8 | 신청 | `POST /bci/BCIAZA02S01` → `/bci/BCIAAA06R01` | 신청 전후 접수번호 차집합으로 새 `pbsvcRecpNo` 식별, `progStateCd=91` |
| 9 | 발급 | DOM: `BCIAAA04L01` "발급" 링크 → `/report/BCIAAA04V01` | **CLIP Report** 캔버스 뷰어(AnySign 불필요) |

리포트 데이터는 뷰어가 `POST /report/RPTCAA02R02`(JSON, base64 `viewData`)로 받아 캔버스에
그린다. 텍스트는 (1) `paintReportText` 후킹(`add_init_script` 로 렌더 전 주입) + (2) `viewData`
디코드로 확보하고, "위반건축물" 부분문자열로 위반 판정한다. PDF 는 뷰어 툴바 "PDF 저장"
버튼(`.report_menu_pdf_button`) 클릭 → 다운로드로 받는다.

## 로컬 PoC (배포 없이 실주소 검증)

```powershell
cd apps/seumteo-worker
pip install -r requirements.txt
python -m playwright install chromium

# 권장 경로: 사람이 브라우저에서 1회 직접 로그인해 세션을 저장한다(자동화가 비밀번호를
# 입력하지 않음). 저장 위치 = config.seumteo_storage_state_path (기본 .auth/state.json).
python login.py

# 이후 발급 검증은 저장된 세션을 재사용한다. (storage_state 없으면 SEUMTER_ID/PASSWORD 폴백)
python poc.py "서울특별시 영등포구 여의대방로43나길 25" 104동 504호 exclusive
python poc.py "서울특별시 영등포구 여의대방로43나길 25" 104동 "" heading
# 위반건축물(노란딱지) 케이스 주소로도 반드시 검증(위반 검출 확인)

# 로그인된 탭을 그대로 재사용해 발급·CLIP 추출까지 사람이 지켜보며 검증할 때:
python attended_poc.py "<도로명주소>" <동> <호>
```
`out/exclusive.pdf`·`out/heading.pdf` 저장 + 콘솔에 위반여부/필드 출력. `HEADLESS=1` 로 헤드리스 강제. (프로덕션 Fly 는 storage_state 파일이 없으므로 secrets 의 ID/비번 자동 로그인 — 무변경.)

## 배포 (리포 루트에서 — build context = 이 디렉토리)

```bash
fly apps create jippin-seumteo-worker                 # 최초 1회
fly secrets set -a jippin-seumteo-worker SEUMTER_ID=<세움터-계정ID> SEUMTER_PASSWORD=****** SEUMTEO_WORKER_TOKEN=$(openssl rand -hex 24)
fly deploy apps/seumteo-worker --flycast --remote-only --ha=false   # **반드시 단일 머신**
fly scale count 1 -a jippin-seumteo-worker            # HA 로 2대 뜨지 않게 1대 고정
fly ips list -a jippin-seumteo-worker                 # private IPv6 만 있어야 함(public 없음)
```

> Docker 베이스 이미지는 `python:3.13-slim-bookworm` 으로 **고정**한다 (`Dockerfile` 참조) —
> `slim`(trixie 승격) 빌드 깨짐 방지. 태그를 `slim` 으로 되돌리지 말 것.

> ⚠️ **단일 머신 필수(단일 세움터 계정)**: `fly deploy` 기본값은 HA 2머신인데, 두 머신이
> 하나의 `<세움터-계정ID>` 계정·서버측 장바구니를 공유하면 한 머신의 `_isolate_cart` D01 삭제가 다른
> 머신 발급 항목을 지우고 발급이 레이스한다(프로세스 내 `render_semaphore`·concurrency 가드는
> 머신 간 보호 못 함). **`--ha=false` + `fly scale count 1`** 로 정확히 1머신만 유지한다.
그다음 apps/api(jippin)에:
```bash
fly secrets set -a jippin SEUMTEO_ENABLED=true SEUMTEO_WORKER_URL=http://jippin-seumteo-worker.flycast SEUMTEO_WORKER_JOB_URL=http://jippin-seumteo-worker.internal:8080 SEUMTEO_WORKER_TOKEN=<위와 동일>
```
`SEUMTEO_ENABLED=true` 순간 home-check 가 CODEF 대신 이 워커를 쓴다. 롤백은 `false`.

> **scale-to-zero 유지**: `min_machines_running=0`을 유지한다. `/home-check/new` 진입 시
> Flycast health probe가 worker를 깨우고, 실제 발급은 browser ready 이후 `.internal`로 보내므로
> cold-start와 Flycast 프록시 요청 상한을 분리한다. 제출 경로도 ready를 다시 확인해 사용자가
> 화면 진입 직후 제출해도 안전하다. 워커 `JOB_DEADLINE_MS=120000`은 API 180초 상한보다
> 짧아 긴 발급이 내부 55초 상한에 잘리는 것을 막는다.

## PoC 검증 체크리스트 (실주소로 확인 후 조정)

2차 실측(용인 기흥더샵프라임뷰)으로 아래 2건은 **발견·수정 완료**:
- ✅ **`untClsfCd` 건물별 가변**(삼환=1020/기흥더샵=1118) — ES `_source.untClsfCd` 읽어 R01/R04 threading. 하드코딩 시 R01 빈 결과.
- ✅ **in-page fetch `credentials:'same-origin'`** — `'include'` 면 교차출처 ES 가 CORS 실패.

나머지는 헤드리스 실환경에서 확인·튜닝한다:
- [ ] **7단계 신청(S01)** 이 in-page fetch 로 성공하는가 — 앱이 추가 헤더/선행콜을 요구하면 flow.py `_submit` 보강.
- [ ] **단일 세션 장바구니 격리** — 이전 잡 잔여 항목이 섞이지 않는가(`_cart_list` 필터 검증).
- [ ] **위반건축물 검출** — 위반 케이스 주소에서 `violation_status=="위반건축물"` 나오는가.
- [ ] **PDF 다운로드** — "PDF 저장" 이 다운로드로 떨어지는가(아니면 `clip._capture_pdf` 경로 B).
- [ ] **전유부 세부(용도/구조/층)** — 필요 시 리포트 텍스트 파싱 보강(현재 면적은 JSON 에서 확보).
- [ ] **동/호 자동매칭** — ES 유일매칭 실패(복수/0건) 시 UX(현재 not_found; 후속으로 needs_input 후보 제시 가능).

## 파일

- `src/main.py` — FastAPI + Playwright lifespan, `POST /jobs/building-register`
- `src/browser.py` — 로그인 세션 상주 브라우저 매니저(능동 세션 검증 + keep-alive + CLIP init script 주입)
- `src/flow.py` — 1~9 단계 오케스트레이션(in-page fetch + DOM 발급)
- `src/clip.py` — CLIP Report 텍스트/위반/PDF 추출
- `src/models.py`·`src/config.py` — HTTP 계약·설정
- `poc.py` — 로컬 단건 검증
- `login.py` — 사람이 1회 직접 로그인해 storage_state 저장(로컬 세션 재사용용)
- `attended_poc.py` — 로그인한 탭을 그대로 재사용하는 유인(attended) 발급 검증
