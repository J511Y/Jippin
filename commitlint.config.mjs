// 집핀(Jippin) commitlint 설정 — CMP-531 / D5 (선택)
//
// AGENTS.md §4.1 / docs/CONTRIBUTING.md §2.1 봉인 정규식을 commitlint 가
// 이해할 수 있는 형태로 표현한다. CI 의 공식 진실은
// `tooling/validate_commit_msg.py` 이며, 본 파일은 로컬에서 commitlint 를
// 직접 돌리고 싶은 기여자를 위한 **보조 도구**다.
//
// 사용법:
//   pnpm dlx commitlint --edit .git/COMMIT_EDITMSG
//   또는 husky 와 함께:
//     pnpm add -D @commitlint/cli @commitlint/config-conventional husky
//     pnpm husky init
//     echo 'pnpm dlx commitlint --edit "$1"' > .husky/commit-msg
//
// 단순 경로(아무 것도 설치하지 않고 동작) 는 `.githooks/commit-msg` +
// `git config core.hooksPath .githooks` 다. CONTRIBUTING.md §6 참조.

const GITMOJI_PATTERN =
  /^(✨|🐛|📝|♻️|✅|🔧|🚀|🔒|🚧) (feat|fix|docs|refactor|test|chore|perf|security|wip)\(([a-z0-9][a-z0-9-]*)\): .+/;

/** @type {import('@commitlint/types').UserConfig} */
export default {
  rules: {
    "jippin-gitmoji-header": [2, "always"],
    "header-max-length": [2, "always", 120],
    "body-leading-blank": [1, "always"],
    "footer-leading-blank": [1, "always"],
    "subject-empty": [2, "never"],
  },
  plugins: [
    {
      rules: {
        "jippin-gitmoji-header": ({ header }) => {
          if (!header) {
            return [false, "header 가 비어 있다."];
          }
          // 머지/리버트/fixup 은 통과.
          if (
            header.startsWith("Merge ") ||
            header.startsWith("Revert ") ||
            header.startsWith("Reapply ") ||
            header.startsWith("fixup! ") ||
            header.startsWith("squash! ")
          ) {
            return [true];
          }
          if (!GITMOJI_PATTERN.test(header)) {
            return [
              false,
              [
                "gitmoji 정규식 위반.",
                "  허용 형식: <이모지> <prefix>(<scope>): <설명>",
                "  허용 이모지: ✨ 🐛 📝 ♻️ ✅ 🔧 🚀 🔒 🚧",
                "  허용 prefix: feat fix docs refactor test chore perf security wip",
                "  scope: [a-z0-9][a-z0-9-]*",
                "  예) ✨ feat(auth): 카카오 콜백",
                "  자세한 규칙: docs/CONTRIBUTING.md §2",
              ].join("\n"),
            ];
          }
          return [true];
        },
      },
    },
  ],
};
