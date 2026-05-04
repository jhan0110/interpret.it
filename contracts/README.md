# contracts/

`contracts.json` is the **canonical wire schema** for every payload that
crosses a service boundary in interpretit. When service code disagrees
with this file, service code is wrong. Update the contract first, then
regenerate downstream types.

## File format

`contracts.json` is JSON-with-comments (jsonc). The repo treats it as
authoritative source, not as something a runtime parses directly — both
sides generate native models from it.

Strip comments before machine parsing:

```bash
# python (anywhere in the repo)
python -c "import json, re, sys; \
  s = open('contracts/contracts.json').read(); \
  s = re.sub(r'(?m)//.*$', '', s); \
  json.loads(s)"   # validates parseability
```

## Generation targets

### Backend (Pydantic v2, both services)

Each top-level key becomes a Pydantic model in
`services/<svc>/app/contracts/models.py`. Field types follow the
notation key in the `_meta` block of `contracts.json`:

- `"uuid"` → `UUID`
- `"iso8601"` → `datetime` (UTC, tz-aware)
- `"float 0-1"` → `confloat(ge=0.0, le=1.0)`
- `"integer 1-10"` → `conint(ge=1, le=10)`
- `"a | b | c"` → `Literal["a", "b", "c"]`
- trailing `"?"` or `"| null"` → `Optional[...]`

WebSocket envelopes are `Annotated[Union[...], Field(discriminator="type")]`
keyed on the literal `type` string.

### Frontend (TypeScript)

Each top-level key becomes a `type` alias in `frontend/lib/contracts.ts`.
Same notation rules; `uuid` and `iso8601` are branded string aliases.
The WS envelope union is a discriminated union on `type`.

A future `scripts/gen_contracts.py` will automate both targets. Until
then, hand-write the models and keep them in lockstep with this file.

## Rules

1. **Contracts first.** If a new field is needed at runtime, add it here
   before touching any service code.
2. **Never remove a required field** without bumping `_meta.version` and
   coordinating across all four agents.
3. **Optional means optional.** Don't add fields that "must always be
   present in practice" — either require them, or accept absence in
   every consumer.
4. **Binary frames carry only bytes.** All metadata travels in a JSON
   envelope. The current binary use case is the Opus blob preceded by
   `WSMessage.AudioSubmitHeader`.
5. **Version bumps follow semver** at the schema level: additive
   optional fields are minor, anything else is major.
