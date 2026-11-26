# Module anchors — how to write them

Every Python module under `server/app/` and `server/tests/` carries a **module anchor** at the top of the file (module docstring). Anchors are navigation and policy hints for coding agents — complementary to behavioral rules in [`rules/anchor_standards.xml`](rules/anchor_standards.xml) (grounding, clarify, escalate, learn, stubs).

## Required fields

| Field | Required | Meaning |
|-------|----------|---------|
| `ANCHOR:` | **yes** | Dotted module name (e.g. `app.application.dialogue.graph`) |
| `PURPOSE:` | **yes** | One or two sentences: what this module owns |
| `Dependencies:` | **yes** | Layers/ports this module may call (or `none`) |
| `CRITICAL:` | if any | Hard invariants (cite `ANC-*` / `CS-*` rule ids when relevant) |
| `DO:` | if useful | Bullet list of required practices |
| `DONT:` | if useful | Bullet list of forbidden shortcuts |

## Template

```python
"""
ANCHOR: app.example.module
PURPOSE: Short responsibility statement.
Dependencies: app.domain, persistence port
CRITICAL: Never invent answers without citations (ANC-GROUND-01).
DO:
- Resolve adapters via DI factories
DONT:
- Import Stub* or Http* from application services
"""
```

## Conventions

1. **One ANCHOR per file** — package `__init__.py` files get anchors too.
2. **English identifiers** in `ANCHOR` / field labels; Russian OK only inside purpose text if describing UX copy.
3. **Prefer citing rule ids** from `rules/anchor_standards.xml`, `rules/coding_standards.xml`, etc., in `CRITICAL` / `DONT`.
4. **Keep anchors short** — they are not a second README; link to `project_context.md` / `semantic_graph.xml` for depth.
5. **Update anchors when ownership moves** — if a module’s Dependencies change, update the header in the same PR.
6. **Behavioral anchors vs module anchors** — product policies (ground / clarify / escalate / learn / stubs) live in `rules/anchor_standards.xml`; module headers point at those rules, they do not replace them.

## Where to look next

| Need | File |
|------|------|
| Module map / edges | [`semantic_graph.xml`](semantic_graph.xml) |
| Stack & REST | [`project_context.md`](project_context.md) |
| Ground / clarify / escalate | [`rules/anchor_standards.xml`](rules/anchor_standards.xml) |
| Layout & stub naming | [`rules/coding_standards.xml`](rules/coding_standards.xml) |
| Phase gates | [`dev_plan.xml`](dev_plan.xml) |
