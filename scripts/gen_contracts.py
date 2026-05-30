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

_SCALAR_NOTATIONS = {
    "binary": "bytes",
    "uuid": "UUID",
    "iso8601": "datetime",
    "float 0-1": "BoundedFloat",
    "float": "float",
    "float (wpm)": "float",
    "integer 1-10": "DifficultyLevel",
    "integer": "int",
    "object": "dict",
}


def _scalar_type(val: str) -> str | None:
    """Resolve a notation string to a non-union Python type, or None."""
    val = val.strip()
    if val in _SCALAR_NOTATIONS:
        return _SCALAR_NOTATIONS[val]
    if val == "string" or val.startswith("string ("):
        return "str"
    return None


# Map contract notation → Python type
def notation_to_type(val: object, field_name: str = "") -> str:
    if not isinstance(val, str):
        return "object"
    val = val.strip()

    scalar = _scalar_type(val)
    if scalar is not None:
        return scalar

    if " | " in val:
        parts = [p.strip() for p in val.split("|")]
        nullable = "null" in parts
        inner_parts = [p for p in parts if p != "null"]

        # Single nullable scalar — recurse so `uuid | null` becomes
        # `Optional[UUID]` rather than `Optional[Literal["uuid"]]`.
        if len(inner_parts) == 1:
            inner_scalar = _scalar_type(inner_parts[0])
            if inner_scalar is not None:
                return f"Optional[{inner_scalar}]" if nullable else inner_scalar

        # Otherwise build a Literal of the string variants.
        literal = "Literal[" + ", ".join(f'"{p}"' for p in inner_parts) + "]"
        return f"Optional[{literal}]" if nullable else literal

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
            # list of objects, named shapes, or scalars
            if ftype and isinstance(ftype[0], dict):
                # inline nested — generate inline
                inner_name = f"{safe_name}_{py_name.title()}"
                lines.insert(0, generate_model(inner_name, ftype[0]))
                lines.append(f"    {py_name}: list[{inner_name}]")
            elif ftype and isinstance(ftype[0], str):
                first = ftype[0].strip()
                scalar = _scalar_type(first)
                if scalar is not None:
                    lines.append(f"    {py_name}: list[{scalar}]")
                elif re.fullmatch(r"[A-Z][A-Za-z0-9_]*", first):
                    # Named shape reference (e.g. "MasteryUpdate", "KeyPoint").
                    lines.append(f"    {py_name}: list[{first}]")
                else:
                    lines.append(f"    {py_name}: list[str]")
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
    """The Python-side `contracts/models.py` files are HAND-MAINTAINED.

    Earlier versions of this script overwrote them with a generic
    auto-generated shape, but the live services depend on hand-coded
    extensions (the gateway's `_Strict` base, GenerationParams.n
    default, audio_format Field constraints, replays_budget, etc.)
    that the generator does not preserve.

    Until the generator is rewritten to layer extensions on top of the
    JSON contract (e.g. via a side-by-side `_generated.py` that the
    hand-maintained file imports), this script writes its output to a
    reference file under `contracts/reference/` instead of clobbering
    the live models. Diff that reference against the live file to spot
    drift; apply changes by hand.
    """
    raw = CONTRACTS_PATH.read_text()
    data = json.loads(strip_comments(raw))
    version = data.get("_meta", {}).get("version", "unknown")

    out_lines = [PYDANTIC_HEADER.format(version=version)]
    skip = {"_meta"}
    for name, shape in data.items():
        if name in skip:
            continue
        out_lines.append(generate_model(name, shape))

    output = "\n".join(out_lines)

    # Write to a non-destination reference path so this script is safe
    # to invoke without losing hand-maintained Pydantic models.
    reference = (
        Path(__file__).parent.parent / "contracts" / "reference" / "pydantic_models_from_json.py"
    )
    reference.parent.mkdir(parents=True, exist_ok=True)
    reference.write_text(output)
    print(f"Written reference-only models to: {reference}")
    print(
        "NOTE: This file is for diffing against the live service models — it is\n"
        "      NOT imported anywhere. Hand-update services/*/app/contracts/models.py."
    )


if __name__ == "__main__":
    main()
