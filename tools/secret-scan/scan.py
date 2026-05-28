#!/usr/bin/env python3
"""집핀 시크릿 스캐너 (pre-commit + CI 진입점).

본 스크립트는 `tools/secret-scan/patterns.yml` 정본 패턴 목록을 읽어
지정된 파일들에서 자격증명·토큰·인라인 비밀번호를 탐지한다.

사용 예::

    # 전체 트리 스캔 (CI · 수동 점검)
    python tools/secret-scan/scan.py

    # 스테이지된 파일만 스캔 (pre-commit 훅)
    python tools/secret-scan/scan.py --staged

    # 임의 파일 목록
    python tools/secret-scan/scan.py --files path/to/a path/to/b

    # 패턴 정의의 자체 정합성 검사
    python tools/secret-scan/scan.py --selftest

종료 코드:
    0 — clean
    2 — 시크릿 또는 의심 패턴 발견
    1 — 스캐너 자체 오류 (패턴 파일 파싱 실패 등)
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

try:
    import yaml  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover
    print(
        "ERROR: PyYAML 이 필요합니다. `pip install pyyaml` 또는 "
        "`uv pip install pyyaml` 후 다시 실행하세요.",
        file=sys.stderr,
    )
    sys.exit(1)

# Windows 콘솔(cp949) 에서 UTF-8 출력 보장. 이미 UTF-8 이면 no-op.
for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name, None)
    if _stream is not None and hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):  # pragma: no cover
            pass


REPO_ROOT = Path(__file__).resolve().parents[2]
PATTERNS_FILE = Path(__file__).resolve().parent / "patterns.yml"

# 디렉터리 prefix 단위 차단 (속도 + 노이즈 차단)
SKIP_DIR_PARTS = {
    ".git",
    "node_modules",
    ".next",
    ".turbo",
    ".pnpm-store",
    "__pycache__",
    ".venv",
    "venv",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
    ".tox",
    "coverage",
    ".nyc_output",
    "model_weights",
    "weights",
    ".cache",
}

# 바이너리 확장자 차단 (false-positive + 속도)
SKIP_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".ico", ".svg",
    ".pdf", ".zip", ".gz", ".tgz", ".tar", ".7z", ".rar",
    ".pyc", ".pyo", ".class", ".jar", ".war", ".so", ".dll", ".dylib", ".exe",
    ".ttf", ".otf", ".woff", ".woff2", ".eot",
    ".mp3", ".mp4", ".mov", ".avi", ".webm",
    ".docx", ".xlsx", ".pptx", ".doc", ".xls", ".ppt",
    ".lock",
    ".pt", ".bin", ".onnx", ".safetensors", ".pth",
}

MAX_FILE_BYTES = 2 * 1024 * 1024  # 2MB — 그 이상은 generated/binary 가정


@dataclass(frozen=True)
class Pattern:
    id: str
    description: str
    regex: re.Pattern[str]
    severity: str
    remediation: str = ""


@dataclass(frozen=True)
class AllowEntry:
    path_glob: str | None
    pattern_id: str | None
    regex: re.Pattern[str] | None
    reason: str


@dataclass
class Finding:
    file: str
    line: int
    column: int
    pattern_id: str
    severity: str
    description: str
    matched: str
    remediation: str

    def redacted(self) -> str:
        """결과 메시지에서 시크릿 본문을 부분 마스킹."""
        s = self.matched
        if len(s) <= 8:
            return s[:2] + "***"
        return s[:4] + "***" + s[-2:]


@dataclass
class Config:
    patterns: list[Pattern] = field(default_factory=list)
    allowlist: list[AllowEntry] = field(default_factory=list)


# ---------- 패턴 로딩 -----------------------------------------------------------


def load_config(path: Path = PATTERNS_FILE) -> Config:
    if not path.exists():
        raise SystemExit(f"패턴 파일이 없습니다: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SystemExit("patterns.yml: 최상위는 매핑이어야 합니다.")

    version = raw.get("version")
    if version != 1:
        raise SystemExit(f"patterns.yml: 알 수 없는 버전 {version!r} — 1 만 지원.")

    patterns: list[Pattern] = []
    seen_ids: set[str] = set()
    for entry in raw.get("patterns", []) or []:
        try:
            pid = entry["id"]
            regex_str = entry["regex"]
            description = entry["description"]
            severity = entry.get("severity", "high")
        except KeyError as exc:  # pragma: no cover
            raise SystemExit(f"patterns.yml: 필수 필드 누락 {exc}") from exc
        if pid in seen_ids:
            raise SystemExit(f"patterns.yml: 중복 pattern id `{pid}`")
        seen_ids.add(pid)
        try:
            compiled = re.compile(regex_str)
        except re.error as exc:
            raise SystemExit(
                f"patterns.yml: pattern `{pid}` 의 regex 컴파일 실패: {exc}"
            ) from exc
        patterns.append(
            Pattern(
                id=pid,
                description=description,
                regex=compiled,
                severity=severity,
                remediation=str(entry.get("remediation", "")).strip(),
            )
        )

    allowlist: list[AllowEntry] = []
    for entry in raw.get("allowlist", []) or []:
        reason = entry.get("reason", "")
        if not reason:
            raise SystemExit("patterns.yml: allowlist 항목은 `reason` 필수.")
        regex_str = entry.get("regex")
        try:
            compiled_r = re.compile(regex_str) if regex_str else None
        except re.error as exc:
            raise SystemExit(
                f"patterns.yml: allowlist regex 컴파일 실패: {exc}"
            ) from exc
        allowlist.append(
            AllowEntry(
                path_glob=entry.get("path"),
                pattern_id=entry.get("pattern_id"),
                regex=compiled_r,
                reason=reason,
            )
        )

    return Config(patterns=patterns, allowlist=allowlist)


# ---------- 파일 수집 -----------------------------------------------------------


def _should_skip_path(rel_path: str) -> bool:
    parts = rel_path.replace("\\", "/").split("/")
    if any(part in SKIP_DIR_PARTS for part in parts):
        return True
    suffix = Path(rel_path).suffix.lower()
    if suffix in SKIP_SUFFIXES:
        return True
    return False


def iter_repo_files(root: Path) -> Iterator[Path]:
    """git ls-files (있으면) 또는 fs walk 로 트리 순회."""
    try:
        out = subprocess.check_output(
            ["git", "ls-files", "-z"],
            cwd=str(root),
            stderr=subprocess.DEVNULL,
        )
        out_others = subprocess.check_output(
            ["git", "ls-files", "-z", "--others", "--exclude-standard"],
            cwd=str(root),
            stderr=subprocess.DEVNULL,
        )
        paths: set[str] = set()
        for chunk in (out + b"\0" + out_others).split(b"\0"):
            if not chunk:
                continue
            rel = chunk.decode("utf-8", errors="replace")
            paths.add(rel)
        for rel in sorted(paths):
            if _should_skip_path(rel):
                continue
            p = root / rel
            if p.is_file():
                yield p
        return
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = str(p.relative_to(root))
        if _should_skip_path(rel):
            continue
        yield p


def staged_files(root: Path) -> list[Path]:
    try:
        out = subprocess.check_output(
            ["git", "diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR"],
            cwd=str(root),
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise SystemExit(
            "git 명령 실행 실패 — pre-commit 훅은 git 리포지토리 안에서만 동작합니다."
        ) from exc
    result: list[Path] = []
    for chunk in out.split(b"\0"):
        if not chunk:
            continue
        rel = chunk.decode("utf-8", errors="replace")
        if _should_skip_path(rel):
            continue
        p = root / rel
        if p.is_file():
            result.append(p)
    return result


def read_text(path: Path) -> str | None:
    try:
        size = path.stat().st_size
    except OSError:
        return None
    if size > MAX_FILE_BYTES:
        return None
    try:
        with path.open("rb") as f:
            sniff = f.read(1024)
            if b"\x00" in sniff:
                return None
            f.seek(0)
            data = f.read()
        return data.decode("utf-8", errors="replace")
    except OSError:
        return None


# ---------- 스캐닝 --------------------------------------------------------------


def _glob_match(pattern: str, path: str) -> bool:
    # fnmatch 는 `**` 를 단순 `*` 처럼 다룬다 — 디렉터리 경계 인식 위해 보정.
    if "**" in pattern:
        parts = pattern.split("**")
        re_pattern = ".*".join(fnmatch.translate(part).rstrip("\\Z") for part in parts)
        return re.match(re_pattern + r"\Z", path) is not None
    return fnmatch.fnmatchcase(path, pattern)


def is_allowed(finding: Finding, allowlist: Iterable[AllowEntry]) -> AllowEntry | None:
    rel = finding.file.replace("\\", "/")
    for entry in allowlist:
        if entry.path_glob and not _glob_match(entry.path_glob, rel):
            continue
        if entry.pattern_id and entry.pattern_id != finding.pattern_id:
            continue
        if entry.regex and not entry.regex.search(finding.matched):
            continue
        return entry
    return None


def scan_text(
    rel_path: str,
    text: str,
    patterns: list[Pattern],
) -> list[Finding]:
    findings: list[Finding] = []
    line_starts = [0]
    for i, ch in enumerate(text):
        if ch == "\n":
            line_starts.append(i + 1)

    def locate(pos: int) -> tuple[int, int]:
        lo, hi = 0, len(line_starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if line_starts[mid] <= pos:
                lo = mid
            else:
                hi = mid - 1
        return lo + 1, pos - line_starts[lo] + 1

    for pat in patterns:
        for m in pat.regex.finditer(text):
            line, col = locate(m.start())
            findings.append(
                Finding(
                    file=rel_path,
                    line=line,
                    column=col,
                    pattern_id=pat.id,
                    severity=pat.severity,
                    description=pat.description,
                    matched=m.group(0),
                    remediation=pat.remediation,
                )
            )
    return findings


def scan_files(
    files: Iterable[Path],
    config: Config,
    root: Path,
) -> list[Finding]:
    out: list[Finding] = []
    for path in files:
        rel = str(path.relative_to(root)) if path.is_absolute() else str(path)
        rel = rel.replace("\\", "/")
        text = read_text(path if path.is_absolute() else root / path)
        if text is None:
            continue
        findings = scan_text(rel, text, config.patterns)
        for f in findings:
            if is_allowed(f, config.allowlist) is None:
                out.append(f)
    return out


# ---------- 출력 ---------------------------------------------------------------


def render_human(findings: list[Finding]) -> str:
    if not findings:
        return "[OK] secret-scan: clean\n"
    lines = [
        "[FAIL] secret-scan: 시크릿 또는 의심 패턴이 발견되었습니다.",
        f"  총 {len(findings)} 건. 커밋/머지가 차단되었습니다.",
        "",
    ]
    by_file: dict[str, list[Finding]] = {}
    for f in findings:
        by_file.setdefault(f.file, []).append(f)
    for file, fs in sorted(by_file.items()):
        lines.append(f"  -- {file} --")
        for f in fs:
            lines.append(
                f"    [{f.severity.upper()}] {f.file}:{f.line}:{f.column} "
                f"pattern={f.pattern_id} matched={f.redacted()!r}"
            )
            lines.append(f"      what: {f.description}")
            if f.remediation:
                first = f.remediation.splitlines()[0]
                lines.append(f"      fix : {first}")
        lines.append("")
    lines.extend(
        [
            "조치 방법:",
            "  1) 시크릿을 즉시 회전 (예: Neon → docs/runbooks/neon-credential-rotation.md).",
            "  2) 코드에서 `.env` 또는 시크릿 매니저 참조로 교체.",
            "  3) 정당한 예시(allowlist) 라면 `tools/secret-scan/patterns.yml` 의 allowlist 에 사유와 함께 등록.",
            "  4) 다시 커밋. CI 가 동일 검사를 반복합니다.",
            "",
        ]
    )
    return "\n".join(lines)


def render_json(findings: list[Finding]) -> str:
    return json.dumps(
        {
            "ok": not findings,
            "count": len(findings),
            "findings": [
                {
                    "file": f.file,
                    "line": f.line,
                    "column": f.column,
                    "pattern_id": f.pattern_id,
                    "severity": f.severity,
                    "description": f.description,
                    "matched_redacted": f.redacted(),
                    "remediation": f.remediation,
                }
                for f in findings
            ],
        },
        ensure_ascii=False,
        indent=2,
    )


# ---------- 자체 점검 ----------------------------------------------------------


SELFTEST_POSITIVES = [
    ("neon-password", "DATABASE_URL=postgres://u:npg_CNDw2RnvGJc5@host/db"),
    ("neon-password", "leak: npg_FAKE_PASSWORD_xxxxx"),
    ("openai-api-key", "OPENAI_API_KEY=sk-proj-abcdefghijklmnopqrstuvwxyz123456"),
    ("aws-access-key-id", "key = AKIAIOSFODNN7EXAMPLE"),
    ("slack-bot-token", "token: xoxb-1234567890-abcdefghij"),
    ("github-personal-token", "ghp_abcdefghijklmnopqrstuvwxyz0123456789"),
    ("github-app-token", "ghs_abcdefghijklmnopqrstuvwxyz0123456789"),
    (
        "db-url-with-inline-password",
        "postgresql://owner:supersecret123@ep-foo.aws.neon.tech/db",
    ),
    ("private-key-block", "-----BEGIN RSA PRIVATE KEY-----"),
]

SELFTEST_NEGATIVES = [
    "DATABASE_URL=postgresql://u:****@host/db",
    "DATABASE_URL=postgresql://u:<password>@host/db",
    "DATABASE_URL=postgresql://u:${DB_PASSWORD}@host/db",
    "# example only: postgres://user:REDACTED@host/db",
]


def selftest(config: Config) -> int:
    failed = 0
    for pid, sample in SELFTEST_POSITIVES:
        findings = scan_text("selftest.txt", sample, config.patterns)
        if not any(f.pattern_id == pid for f in findings):
            print(f"  [X] pattern `{pid}` 가 자체 양성 샘플을 잡지 못함: {sample!r}")
            failed += 1
        else:
            print(f"  [OK] pattern `{pid}` ok ({sample[:40]}...)")
    for sample in SELFTEST_NEGATIVES:
        findings = scan_text("selftest.txt", sample, config.patterns)
        db_findings = [f for f in findings if f.pattern_id == "db-url-with-inline-password"]
        if db_findings:
            print(
                f"  [X] db-url 패턴이 마스킹된 값을 false-positive: {sample!r} -> "
                f"{[f.redacted() for f in db_findings]}"
            )
            failed += 1
    if failed:
        print(f"\n자체 점검 실패 {failed} 건.")
        return 1
    print("\n[OK] 자체 점검 통과.")
    return 0


# ---------- main ---------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="secret-scan",
        description="집핀 시크릿 스캐너 — pre-commit + CI 진입점.",
    )
    parser.add_argument(
        "--staged",
        action="store_true",
        help="git 스테이지된 파일만 스캔 (pre-commit 훅용)",
    )
    parser.add_argument(
        "--files",
        nargs="*",
        help="명시된 파일들만 스캔",
    )
    parser.add_argument(
        "--root",
        default=str(REPO_ROOT),
        help="레포 루트 (기본: 스크립트 기준 자동 추론)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="JSON 출력 (사람 친화 메시지 대신 기계 판독용)",
    )
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="패턴 자체 정합성 점검 (CI smoke test)",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    config = load_config()

    if args.selftest:
        return selftest(config)

    if args.files:
        files: list[Path] = [Path(f) for f in args.files]
    elif args.staged:
        files = staged_files(root)
    else:
        files = list(iter_repo_files(root))

    findings = scan_files(files, config, root)

    if args.json:
        sys.stdout.write(render_json(findings) + "\n")
    else:
        sys.stdout.write(render_human(findings))

    return 2 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
