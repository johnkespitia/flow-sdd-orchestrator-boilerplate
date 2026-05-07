# SoftOS Harness Profiles

English source: [profiles/README.md](../README.md)

Los profiles conectan el Harness Core generico con una organizacion, conjunto
de repositorios, flujo de entrega y toolchain especificos.

## Novedades

- Contrato de profile formalizado en `profiles/<profile-id>/profile.json`.
- Profile de ejemplo agregado en `profiles/example-api-ticket/profile.json`.
- Validacion disponible con `python3 scripts/harness/validate_profile.py --root . --json`.

Un profile define:

- sistemas de tickets y patrones de work item
- formato de mirror de repositorios
- labels y convenciones de PR
- estrategia de staging/deploy/E2E
- canales de comunicacion
- nombres esperados de checks/CI
- reglas de descubrimiento de reviewers/owners
- reglas de redaccion y privacidad

Las politicas core deben permanecer neutrales al proyecto. Los profiles pueden
incluir convenciones especificas, pero deben evitar secretos y enlaces privados
salvo que el profile se mantenga privado/local.

La telemetria de uso/costo se activa con `usage_telemetry` en cada profile. El contrato exige checkpoints en progress updates y resumen de closeout, marcando cada valor como `exact`, `provider_reconciled` o `estimated`.
