"""scripts/generate.py — JSON Schema → Pydantic v2 모델 생성기.

- 입력: ../schemas/*.schema.json
- 출력: ../python/zippin_contracts/<snake>.py + ../python/zippin_contracts/__init__.py
- 결정성: file order, banner, generator 옵션을 고정해 재실행 시 동일 출력.

본 스크립트는 ``datamodel-code-generator>=0.28`` 의 Python API 를 사용한다.
실행 시 의존성은 ``uv run --no-project --with datamodel-code-generator==0.28.5`` 로 주입한다.
(``pnpm run generate:py`` 가 자동 수행.)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    from datamodel_code_generator import (
        DataModelType,
        InputFileType,
        PythonVersion,
        generate,
    )
except ImportError as exc:  # pragma: no cover - import-time guard
    sys.stderr.write(
        "datamodel-code-generator 0.28.x 를 찾지 못했습니다. "
        "`pnpm run generate:py` 로 실행하세요.\n"
    )
    raise SystemExit(1) from exc


HERE = Path(__file__).resolve().parent
SCHEMAS_DIR = HERE.parent / "schemas"
PYTHON_PKG_DIR = HERE.parent / "python" / "zippin_contracts"

BANNER = (
    "# THIS FILE IS AUTO-GENERATED — DO NOT EDIT BY HAND.\n"
    "# Source: packages/contracts/schemas/*.schema.json\n"
    "# Regenerate: pnpm -C packages/contracts run generate\n"
)


def _snake(name: str) -> str:
    name = name.replace(".schema.json", "")
    return name.replace("-", "_")


def _module_export_names(py_path: Path) -> list[str]:
    """Find class/Enum names exported from a generated module (top-level ``class Foo``)."""
    pattern = re.compile(r"^class\s+([A-Za-z_][A-Za-z0-9_]*)\s*[\(:]", re.MULTILINE)
    text = py_path.read_text(encoding="utf-8")
    return sorted(set(pattern.findall(text)))


def _prepend_banner(path: Path) -> None:
    existing = path.read_text(encoding="utf-8")
    if existing.startswith(BANNER):
        return
    path.write_text(BANNER + existing, encoding="utf-8")


def main() -> None:
    schemas = sorted(p for p in SCHEMAS_DIR.glob("*.schema.json"))
    if not schemas:
        raise SystemExit(f"No *.schema.json found in {SCHEMAS_DIR}")

    if PYTHON_PKG_DIR.exists():
        for child in PYTHON_PKG_DIR.iterdir():
            if child.is_file() and child.suffix == ".py":
                child.unlink()
    else:
        PYTHON_PKG_DIR.mkdir(parents=True)

    per_module_exports: dict[str, list[str]] = {}

    for schema in schemas:
        module_name = _snake(schema.name)
        out_path = PYTHON_PKG_DIR / f"{module_name}.py"
        generate(
            input_=schema,
            input_file_type=InputFileType.JsonSchema,
            output=out_path,
            output_model_type=DataModelType.PydanticV2BaseModel,
            target_python_version=PythonVersion.PY_313,
            use_schema_description=True,
            use_field_description=True,
            use_double_quotes=True,
            field_constraints=True,
            snake_case_field=False,
            disable_timestamp=True,
            enum_field_as_literal="all",
            use_standard_collections=True,
            use_union_operator=True,
        )
        _prepend_banner(out_path)
        per_module_exports[module_name] = _module_export_names(out_path)
        sys.stdout.write(f"[ok] py: {schema.name} -> {module_name}.py\n")

    # __init__.py
    init_path = PYTHON_PKG_DIR / "__init__.py"
    lines: list[str] = [BANNER.rstrip(), ""]
    all_names: list[str] = []
    for module_name in sorted(per_module_exports):
        names = per_module_exports[module_name]
        if not names:
            continue
        lines.append(f"from .{module_name} import {', '.join(names)}")
        all_names.extend(names)
    all_names = sorted(set(all_names))
    lines.append("")
    lines.append("__all__ = [")
    for n in all_names:
        lines.append(f'    "{n}",')
    lines.append("]")
    lines.append("")
    init_path.write_text("\n".join(lines), encoding="utf-8")
    sys.stdout.write(
        f"[ok] py: __init__.py ({len(all_names)} exports across "
        f"{len(per_module_exports)} modules)\n"
    )


if __name__ == "__main__":
    main()
