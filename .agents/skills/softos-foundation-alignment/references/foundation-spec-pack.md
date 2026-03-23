# Foundation Spec Pack

Create foundation specs under `specs/000-foundation/`.

## Required Spec Set

1. `<project>-foundation-alignment.spec.md`
2. `<project>-coding-style-and-quality-contract.spec.md`
3. `<project>-runtime-capability-skill-governance.spec.md`

## Mandatory Frontmatter Fields

- `schema_version: 2`
- `name`
- `description`
- `status: draft` (until approved)
- `owner`
- `depends_on`
- `required_runtimes`
- `required_services`
- `required_capabilities`
- `targets`

## Mandatory Body Sections

- `Objetivo`
- `Contexto`
- `Problema a resolver`
- `Alcance` (`Incluye` / `No incluye`)
- `Repos afectados`
- `Resultado esperado`
- `Reglas de negocio`
- `Flujo principal`
- `Contrato funcional`
- `Criterios de aceptacion`
- `Test plan`
- `Rollout`
- `Rollback`

## Foundation-specific Acceptance Criteria (minimum)

Each foundation spec should assert at least:

- Declarative contract exists and is versioned in root.
- Repo routing via `targets` is unambiguous.
- CI/test contracts are runnable and mapped by runtime.
- Skills/runtimes/capabilities referenced by specs exist in manifests.
- `flow spec review`, `flow spec approve`, and `flow ci spec` pass.

## Testability Rule for Foundation Specs

Include `[@test]` references per affected repo. If tests are absent:

1. Create a minimal valid test file following repo `test_runner`.
2. Point `[@test]` to that file.
3. Keep the test as smoke placeholder until implementation slices replace it.
