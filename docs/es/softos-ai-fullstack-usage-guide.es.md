# Como la IA entiende y usa SoftOS al maximo

English source: [docs/softos-ai-fullstack-usage-guide.md](../softos-ai-fullstack-usage-guide.md)

Source: `docs/softos-ai-fullstack-usage-guide.md`  
Last updated: 2026-05-07

Este documento explica como un agente de IA debe razonar, ejecutar y validar trabajo en SoftOS para maximizar confiabilidad y throughput.

## 1. Modelo mental de la IA

SoftOS es orquestacion guiada por specs, no coding ad-hoc.

La IA debe tratar:

- `specs/**` como fuente de verdad.
- `flow` como control plane de orquestacion.
- reportes CI y evidencia de release como criterio de cierre.

## 2. Orden correcto de ejecucion

1. Leer primero la spec relevante.
2. Resolver repos target y contexto runtime.
3. Cargar contexto de skills del repo.
4. Implementar solo dentro de targets declarados.
5. Ejecutar validaciones requeridas.
6. Producir evidencia y cerrar el loop.

## 3. Contrato de seguridad para cambios

1. No inferir expansion mayor de alcance sin actualizar spec.
2. No marcar done sin evidencia de spec/CI.
3. No tratar `.flow/**` como verdad por encima de `specs/**`.
4. Preferir diffs minimos y deterministas por slice.

## 4. Flujo de alto apalancamiento

1. **Parse de spec**: extraer goals, non-goals, targets, stop conditions.
2. **Mapeo de superficies**: mapear cada edicion prevista a rutas target.
3. **Implementacion**: aplicar cambios acotados.
4. **Validacion**: correr gates de `flow` y tests por repo.
5. **Evidencia**: conservar salidas y artefactos ligados a la slice.
6. **Release readiness**: verificar preflight antes de promote.

## 5. Razonamiento multi-repo

La IA debe evitar leakage cross-repo por defecto.

- Cambios en repo A no deben modificar repo B en silencio.
- Comportamiento compartido debe representarse primero en specs root.
- Comandos runtime/tooling deben ejecutarse en el servicio correcto del repo.

## 6. Logica de cierre CI-first

El criterio de cierre de IA debe incluir:

- spec guard en pass
- drift check en pass
- contract verify en pass
- repo CI en pass donde aplique
- sin bloqueos de gate pendientes

## 7. Disciplina de promote

Antes de promote a staging, IA debe verificar:

- readiness del ref remoto source
- readiness de dispatch de workflow
- disponibilidad de auth en gateway/runtime
- migraciones sensibles a rollout siguen gateadas

La salida es binaria:

- `promote dispatchable`
- `promote blocked`

## 8. Inteligencia documental

La IA debe mantener docs ejecutables y actuales:

- actualizar docs operativas con cambios de comportamiento
- mantener politica EN canonico + ES espejo
- asegurar links cruzados y metadata
- preferir lenguaje conciso y verificable operativamente

## 9. Politica de uso de memoria

Si hay tooling de memoria habilitado, IA debe usar memoria solo como contexto consultivo.

- memoria ayuda a recall y continuidad
- memoria nunca reemplaza specs, evidencia CI ni contratos de release

## 10. Checklist de modo full-power para IA

- planificacion spec-first completada
- superficies target acotadas
- contexto runtime/skills cargado
- implementacion aplicada con drift minimo
- gates CI ejecutados y en verde
- preflight de release evaluado
- documentacion actualizada y espejada
- reporte final con evidencia y riesgos residuales
