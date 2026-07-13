# Jippin Deployment

이 문서는 집핀의 클라우드 배포 방식, DB 브랜치 전략, 마이그레이션 검증 절차를 누적 기록하는 운영 문서다.

> **배포 토폴로지 (라이브, 2026-06 배포 완료)**: [`docs/adr/0006-deployment-split-topology.md`](docs/adr/0006-deployment-split-topology.md) 의 **분리형 토폴로지**가 실제 운영 중이다 — web=**Vercel** (`jippin.ai` + `www`, git integration 자동 배포) · api=**Fly.io 도쿄(`nrt`)** 앱명 `jippin` (`api.jippin.ai`, `apps/api/fly.toml`) · redis=**managed Redis 도쿄** · postgres=**Supabase 서울** (session pooler) · 도면 추론=**Hugging Face Inference Endpoint** (private, scale-to-zero). 추가로 세움터 발급 워커 [`apps/seumteo-worker`](apps/seumteo-worker/README.md) 가 **별개 Fly 앱 `jippin-seumteo-worker`** (Flycast 사설망 전용, public IP 없음)로 배포된다 (ADR-0009). 실행 런북: [`docs/runbooks/fly-api-deploy.md`](docs/runbooks/fly-api-deploy.md).
>
> 배포 실행 주체: **Vercel 은 git integration 이 자동**, **Fly 두 앱(`fly deploy`, `fly deploy apps/seumteo-worker`)은 운영자가 수동 실행**한다. `.github/workflows/deploy.yml` 의 deploy job 은 여전히 스텁이며 실 배포를 수행하지 않는다.
>
> ⚠ ADR-0006 문서 상태는 아직 **Proposed** 이고 redis 를 **Upstash** 로 표기하고 있으나, 실제 운영은 배포 완료 + managed Redis(도쿄) 다. ADR 상태 갱신(Accepted + redis 벤더 표기 정정)은 오너 결정 사항으로 보류 중.
>
> ⚠ **DB 마이그레이션 SSOT 는 Supabase** (`supabase/migrations/*.sql` + Supabase GitHub Integration — `AGENTS.md` 최상단 / `docs/runbooks/supabase-*`). 아래 **§1~§4 의 Neon · `neon-pr-branch.yml` · Alembic · `NEON_*` 서술은 Supabase cutover (CMP-603) 이전의 역사적 기록**이며 forward 정본이 아니다 — 새 토폴로지 배포에 Neon 흐름을 적용하지 말 것. (Git branch ↔ APP_ENV ↔ DB 브랜치 매핑 개념만 Supabase 로 치환해 유효.)

## 1. 현재 배포 모델

| Git branch | GitHub Environment | APP_ENV | Neon branch | 용도 |
|---|---|---|---|---|
| feature / issue branch | 없음 | `test` | `preview/pr-<PR>-<branch>` | PR 단위 기능/스키마 검증 |
| `dev` | `development` | `development` | `development` | 개발 통합 환경 |
| `main` | `production` | `production` | `production` | 운영 환경 |

기본 흐름:

1. 이슈 브랜치에서 PR 을 열면 `.github/workflows/neon-pr-branch.yml` 이 Neon preview branch 를 만든다.
2. preview branch 에 `alembic upgrade head` 를 적용해 PR 스키마가 실제 DB 에 올라가는지 확인한다.
3. PR 이 문제 없으면 `dev` 로 squash merge 한다.
4. `dev` push 로 `.github/workflows/deploy.yml` 이 `NEON_DEV_DATABASE_URL` 에 `APP_ENV=development` 마이그레이션을 적용한다.
5. 개발 환경 검증 후 `dev` 를 `main` 으로 PR/squash merge 한다.
6. `main` push 로 같은 workflow 가 `NEON_PROD_DATABASE_URL` 에 `APP_ENV=production` 마이그레이션을 적용한다.

Hotfix 는 `main` 기준으로 브랜치를 만들고 `main` 으로 PR 을 보낸다. 머지 후에는 `dev` 에도 동일 변경을 back-merge 또는 cherry-pick 해서 장기 브랜치 간 drift 를 없앤다.

## 2. GitHub 설정

Repository variable:

- `NEON_PROJECT_ID`: Neon project id.

Repository 또는 Environment secret:

- `NEON_API_KEY`: PR preview branch 생성/삭제용 Neon API key.
- `NEON_DEV_PARENT_BRANCH`: `dev` 대상 PR preview 의 parent branch. Neon branch id 사용을 권장한다.
- `NEON_DEV_DATABASE_URL`: `dev` merge 후 development Neon branch 에 적용할 non-pooler URL.
- `NEON_PROD_DATABASE_URL`: `main` merge 후 production Neon branch 에 적용할 non-pooler URL.
- `NEON_TEST_DATABASE_URL`: 선택. CI drift guard 용 테스트 DB URL.

`NEON_DEV_DATABASE_URL` 과 `NEON_PROD_DATABASE_URL` 은 가능하면 각각 GitHub Environment `development`, `production` 에 둔다. production environment 에는 required reviewers 를 걸어 운영 DB 마이그레이션을 보호한다.

Alembic 마이그레이션은 `DATABASE_URL` 에 non-pooler connection string 을 사용한다. 일반 애플리케이션 쿼리는 별도 `DATABASE_POOL_URL` 을 사용할 수 있지만, DDL/lock 이 필요한 마이그레이션에는 pooler 를 쓰지 않는다.

## 3. PR Preview Branch

PR open/reopen/synchronize 시 workflow 는 다음 이름의 Neon branch 를 만든다.

```text
preview/pr-<PR번호>-<head branch>
```

PR base 가 `dev` 면 `NEON_DEV_PARENT_BRANCH` 를 parent 로 사용하고, PR base 가 `main` 이면 Neon `production` branch 를 parent 로 사용한다. 생성된 preview branch 는 14일 만료 시간을 가진다.

connection string 은 credential 이므로 로그나 PR 코멘트에 출력하지 않는다. PR 코멘트에는 branch 이름, parent, migration 실행 여부만 남긴다.

## 4. 로컬 검증 절차

로컬에서 Neon branch 별 마이그레이션을 확인할 때는 shell 에서 `DATABASE_URL` 과 `APP_ENV` 만 바꿔 같은 명령을 실행한다. 실제 URL 값은 `.env` 또는 비밀 저장소에서 주입하고, 터미널/이슈/PR 본문에 출력하지 않는다.

```powershell
cd C:\Users\jhyou\2026\jippin\apps\api

# PR preview 또는 테스트 브랜치
$env:APP_ENV = "test"
$env:DATABASE_URL = "<preview-or-test-non-pooler-url>"
uv run alembic upgrade head

# development 브랜치
$env:APP_ENV = "development"
$env:DATABASE_URL = "<development-non-pooler-url>"
uv run alembic upgrade head

# production 브랜치
$env:APP_ENV = "production"
$env:DATABASE_URL = "<production-non-pooler-url>"
uv run alembic upgrade head
```

스키마 반영 smoke test 는 임시 migration 으로 `deployment_probe_temp` 같은 테이블을 만들고, 각 Neon branch 에서 존재 여부를 확인한 뒤 cleanup migration 으로 제거한다. production 에 테스트 테이블을 남기지 않는다.

권장 순서:

1. 임시 migration 추가: `deployment_probe_temp` 생성.
2. 이슈 브랜치 PR 생성: preview branch 에 테이블이 생기는지 확인.
3. `dev` merge: development Neon branch 에 테이블이 생기는지 확인.
4. `main` merge: production Neon branch 에 테이블이 생기는지 확인.
5. cleanup migration 추가: `deployment_probe_temp` 제거.
6. cleanup 도 같은 경로로 preview -> dev -> main 순서로 반영해 최종 production 에 임시 테이블이 남지 않게 한다.

테이블 존재 확인 SQL:

```sql
select to_regclass('public.deployment_probe_temp') as table_name;
```

## 5. 운영 원칙

- `main` 에 직접 push 하지 않는다.
- DB migration 은 forward-only 로 작성한다. 자동 downgrade 는 운영 사고 가능성이 있어 사용하지 않는다.
- schema 변경 PR 은 모델, migration, 검증 로그를 함께 남긴다.
- connection string, API key, 도면 원본, 개인정보는 commit/PR/issue/comment 에 남기지 않는다.
- `deploy.yml` 의 deploy job 은 스텁이다. 실 배포는 **web=Vercel git integration(자동)** / **api·seumteo-worker=Fly `fly deploy`(운영자 수동)** 로 수행한다 (ADR-0006 / ADR-0009 / `docs/runbooks/fly-api-deploy.md`). deploy job 을 실 배포로 전환하려면 별도 이슈 + 운영자 승인이 필요하다.
- `apps/seumteo-worker` 코드를 수정하면 api 와 **별개로** `fly deploy apps/seumteo-worker` 를 실행해야 반영된다 (별개 Fly 앱 — 릴리즈 히스토리·시크릿 독립).
