#!/usr/bin/env python3
"""Generate Pydantic v2 models from contracts/contracts.json for both services."""

import json
import re
import sys
from pathlib import Path

CONTRACTS_PATH = Path(__file__).parent.parent / "contracts" / "contracts.json"

PYDANTIC_HEADER = '''\
# AUTO-GENERATED — do not edit manually.
# Regenerate with: python scripts/gen_contracts.py
# Source: contracts/contracts.json v{version}

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

# ── type aliases ──────────────────────────────────────────────────────────────
BoundedFloat = Annotated[float, Field(ge=0.0, le=1.0)]
DifficultyLevel = Annotated[int, Field(ge=1, le=10)]
'''

# Map contract notation → Python type
def notation_to_type(val: object, field_name: str = "") -> str:
    if not isinstance(val, str):
        return "object"
    val = val.strip()

    if val == "binary":
        return "bytes"
    if val == "uuid":
        return "UUID"
    if val == "iso8601":
        return "datetime"
    if val == "float 0-1":
        return "BoundedFloat"
    if val in ("float", "float (wpm)"):
        return "float"
    if val == "integer 1-10":
        return "DifficultyLevel"
    if val == "integer":
        return "int"
    if val == "string" or val.startswith("string ("):
        return "str"
    if val == "object":
        return "dict"
    if " | " in val:
        parts = [p.strip() for p in val.split("|")]
        # check for null
        if "null" in parts:
            inner_parts = [p for p in parts if p != "null"]
            inner = ", ".join(f'"{p}"' for p in inner_parts)
            return f"Optional[Literal[{inner}]]"
        return "Literal[" + ", ".join(f'"{p}"' for p in parts) + "]"

    return "str"


def strip_comments(text: str) -> str:
    return re.sub(r"(?m)//.*$", "", text)


def snake_case(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def generate_model(name: str, shape: dict | str | list) -> str:
    if isinstance(shape, str):
        # alias — skip, handled as type comment
        return f"# {name} is an alias for: {shape}\n"
    if isinstance(shape, list):
        return f"# {name} is a list type — not generated as a standalone model\n"

    safe_name = name.replace(".", "_").replace("*", "All")
    lines = [f"class {safe_name}(BaseModel):"]
    for field, ftype in shape.items():
        py_name = field
        optional = False

        if isinstance(ftype, list):
            # list of objects or strings
            if ftype and isinstance(ftype[0], dict):
                # inline nested — generate inline
                inner_name = f"{safe_name}_{py_name.title()}"
                lines.insert(0, generate_model(inner_name, ftype[0]))
                lines.append(f"    {py_name}: list[{inner_name}]")
            else:
                lines.append(f"    {py_name}: list[str]")
        elif isinstance(ftype, dict):
            # inline nested object
            inner_name = f"{safe_name}_{py_name.title()}"
            lines.insert(0, generate_model(inner_name, ftype))
            lines.append(f"    {py_name}: {inner_name}")
        else:
            type_str = notation_to_type(ftype, field)
            if type_str.startswith("Optional["):
                optional = True
            if optional:
                lines.append(f"    {py_name}: {type_str} = None")
            else:
                lines.append(f"    {py_name}: {type_str}")

    if len(lines) == 1:
        lines.append("    pass")
    return "\n".join(lines) + "\n"


def main() -> None:
    raw = CONTRACTS_PATH.read_text()
    data = json.loads(strip_comments(raw))
    version = data.get("_meta", {}).get("version", "unknown")

    out_lines = [PYDANTIC_HEADER.format(version=version)]
    # Skip _meta and REST alias keys
    skip = {"_meta"}

    # Collect names that are just string aliases (e.g. "REST.PostSessionResponse": "Session")
    for name, shape in data.items():
        if name in skip:
            continue
        out_lines.append(generate_model(name, shape))

    output = "\n".join(out_lines)

    targets = [
        Path(__file__).parent.parent / "services" / "analysis" / "app" / "contracts" / "models.py",
        Path(__file__).parent.parent / "services" / "gateway" / "app" / "contracts" / "models.py",
    ]
    for target in targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(output)
        print(f"Written: {target}")


if __name__ == "__main__":
    main()
