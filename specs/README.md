# Root Specs

`specs/**` es la fuente de verdad del sistema.

## Regla de alcance

- Las specs del root describen comportamiento, arquitectura, contratos y slices del sistema.
- Los `targets` apuntan a archivos reales dentro de los repos configurados en `workspace.config.json`
  o el propio root.
- Los submodulos implementan codigo; el root orquesta y conserva la trazabilidad.

## Layout

- `000-foundation/`: reglas base del sistema y del flujo SDD
- `domains/`: lenguaje de dominio y contratos estables
- `features/`: features, waves y slices ejecutables
