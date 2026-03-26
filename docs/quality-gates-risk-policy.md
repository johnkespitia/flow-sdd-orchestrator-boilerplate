# Quality Gates Risk Policy

## Umbrales de riesgo

| Risk level | Reglas deterministicas | Umbral score minimo |
| --- | --- | --- |
| `low` | Write-set acotado sin API/DTO/infra critica | `50` |
| `medium` | Write-set amplio (>=6 targets) | `65` |
| `high` | Cambios en superficies `api/dto/contract/schema` | `80` |
| `critical` | Cambios en `migrations`, `infra`, `security/auth/payment` | `90` |

## Checkpoints por etapa (gates)

- `plan`: `plan-stage-pass`
- `slice_start`: `slice_start-stage-pass`
- `ci_spec`: `ci_spec-stage-pass`, `drift-check-pass`, y para API/DTO tambien `generate-contracts-pass` + `contract-verify-pass`
- `ci_repo`: `ci_repo-stage-pass`
- `ci_integration`: `ci_integration-stage-pass`; para `high/critical` tambien `ci-integration-extended-pass`
- `release_promote`: `confidence-threshold-pass`; para `high/critical` tambien `additional-reviewer-pass`
- `release_verify`: `release_verify-stage-pass`
- `infra_apply`: `infra_apply-stage-pass`

## Score por slice

Score deterministico (0-100):

- CI: `ci_spec` (40) + `ci_repo` (30) + `ci_integration` (15)
- Evidencia de tests: hasta 15 por `linked_tests`
- Criticidad por archivos: bonus por riesgo (`low=20`, `medium=12`, `high=6`, `critical=0`)
- Contrato y drift: `contract_ok` (15) + `drift_ok` (10)
