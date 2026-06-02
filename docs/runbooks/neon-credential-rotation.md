# Runbook — Neon Postgres 자격증명 회전

> **⚠ TRANSITIONAL (2026-06-02)**
>
> 본 런북은 **Neon project 가 잔존하는 동안 (cutover 완료 전) 유효** 하다. ADR-0004 (Neon → Supabase 전환, Proposed) 의 cutover PR 머지 + Neon project 폐기 시점에 본 런북은 archive (`docs/runbooks/_archive/`) 로 이동한다.
>
> Supabase project 의 service role key / DB password 회전은 별도 Supabase 회전 런북 (후속 이슈 — DevOps Lead) 에서 다룬다. 본 런북을 Supabase 에 그대로 적용하지 말 것. 단, **시크릿 노출·이탈자 대응의 일반 절차**(§0 사전 체크리스트, 코드/이슈/PR 본문 스캐닝, 사고 코멘트) 는 그대로 참조 가능하다.

- 정본 책임자: **Security Lead** (1차) · **Database Engineer / CEO** (실행 권한 보유자)
- 관련: CEO 브리프 §5.1·§8 R1, AGENTS.md §4.4, ADR-0001 §4 (ADR-0004 부분 supersede 진행 중), CMP-533, **CMP-602 (Supabase 전환 — 본 런북 한시 잔존)**
- 목표 소요: **30분 이내** (콘솔 작업 5분 + 환경 전파 15분 + 검증 10분)
- 트리거:
  1. **즉시 회전 (R1)** — CEO 브리프 §5.1 의 평문 노출된 Neon 비밀번호 (`npg_CNDw…` 접두; 정본은 CEO 브리프 참조) 회전. **본 작업이 본 런북의 첫 적용 케이스**.
  2. **정기 회전** — 90 일마다 (NFR-SEC-001 보완 정책).
  3. **사고 대응** — 시크릿 스캐너(`tools/secret-scan/scan.py`) 또는 gitleaks 가 신규 `npg_*` 검출.
  4. **이탈자** — Neon Console 접근권한 보유자가 팀에서 이탈할 때.

> **법적 / 운영 고지**: 회전 작업은 활성 세션이 일시적으로 끊긴다. MVP(30 세션 가정) 에서는 영향 미미하지만 P1+ 운영에서는 사전 공지 후 진행.

---

## 0. 사전 체크리스트 (작업 시작 전 3분)

- [ ] 본인이 Neon Console (https://console.neon.tech) **Project Owner** 또는 **Admin** 권한 보유자인가? — 아니라면 CEO 또는 DBA 에게 본 런북을 위임할 것.
- [ ] 환경 변수가 전파되어야 하는 모든 위치를 확인했는가?
  - 로컬: 각 개발자 머신의 `.env` / `apps/api/.env` / `apps/web/.env.local`
  - CI: GitHub Actions Repository / Organization secrets — `DATABASE_URL`, `DATABASE_POOL_URL`
  - 배포 타깃: D6 결정 후 Vercel / Cloud Run / EC2 / Lightsail 시크릿 매니저 (현 시점에는 미배포)
  - 백업/모니터링: Neon `pgdump` 자동 백업 잡, 외부 BI 도구 — 본 프로젝트는 아직 없음
- [ ] 사용자에게 5 분 다운타임 공지가 필요한가? — MVP 단계에서는 불필요.
- [ ] 회전 시작 직전 시각을 기록: `___:___ UTC` (Slack #security 또는 이슈 댓글)

---

## 1. Neon Console 에서 비밀번호 회전 (5 분)

1. https://console.neon.tech 로그인.
2. 좌측에서 **Project 선택** (집핀 프로젝트, host prefix `ep-empty-heart-aolzk9rl`).
3. 좌측 메뉴: **Branches** → `main` 브랜치 → **Roles & Database** 탭.
4. `neondb_owner` 역할의 우측 `⋯` 메뉴 → **Reset password**.
5. Neon 이 새 비밀번호를 생성한다. **이 화면을 떠나기 전 즉시 복사** — 다시 표시되지 않는다.
   - 형식: `npg_[A-Za-z0-9]{12,16}` (예: `npg_REDACTED_NEW_PW_12CH`)
6. **두 connection string 모두 복사** (Connection Details 패널):
   - Direct(non-pooler): `postgresql://neondb_owner:<NEW_PASSWORD>@ep-empty-heart-aolzk9rl.c-2.ap-southeast-1.aws.neon.tech/neondb?sslmode=require`
   - Pooler: `postgresql://neondb_owner:<NEW_PASSWORD>@ep-empty-heart-aolzk9rl-pooler.c-2.ap-southeast-1.aws.neon.tech/neondb?sslmode=require`
7. **저장 위치**: 1Password / 1pass team vault 의 `집핀 / Neon main / neondb_owner` 항목에 즉시 붙여넣고 **이전 값은 archived 상태로 보존**(audit trail).

> Neon 의 비밀번호 회전은 즉시 적용된다. **이 시점부터 모든 활성 세션은 새 비밀번호로 재인증해야 한다.**

---

## 2. 로컬 환경 (.env) 갱신 (2 분, 개발자당)

각 개발자 머신에서 (`<NEW_PASSWORD>` 자리에 §1 에서 복사한 새 비밀번호 붙여넣기):

```bash
# apps/api/.env (FastAPI)
DATABASE_URL=postgresql://neondb_owner:<NEW_PASSWORD>@ep-empty-heart-aolzk9rl.c-2.ap-southeast-1.aws.neon.tech/neondb?sslmode=require
DATABASE_POOL_URL=postgresql://neondb_owner:<NEW_PASSWORD>@ep-empty-heart-aolzk9rl-pooler.c-2.ap-southeast-1.aws.neon.tech/neondb?sslmode=require
```

검증:

```bash
cd apps/api
uv run python -c "from app.core.db import healthcheck; import asyncio; print(asyncio.run(healthcheck()))"
# 또는 (서버 부팅 후)
curl http://localhost:8000/healthz
# {"status":"ok","db":"ok",...} 가 돌아오는지 확인
```

새 비밀번호가 받아들여지지 않으면:
- 5 분 정도 Neon DNS / 컴퓨트 cold-start 대기
- 그래도 실패하면 §5 롤백 절차로

---

## 3. .env.example 갱신 (한 번만, 0.5 분)

`.env.example` / `infra/compose/.env.example` 의 placeholder 가 평문 비밀번호를 흉내내지 않도록 한다.

```env
# apps/api/.env.example  /  infra/compose/.env.example
DATABASE_URL=postgresql://neondb_owner:<NEW_PASSWORD>@ep-empty-heart-aolzk9rl.c-2.ap-southeast-1.aws.neon.tech/neondb?sslmode=require
DATABASE_POOL_URL=postgresql://neondb_owner:<NEW_PASSWORD>@ep-empty-heart-aolzk9rl-pooler.c-2.ap-southeast-1.aws.neon.tech/neondb?sslmode=require
```

> 위 `<NEW_PASSWORD>` placeholder 는 `tools/secret-scan/patterns.yml` 의 db-url 패턴이 negative lookahead 로 인식해 차단하지 않는다. (다른 허용 형식: `****`, `xxxx`, `password`, `REDACTED`, `${ENV_VAR}`.)

---

## 4. CI / 배포 환경 시크릿 갱신 (10 분)

### 4.1 GitHub Actions

본 레포의 모든 워크플로(`.github/workflows/`) 가 사용하는 secrets:

- `DATABASE_URL` (non-pooler)
- `DATABASE_POOL_URL` (pooler)

설정 위치: `Settings → Secrets and variables → Actions → Repository secrets`

```text
1. 두 secret 의 Update 버튼으로 새 값 붙여넣기
2. 마지막 수정 시각이 회전 시각보다 뒤에 있는지 확인
3. 진행 중인 PR 워크플로가 있다면 재실행 (Re-run jobs) — 캐시된 secret 은 없으므로 즉시 새 값 사용
```

### 4.2 Vercel (apps/web 프론트엔드, 현 시점 미배포)

> ADR-0001 §8 T7: 클라우드는 D6 결정 후. 현 시점에는 Vercel 배포 없음.
> 향후 배포되면 본 섹션을 활성화 — Vercel Dashboard → Project → Settings → Environment Variables 에 `DATABASE_URL`, `DATABASE_POOL_URL` 갱신.

### 4.3 클라우드 인프라 (apps/api, 현 시점 미배포)

> ADR-0001 §8 T7: D6 결정 전까지 로컬 docker-compose 만 보증. 배포 환경 갱신은 D6 후속 이슈에서 본 런북에 추가.

---

## 5. 사고 대응 — 비밀번호가 외부 노출된 정황이 있을 때

### 5.1 즉시 (5 분 내)

1. **새 비밀번호로 회전** (§1).
2. Neon Console → **Operations / History** 탭에서 의심 시간대의 접속 IP 를 확인.
3. Slack `#security` 채널 또는 Paperclip 이슈에 인시던트 코멘트 (`severity=high`).

### 5.2 1 시간 내

1. **데이터 변경 감사**: 의심 시간대 동안의 INSERT/UPDATE/DELETE 를 조사한다.
   ```sql
   -- 의심 시간대 동안 변경된 행이 있는지 (테이블별)
   SELECT relname, n_tup_ins, n_tup_upd, n_tup_del
   FROM pg_stat_user_tables;
   ```
   - PII 테이블 (`users`, `leads`) 에 비정상 갱신이 있으면 NFR-SEC-003(PII 보호) 인시던트.
2. **로그 보존**: Neon 로그(접근 IP, 쿼리 수) 를 PDF / CSV 로 다운로드해 보관.
3. **법적 검토 트리거**: 개인정보보호법 §34 통지 요건(개인정보 1,000건 이상 유출 또는 민감정보) 에 해당하면 CEO / 법무 즉시 호출.

### 5.3 24 시간 내

1. 노출 경로 사후 분석 (인시던트 코멘트로 기록).
2. 본 런북 / `docs/runbooks/security-policy.md` 갱신 (재발 방지 룰 추가).
3. 시크릿 스캐너 패턴이 차단했어야 했는데 놓쳤다면 `tools/secret-scan/patterns.yml` 보강.

---

## 6. 검증 체크리스트 (회전 종료 직전)

- [ ] 로컬 `apps/api/.env` 의 두 URL 갱신 + `curl /healthz` 200
- [ ] GitHub Actions `DATABASE_URL`, `DATABASE_POOL_URL` 갱신 시각 ≥ 회전 시각
- [ ] CI 워크플로(`ci.yml`, `secret-scan.yml`) 의 가장 최근 실행이 success
- [ ] `tools/secret-scan/scan.py` 전체 트리 스캔이 새 비밀번호를 잡지 못함 (= 코드에 평문 없음)
- [ ] 1Password vault 의 이전 값 항목이 `archived` 로 이동되었고 새 값이 `primary`
- [ ] Slack `#security` 또는 Paperclip 이슈에 회전 완료 코멘트 (`회전 완료. 새 비번 prefix: npg_REDA...`)
- [ ] 이전 비밀번호로 접속 시도가 실패하는지 확인 (예: 이전 `.env` 백업으로 부팅 → 401)

---

## 7. 본 회전의 최초 적용 — CMP-533 R1 대응

**컨텍스트**:
- CEO 브리프 §5.1 / §8 R1 이 평문 노출한 Neon 비밀번호(접두 `npg_CNDw…`, 본 런북에서는 마스킹하여 표기 — 정본은 CEO 브리프 / 1Password)가 본 회전의 회전 대상이다.
- 본 패스워드는 git history (브리프 문서) 와 Paperclip 이슈 메타데이터(외부 시스템) 둘 모두에 평문 존재한다 → 회전이 완료될 때까지 위험은 유효하다.

**실행 결정 (CMP-533 시점)**:
- 본 런북 작성·머지: **Security Engineer** (자동화 가능).
- **실제 회전 실행**: **CEO 또는 DBA 만 가능** — Neon Console 권한 보유자가 필요. Security Engineer 는 권한이 없다.
- 본 이슈(CMP-533) 의 disposition 은 `done` 일 수 있으나 **R1 자체의 잔존 위험은 회전이 끝날 때까지 open** → 별도 추적 이슈로 분기 (CEO/DBA owner).

**잔존 위험 평가 (회전 전·후)**:

| 시점 | 위험 | 평가 근거 |
|---|---|---|
| 회전 전 (현재) | **High** | 평문 비번이 issue 본문·Paperclip 외부 DB 에 노출. 인터넷 도달 가능 가정 시 즉시 침해 가능. |
| 회전 직후 | Low | 이전 값은 무효. git history 의 평문은 잔존하지만 사용 불가. |
| 회전 후 30 일 | Negligible | 노출 흔적이 LLM 모델 학습 데이터로 들어갔어도 사용 불가능한 dead string. |

**R1 후속 이슈 (CEO 액션 요구)**:
- 제목: `[R1] Neon main 비밀번호 회전 실행 (CMP-533 런북 따라)`
- Owner: CEO (또는 위임된 DBA)
- 수용 기준:
  - [ ] §1~§4 단계 모두 완료
  - [ ] §6 검증 체크리스트 100%
  - [ ] 본 런북의 §7 평가표가 "회전 직후" 행으로 업데이트

---

## 8. 참고

- Neon: https://neon.com/docs/manage/passwords
- Neon connection pooler: https://neon.com/docs/connect/connection-pooling
- ADR-0001 §4 (Neon Postgres 17 결정)
- AGENTS.md §4.4 (시크릿 정책)
- `tools/secret-scan/patterns.yml` (검출 정본)
