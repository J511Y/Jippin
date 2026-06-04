# Runbook — Neon Postgres 브랜치 운영 (APP_ENV ↔ branch 매핑)

> **⚠ ARCHIVE — Neon → Supabase cutover 완료 (CMP-603, 2026-06-02)**
>
> 본 런북은 **이력 참조용 archive** 다. Forward DB schema / branching 정본은 [`supabase-branching.md`](supabase-branching.md). CI/CD 측 변경:
>
> - `.github/workflows/neon-pr-branch.yml` → `.github/workflows/_archive/neon-pr-branch.yml.archived` (GitHub Actions 가 로드하지 않음).
> - `.github/workflows/deploy.yml::release-migrate` (Neon `DATABASE_URL` + `alembic upgrade head`) → 제거.
> - `.github/workflows/ci.yml::migrate-check` → Supabase SQL migration drift 가드로 재정의 (Neon secret 의존 없음).
>
> 본 런북을 읽어도 되는 경우:
> - Neon project 가 잔존하는 동안 본인의 1Password vault 에서 connection string 의 host prefix 를 해석할 때.
> - 과거 Neon 운영 행위의 audit trail 확인.
> - Neon 비밀번호 회전 ([`neon-credential-rotation.md`](neon-credential-rotation.md)) — Neon project 가 폐기되기 전까지만 의미 있음.
>
> **하지 말 것**:
> - 본 런북의 절차로 새 Neon branch 를 만들어 forward migration 을 적용. cutover 이후 Neon 은 forward authority 가 아니다.
> - `.github/workflows/_archive/` 안의 워크플로우를 다시 active 디렉터리로 옮김.
> - 새 작업 base 로 본 런북을 인용. 신규 작업은 [`supabase-branching.md`](supabase-branching.md) 와 [`supabase-migration-plan.md`](supabase-migration-plan.md) 를 정본으로 한다.
>
> Neon project 자체 폐기 + Neon 시크릿/변수 GitHub Settings 일괄 삭제는 사용자 콘솔 작업 (CMP-603 PR 본문 §사용자 작업 체크리스트). 폐기 완료 시점에 본 디렉터리 자체가 `docs/runbooks/_archive/` 로 이동할 수 있다.

- 정본 책임자: **Infrastructure Lead** · **Database Engineer** 리뷰
- 관련: CMP-536 (Neon 마이그레이션 세팅), CMP-538 (본 문서), CMP-543 (개발환경 구축), CMP-544 (`local` 브랜치 신설), AGENTS.md §4.4, **CMP-574 / CMP-602 (Supabase 전환 — 본 런북 archive 대상)**
- 인접 런북: [`neon-credential-rotation.md`](neon-credential-rotation.md) (비밀번호 회전, 한시 잔존), [`supabase-branching.md`](supabase-branching.md) (Supabase 브랜치 운영, **현 정본**)
- 목표 소요(신규 작업자 자기 `local` fork 생성): **30분 이내**

---

## 0. 봉인된 매핑 (CTO 결정 — 본 런북은 단지 운영 절차일 뿐 매핑은 봉인)

| APP_ENV       | Neon 브랜치               | 수명           | 비고                                  |
|---------------|---------------------------|----------------|---------------------------------------|
| `development` | `dev` [^cmp544]           | 장기, 공유     | 로컬 개발자 공용                      |
| `test`        | `dev` 또는 PR ephemeral   | 단기           | CI / 단위 테스트 (ephemeral은 CMP-536 자식 C) |
| `staging`     | `staging`                 | 장기           | QA / 사전검증                         |
| `production`  | `main`                    | 장기           | 운영 (Neon project default branch)    |

[^cmp544]: CMP-544 — `APP_ENV=development` 의 표준 Neon 브랜치는 **`local` (로컬 워크스테이션)** 또는 **`dev` (CI / `development` GitHub Environment 배포)** 이다. 둘 다 `APP_ENV=development` 로 부팅하며 enum 은 확장하지 않는다 (CMP-538 봉인 유지). 어느 브랜치를 보느냐는 `apps/api/.env` 의 `DATABASE_URL` / `DATABASE_POOL_URL` host 한 줄로만 결정한다 (12-factor). **표 자체는 봉인이며 본 각주만 추가된다.**

**코드 분기는 만들지 않는다** — 매핑은 환경별 `.env` 의 `DATABASE_URL` / `DATABASE_POOL_URL` 값으로만 한다 (12-factor).

본 매핑은 봉인이다. 변경하려면 ADR 을 새로 발행하고 AGENTS.md §4.4·`apps/api/.env.example`·`apps/api/src/config.py::ALLOWED_APP_ENVS`·본 런북을 같은 PR 에서 갱신한다.

---

## 1. Neon 브랜치 트리 (기대 상태)

```
neon project (jippin)
└── main                 ← APP_ENV=production
    ├── staging          ← APP_ENV=staging        (parent: main)
    └── dev              ← APP_ENV=development    (parent: main 또는 staging)
        │                  · CI 워크플로 / `development` GitHub Environment 배포 전용
        │                  · pr-N ephemeral 의 parent (CMP-536 자식 C)
        ├── pr-1234         (CMP-536 자식 C, ephemeral, parent: dev)
        ├── pr-1235         (ephemeral)
        └── local         ← APP_ENV=development    (parent: dev, CMP-544)
            │                · 로컬 워크스테이션 표준 브랜치 (공용 시드, 공용 schema)
            │                · scale-to-zero ON, suspend 5분, history retention 최소
            └── local-<handle>  (선택: 작업자별 격리 fork, parent: local)
```

운영 원칙:

- 브랜치 parent 는 항상 더 신뢰도 높은 브랜치를 가리킨다 (production → staging → dev → local).
- `dev` 의 스키마는 `staging` 의 스키마와 동일하거나 **앞서 있을 수 있다** (마이그레이션이 먼저 dev 에서 검증).
- `staging` 의 스키마는 `main` 의 스키마와 동일하거나 앞서 있을 수 있다.
- `local` 은 `dev` 에서 분기된 로컬 전용 브랜치다. 여기서 수행한 마이그레이션 실험은 PR/CI 를 통해 `dev` 로 승격되며, 자동 역전파는 없다.
- 거꾸로 흐르는 데이터 복제는 본 런북 범위가 아니다 (`reset_from_parent` 별도 운용).

---

## 2. Neon 콘솔에서 브랜치 생성 (콘솔 작업, 사람만 수행)

본 런북은 절차만 명시한다. 실제 콘솔 행위는 Neon Project Owner / Admin 권한 보유자(현재: CEO 또는 위임된 DBA) 가 수행한다. Paperclip 에이전트는 직접 실행하지 않는다.

### 2.1 사전 체크 (3분)

- [ ] https://console.neon.tech 로그인 + 본 프로젝트 선택 (host prefix `ep-empty-heart-aolzk9rl`).
- [ ] 본 프로젝트의 default branch 가 `main` 인지 확인 (Branches 화면 상단 배지). 다르면 `production` ↔ `main` 매핑이 깨진다 → 작업 중단 후 CEO 알림.
- [ ] 1Password vault `집핀 / Neon` 의 접근 권한 확인.

### 2.2 staging 브랜치 (1회만, 최초 셋업 시)

1. **Branches** → `Create branch`.
2. 이름: `staging`, parent: `main`, **include data**: Yes (default).
3. compute size: dev 와 동일하거나 더 작게. autoscale: scale-to-zero ON, suspend after 5분.
4. 생성 후 **Connection details** 에서 다음 두 URL 을 복사해 1Password 항목 `집핀 / Neon staging / neondb_owner` 에 저장.
   - Direct (non-pooler): host 는 `ep-…` (no `-pooler`)
   - Pooler:              host 는 `ep-…-pooler`
5. 회전 정책: §5 참조.

### 2.3 dev 브랜치 (1회만, 최초 셋업 시)

1. **Branches** → `Create branch`.
2. 이름: `dev`, parent: `main` (또는 `staging` — CTO 결정에 따른다), **include data**: Yes.
3. compute size: 가장 작은 옵션. autoscale: scale-to-zero ON, suspend after 5분.
4. **Connection details** 의 두 URL 을 1Password `집핀 / Neon dev / neondb_owner` 에 저장.
5. **TTL 끔.** `dev` 는 장기 공유 브랜치이므로 expiration 없이 운영한다. Neon 콘솔 `Branches > dev > Edit > Expiration` 에서 `Never` 로 설정. (TTL 이 설정된 브랜치는 자식 브랜치를 만들 수 없으며, CMP-544 의 `local` 자식 생성을 차단한다.)

### 2.4 자기 `local` fork (로컬 워크스테이션, 신규 작업자 onboarding 30분 안에)

본 절차가 **신규 작업자가 스스로 따라할 수 있는 셀프 가이드** 이며, 본 런북의 자기 점검 기준이다. 본 절차는 CMP-544 에서 `dev-<handle>` → `local` 기반으로 재작성됐다.

선행 조건:

- 프로젝트에 공용 `local` 브랜치가 이미 존재한다 (CMP-544 가 1회 생성). 없다면 §2.4.0 의 1회 셋업을 먼저 수행한다.

#### 2.4.0 공용 `local` 브랜치 (1회만, CMP-544 인도물)

1. **Branches** → `Create branch`.
2. 이름: `local`. parent: `dev`. **include data**: Yes.
3. compute size: 가장 작은 옵션. autoscale: scale-to-zero ON, suspend after 5분.
4. **History retention**: 최소 (콘솔 슬라이더 최좌측).
5. **TTL/Expiration**: `Never` (장기 공유 브랜치).
6. **Connection details** 의 두 URL 을 1Password `집핀 / Neon local / neondb_owner` 에 저장.

MCP 로도 생성 가능하다: `mcp__Neon__create_branch(projectId="<...>", branchName="local", parentId="<dev branch id>")`. MCP 는 compute / TTL / history retention 옵션을 노출하지 않으므로 생성 직후 Neon 콘솔에서 위 세 값을 직접 확인·수정한다.

#### 2.4.1 자기 local fork (작업자별)

1. **Branches** → `Create branch`.
2. 이름: `local-<handle>` (예: `local-jhyou`). parent: `local`. **include data**: Yes.
3. 작은 compute, scale-to-zero, suspend 5분.
4. **Connection details** 패널의 두 URL 을 로컬 `apps/api/.env` 에 붙여넣는다. (절대 커밋 금지)
5. `cd apps/api && uv run uvicorn src.main:app --reload` 로 부팅 (`APP_ENV=development` 그대로).
6. `curl http://localhost:8000/healthz` 가 200 + `db.ok=true` 인지 확인.
7. (선택) 자기 fork 가 더는 필요 없으면 §3 정리.

> 격리가 필요 없는 작업자는 공용 `local` 브랜치 URL 을 그대로 `.env` 에 사용해도 된다. 스키마가 충돌할 위험이 있을 때만 `local-<handle>` 로 분리한다.

### 2.5 신규 작업자 자기 점검 체크리스트 (30분 내 완료해야 본 런북 통과)

- [ ] 0 분 — 콘솔 로그인 + 프로젝트 진입.
- [ ] 5 분 — §2.4.1 절차로 `local-<handle>` (또는 공용 `local`) URL 확보 완료.
- [ ] 10분 — 두 URL 을 `apps/api/.env` 에 채움. `sslmode=require` 포함 확인.
- [ ] 15분 — `APP_ENV=development` 로 부팅. `/healthz` 200.
- [ ] 20분 — psql 또는 `uv run python -c "..."` 로 `SELECT 1` 직접 실행 성공.
- [ ] 25분 — `git status` 가 깨끗하다 (실수로 `.env` 가 스테이지되지 않았다).
- [ ] 30분 — `infra/compose/.env.example` / `apps/api/.env.example` 에 자기 비밀번호 흔적이 없다 (`grep npg_` 결과 0).

30분을 초과하면 본 런북이 미흡하다는 신호다. 인프라 Lead 에게 피드백 코멘트로 보고할 것.

---

## 3. 브랜치 정리 (자기 `local` fork 폐기)

작업자 이탈, 머신 교체, 또는 더 이상 fork 가 필요 없을 때:

1. Neon 콘솔 **Branches** → `local-<handle>` → 우측 `⋯` → `Delete branch`.
2. 1Password `집핀 / Neon local-<handle>` 항목을 `archived` 로 이동.
3. 로컬 `.env` 의 두 URL 을 비우거나 새 fork 의 URL 로 교체.
4. 본인이 만든 ephemeral PR 브랜치(있으면)도 같이 삭제.

> **공유 브랜치는 절대 임의 삭제 금지.** `local` / `dev` / `staging` / `main` 삭제는 CEO + DBA 합의가 필요하다.

---

## 4. Connection string 패턴 (pooler / non-pooler)

모든 URL 은 `sslmode=require` 가 필수다. Neon 은 TLS 가 없는 연결을 거부한다.

```
postgresql+psycopg://<USER>:<PASSWORD>@<HOST>/<DB>?sslmode=require
```

`<HOST>` 의 prefix 가 브랜치 라벨을 결정한다 (Neon 콘솔이 자동 부여 — 예: `ep-local-…`, `ep-dev-…`, `ep-staging-…`, `ep-main-…`).

| 키                  | 호스트 패턴            | 용도                                |
|---------------------|------------------------|-------------------------------------|
| `DATABASE_POOL_URL` | `ep-<…>-pooler.<…>`    | 어플리케이션 단의 요청 경로 쿼리    |
| `DATABASE_URL`      | `ep-<…>.<…>` (no -pooler) | Alembic 마이그레이션, 장기 트랜잭션 |

`apps/api/src/db.py` 가 두 엔진을 분리해 관리한다 (CMP-528).

APP_ENV 별 자리표시자 예시는 [`apps/api/.env.example`](../../apps/api/.env.example) 의 코멘트를 정본으로 본다.

---

## 5. 시크릿 회전 정책 (환경별)

본 런북은 정책만, 실제 회전 절차는 [`neon-credential-rotation.md`](neon-credential-rotation.md) 참조.

| 환경        | 정기 회전 주기 | compromise 의심 시       | 비고                              |
|-------------|----------------|--------------------------|-----------------------------------|
| production  | 90일           | **즉시** + audit         | 다운타임 공지 5분 권장            |
| staging     | 180일          | 즉시 (production보다 후) | QA 알림 후 진행                   |
| dev (공유)  | 365일          | 즉시                     | CI / development env 배포 의존; 절대 평문 commit 금지 |
| local (공유) | 365일         | 즉시                     | 로컬 워크스테이션 공용; 절대 평문 commit 금지 |
| local-<handle>| 작업자 책임  | 즉시 + Neon 콘솔 삭제 후 재생성 | 자기 fork 는 자기가 관리          |

compromise 의심 = 다음 중 하나라도 해당:

- `npg_` / `sk-` / `AKIA` 패턴이 git push 에 섞여 GitHub 에 도달했다.
- 1Password vault 외 위치(슬랙, 메일, 외부 SaaS 노트) 에서 평문이 발견되었다.
- 이탈자가 vault 접근 권한을 가졌었다.
- 외부 IP 가 Neon Operations 로그에 등장.

**필수 self-check (모든 PR 작성자 + 모든 에이전트)**:

```powershell
# 본 레포 트리에서 평문 비밀번호 패턴이 없는지 확인. 결과는 반드시 0건.
git grep -nE "npg_[A-Za-z0-9]{8,}" -- ":(exclude)*/node_modules/*" ":(exclude)*/.venv/*"
git grep -nE "sk-[A-Za-z0-9]{16,}" -- ":(exclude)*/node_modules/*" ":(exclude)*/.venv/*"
git grep -nE "AKIA[0-9A-Z]{16}"  -- ":(exclude)*/node_modules/*" ":(exclude)*/.venv/*"
```

회전 절차 자체는 [`neon-credential-rotation.md`](neon-credential-rotation.md) §1~§6 따른다.

---

## 6. APP_ENV 검증 (코드 단)

`apps/api/src/config.py::ALLOWED_APP_ENVS = {"development","test","staging","production"}` 가 봉인이다. 그 외 값으로 부팅하면 pydantic ValidationError 로 즉시 실패한다.

수동 확인:

```powershell
# 차단되어야 한다 (실패 기대):
$env:APP_ENV = "foobar"
cd apps/api
uv run uvicorn src.main:app
# → pydantic ValidationError 메시지에 "APP_ENV='foobar' is not one of ..." 포함

# 정상 부팅:
$env:APP_ENV = "development"
uv run uvicorn src.main:app
```

CI 회귀는 `apps/api/tests/test_config.py` 가 잡는다.

---

## 7. 비범위 (본 런북이 다루지 않는 것)

- **PR 별 ephemeral Neon 브랜치 자동 생성/삭제** — CMP-536 자식 C 가 다룬다 (GitHub Actions + Neon API).
- **시크릿 회전 자동화** — Security Lead 후속.
- 실제 staging/production 브랜치 생성 행위 — 사람 (CEO/DBA) 가 §2.2·§2.3 절차로 콘솔에서 수행.
- 데이터 마이그레이션(스키마 외 데이터 복제) — Database Engineer 별도 이슈.

---

## 8. 참고

- Neon 브랜치: https://neon.com/docs/manage/branches
- Neon connection pooler: https://neon.com/docs/connect/connection-pooling
- AGENTS.md §4.4 (APP_ENV ↔ Neon 브랜치 봉인)
- `docs/adr/0001-stack-reevaluation.md` §4 (Neon Postgres 17 결정)
- `apps/api/.env.example` (자리표시자 정본)
- `apps/api/src/config.py` (`ALLOWED_APP_ENVS`)
- `apps/api/tests/test_config.py` (검증 회귀)
