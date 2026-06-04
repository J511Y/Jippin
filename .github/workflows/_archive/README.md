# `.github/workflows/_archive/`

비활성 워크플로우 파일을 이력 참조용으로 보존하는 디렉터리.

## 규칙

- 본 디렉터리에 있는 모든 파일은 **GitHub Actions 가 워크플로우로 로드하지 않는다**. Actions 는 `.github/workflows/*.yml` 또는 `*.yaml` 만 인식한다 (정본: https://docs.github.com/en/actions/using-workflows/about-workflows#about-workflows).
- 따라서 보관 시 확장자를 `.yml.archived` (또는 `.yaml.archived`) 로 바꿔서 같은 트리 안에 두더라도 활성화되지 않게 한다.
- 파일 헤더에 archive 사유 (어떤 PR/이슈에서, 왜 비활성화했는지) 를 명시한다. 본 README 만으로 끝내지 않는다.
- 시크릿/연결 문자열은 절대 포함하지 않는다 (`docs/runbooks/security-policy.md`).
- 이 트리에서 직접 활성화하지 말 것. 다시 살릴 필요가 생기면 새 PR 에서 `.github/workflows/` 로 이동하고 본 README 의 archive 이력을 갱신한다.

## 현재 보관 항목

| 파일 | archive 사유 | archive PR / 이슈 |
|---|---|---|
| `neon-pr-branch.yml.archived` | Neon → Supabase cutover. PR preview branch 책임을 Supabase Automatic Branching 으로 이전. (`docs/runbooks/supabase-branching.md §6 단계 3`) | CMP-603 |
