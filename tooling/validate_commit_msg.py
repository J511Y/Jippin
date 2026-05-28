#!/usr/bin/env python3
"""집핀(Jippin) gitmoji 커밋 메시지 검증기.

AGENTS.md §4.1 / docs/CONTRIBUTING.md §2.1 봉인 정규식을 강제한다.
CI 의 `gitmoji-validate` job 과 로컬 git hook(`.githooks/commit-msg`) 가
공통으로 호출한다.

사용법:
    # 단일 메시지 파일 검증 (commit-msg 훅이 넘기는 $1)
    python tooling/validate_commit_msg.py <COMMIT_MSG_FILE>

    # 범위 검증 (CI: PR 의 모든 커밋)
    python tooling/validate_commit_msg.py --range <BASE_SHA>..<HEAD_SHA>

    # stdin 으로 메시지 직접 검증
    echo "✨ feat(auth): 카카오 콜백" | python tooling/validate_commit_msg.py --stdin

종료 코드:
    0 — 모두 통과
    1 — 하나 이상 위반
    2 — 사용 오류

본 스크립트는 표준 라이브러리만 사용한다(Python 3.13). 외부 의존성 X.
Windows 콘솔(cp949) 에서도 동작하도록 stdout 을 UTF-8 로 재바인딩한다.
"""

from __future__ import annotations

import argparse
import io
import re
import subprocess
import sys
from pathlib import Path

# Windows cp949 콘솔에서 ✨/❌ 등이 UnicodeEncodeError 를 일으키지 않도록
# 표준 출력/오류를 UTF-8 로 재바인딩한다.
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# AGENTS.md §4.1 의 9개 prefix.
# 정규식은 docs/CONTRIBUTING.md §2.1 과 1:1.
GITMOJI_PATTERN = re.compile(
    r"^(✨|🐛|📝|♻️|✅|🔧|🚀|🔒|🚧) "
    r"(feat|fix|docs|refactor|test|chore|perf|security|wip)"
    r"\(([a-z0-9][a-z0-9-]*)\): .+"
)

# 머지·리버트·릴리스 자동 커밋은 검증 대상에서 제외.
SKIP_PREFIXES = (
    "Merge ",
    "Revert ",
    "Reapply ",
    "fixup! ",
    "squash! ",
)


def is_skippable(subject: str) -> bool:
    return subject.startswith(SKIP_PREFIXES)


def validate_subject(subject: str) -> str | None:
    """한 줄(subject)을 검증. 통과면 None, 위반이면 사람용 메시지를 반환."""
    if is_skippable(subject):
        return None
    if not GITMOJI_PATTERN.match(subject):
        return (
            "gitmoji 정규식 위반.\n"
            "  허용 형식: <이모지> <prefix>(<scope>): <설명>\n"
            "  허용 이모지: ✨ 🐛 📝 ♻️ ✅ 🔧 🚀 🔒 🚧\n"
            "  허용 prefix: feat fix docs refactor test chore perf security wip\n"
            "  scope: 영문 소문자/숫자/하이픈. 예) ✨ feat(auth): 카카오 콜백\n"
            "  자세한 규칙: docs/CONTRIBUTING.md §2"
        )
    return None


def read_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def commits_in_range(rev_range: str) -> list[tuple[str, str]]:
    """git log --format='%H%x00%s' <range> 결과를 [(sha, subject), ...] 로 반환."""
    out = subprocess.check_output(
        ["git", "log", "--format=%H%x00%s", rev_range],
        text=True,
        encoding="utf-8",
    )
    rows: list[tuple[str, str]] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        sha, _, subject = line.partition("\x00")
        rows.append((sha, subject))
    return rows


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="gitmoji commit message validator")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "msg_file",
        nargs="?",
        type=Path,
        help="검증할 커밋 메시지 파일 (git hook 이 넘기는 .git/COMMIT_EDITMSG)",
    )
    group.add_argument(
        "--range",
        dest="rev_range",
        help="git revision range (예: origin/main..HEAD). PR 전체 커밋 검증용.",
    )
    group.add_argument(
        "--stdin",
        action="store_true",
        help="표준 입력에서 메시지 1건을 읽어 검증.",
    )
    args = parser.parse_args(argv)

    failures: list[str] = []

    if args.rev_range:
        for sha, subject in commits_in_range(args.rev_range):
            err = validate_subject(subject)
            if err:
                failures.append(f"FAIL {sha[:8]}  {subject}\n{err}")
            else:
                print(f"OK   {sha[:8]}  {subject}")
    else:
        if args.stdin:
            raw = sys.stdin.read()
        else:
            raw = read_file(args.msg_file)
        # 첫 비어있지 않은, 주석(#)이 아닌 줄을 subject 로 본다.
        subject = ""
        for line in raw.splitlines():
            stripped = line.rstrip()
            if not stripped or stripped.startswith("#"):
                continue
            subject = stripped
            break
        err = validate_subject(subject)
        if err:
            failures.append(f"FAIL  {subject!r}\n{err}")
        else:
            print(f"OK    {subject}")

    if failures:
        print()
        print("=" * 70)
        for f in failures:
            print(f)
            print("-" * 70)
        print(f"총 {len(failures)}건의 커밋이 gitmoji 정책을 위반함.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
