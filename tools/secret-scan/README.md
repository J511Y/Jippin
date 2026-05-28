# tools/secret-scan — 집핀 시크릿 스캐너

집핀(Jippin) 레포에 자격증명·토큰·인라인 비밀번호가 우발적으로 들어가지 않도록 막는 정본 가드.
CMP-533 (Security Engineer) 가 봉인. pre-commit + CI 양쪽에서 동일한 결과를 낸다.

> 한 줄: **`patterns.yml` 이 정본, `scan.py` 가 진입점, `.pre-commit-config.yaml` / `.github/workflows/secret-scan.yml` 이 강제 지점.**

---

## 0. 5초 사용법

```bash
# 한 번만 — pre-commit 훅 설치
pip install pre-commit && pre-commit install

# 평소
git add .
git commit -m "..."        # ← jippin-secret-scan 훅이 자동 실행

# 수동 — 전체 트리 스캔
python tools/secret-scan/scan.py

# 패턴 정의가 자기 자신을 잡는지 self-test
python tools/secret-scan/scan.py --selftest
```

---

## 1. 무엇을 잡는가

| 패턴 ID | 잡는 시크릿 | 심각도 |
|---|---|---|
| `neon-password` | `npg_*` (Neon Postgres) | critical |
| `openai-api-key` | `sk-*`, `sk-proj-*`, `sk-svcacct-*` | critical |
| `aws-access-key-id` | `AKIA*`, `ASIA*`, `AIDA*`, ... | critical |
| `aws-secret-access-key` | `aws_secret_access_key=...` 컨텍스트 + 40자 | critical |
| `slack-bot-token` | `xoxb-*`, `xoxp-*`, `xoxa-*`, ... | high |
| `github-personal-token` | `ghp_*` | critical |
| `github-oauth-token` | `gho_*` | high |
| `github-app-token` | `ghs_*`, `ghu_*`, `ghr_*` | high |
| `db-url-with-inline-password` | `postgresql://user:pw@`, `mysql://...`, `mongodb://...` | critical |
| `google-api-key` | `AIza*` | high |
| `stripe-secret-key` | `sk_live_*`, `sk_test_*`, `rk_*` | critical |
| `private-key-block` | `-----BEGIN ... PRIVATE KEY-----` | critical |

전체 정의는 `patterns.yml`. 변경은 Security Engineer 리뷰 필수.

---

## 2. 무엇을 무시하는가 (Allowlist)

`patterns.yml` 의 `allowlist:` 섹션이 정당한 예외를 정의한다.

- 패턴 정의 자체(`patterns.yml`) — 시그니처 포함
- 스캐너 코드(`scan.py`) — self-test fixture
- 런북(`docs/runbooks/neon-credential-rotation.md`) — `npg_FAKE_*` / `npg_REDACTED_*` 같은 placeholder 만 허용
- 보안 정책(`docs/runbooks/security-policy.md`)
- `.env.example`, `infra/compose/.env.example`

예외 추가 절차:
1. `patterns.yml` 의 `allowlist:` 에 `path` / `pattern_id` / `regex` / `reason` 명시.
2. PR 본문에 "왜 정당한 예외인지" 1 문단 작성.
3. CODEOWNERS 가 Security Engineer 리뷰 강제.

---

## 3. 무엇을 강제하는가

| 강제 지점 | 어디서 | 동작 |
|---|---|---|
| Pre-commit 훅 | 개발자 머신 | `scan.py --staged` 가 staged 변경만 검사. 발견 시 commit 차단. |
| CI `pattern-scan` job | GitHub Actions PR / push / 주간 cron | `scan.py` 가 전체 트리를 검사 + JSON 리포트 아티팩트. |
| CI `gitleaks` job | GitHub Actions | `.gitleaks.toml` (patterns.yml 미러) 로 industry-standard 보조 스캔. |
| CI `diff-grep` job | PR 만 | 추가 diff 라인을 bash grep — 위 둘이 다운돼도 최후 안전망. |

세 CI job 은 `secret-scan-status` 메타 job 에서 aggregate. branch protection 은 이 한 개만 required 설정하면 충분.

---

## 4. 발견되면 어떻게 하는가

스캐너 출력은 다음 형식이다:

```
[FAIL] secret-scan: 시크릿 또는 의심 패턴이 발견되었습니다.
  총 1 건. 커밋/머지가 차단되었습니다.

  -- apps/api/app/core/config.py --
    [CRITICAL] apps/api/app/core/config.py:42:18 pattern=neon-password matched='npg_***c5'
      what: Neon Serverless Postgres 비밀번호 (`npg_*`)
      fix : Neon Console 에서 즉시 비밀번호 회전 (`docs/runbooks/neon-credential-rotation.md`).
```

조치 흐름:

1. **시크릿이 실제 활성 자격증명인가** — 그렇다면 **즉시 회전**.
   - Neon: `docs/runbooks/neon-credential-rotation.md`
   - 그 외: `docs/runbooks/security-policy.md` §6 회전 정책 표
2. 코드에서 평문 값을 제거하고 환경변수 / `.env` / 시크릿 매니저 참조로 교체.
3. (이미 커밋된 경우) 별도 commit 으로 제거 + `git push` 후 git history 정리는 Security Engineer 와 협의 (BFG 또는 `git filter-repo`).
4. **테스트 fixture / 문서 예시** 였다면 `patterns.yml` 의 allowlist 에 등록.
5. 다시 커밋 → pre-commit + CI 가 통과해야 한다.

**절대 하지 말 것**:
- `git commit --no-verify` 로 우회 (코드 리뷰 거부 사유).
- 본 README 의 사용 예시처럼 평문 키를 새 라인으로 추가 (allowlist 등재된 경로만 허용).
- 시크릿 값을 Slack / 이슈 댓글에 평문으로 paste — 이미 노출된 값이라도 추가 확산은 금지.

---

## 5. 자기 자신 검증 — `--selftest`

신규 패턴을 `patterns.yml` 에 추가했다면 반드시:

```bash
python tools/secret-scan/scan.py --selftest
```

이 명령은:
- `scan.py` 내부의 `SELFTEST_POSITIVES` 샘플을 각 패턴이 잡는지 확인 (regex 회귀 방지).
- `SELFTEST_NEGATIVES` 의 마스킹된 placeholder (`****`, `<password>`, `${ENV}`) 를 잡지 않는지 확인 (false-positive 회귀 방지).

pre-commit 도 `patterns.yml` / `scan.py` 가 변경될 때 자동으로 selftest 를 실행한다.

---

## 6. 가짜 시크릿 commit 테스트 (수용 기준 검증)

본 가드가 진짜로 작동하는지 보려면:

```bash
# 1) 일부러 시크릿이 박힌 파일 생성
echo 'DATABASE_URL=postgres://u:npg_FAKE_PASSWORD_xxxxx@host/db' > apps/api/leaky.py
git add apps/api/leaky.py

# 2) 커밋 시도 — pre-commit 훅이 차단해야 한다
git commit -m "🚧 wip: 가짜 시크릿 테스트"

# 기대 결과 (exit code 2):
#   집핀 시크릿 스캐너 ...........................................Failed
#   - hook id: jippin-secret-scan
#   - exit code: 2
#   [FAIL] secret-scan: 시크릿 또는 의심 패턴이 발견되었습니다.
#     ...
#       [CRITICAL] apps/api/leaky.py:1:18 pattern=neon-password matched='npg_***xx'
#       [CRITICAL] apps/api/leaky.py:1:14 pattern=db-url-with-inline-password matched='post***db'
```

CI 도 동일하게 차단한다. **`npg_FAKE_PASSWORD_xxxxx` 가 코드 파일에 들어가면 pre-commit + CI 모두 fail.**

(가짜 값이 `docs/runbooks/neon-credential-rotation.md` 에 등장하는 경우는 allowlist `npg_(FAKE|REDACTED|EXAMPLE|XXXX|SAMPLE)*` 가 허용한다 — 런북의 안전한 placeholder.)

본 테스트는 `scan.py --selftest` 의 일부로 자동화되어 있다:

```python
SELFTEST_POSITIVES = [
    ("neon-password", "DATABASE_URL=postgres://u:npg_CNDw2RnvGJc5@host/db"),
    ("neon-password", "leak: npg_FAKE_PASSWORD_xxxxx"),   # ← 본 수용 기준 항목
    ...
]
```

---

## 7. 관련 문서

- `patterns.yml` — 패턴 정본 (변경 시 `.gitleaks.toml` 도 갱신)
- `.gitleaks.toml` — gitleaks 보조 스캐너용 미러
- `.pre-commit-config.yaml` — pre-commit 훅 정의
- `.github/workflows/secret-scan.yml` — CI 워크플로
- `docs/runbooks/neon-credential-rotation.md` — Neon 회전 절차
- `docs/runbooks/security-policy.md` — 전체 보안 정책
- AGENTS.md §4.4 — 시크릿·환경변수 규약
- ADR-0001 §9 — 봉인된 환경변수 / 바이너리 버전
