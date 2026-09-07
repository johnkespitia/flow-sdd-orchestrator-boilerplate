# Recursos de ejecución OpenCode (SoftOS V1)

> Fuente en inglés: [OpenCode Execution Resources](../opencode-execution-resources.md)

Este documento es el contrato de producto, propiedad del repositorio, para los recursos
lógicos OpenCode de SoftOS. Distingue la configuración portable del repositorio del
estado local de OpenCode en la máquina, y la ejecución local mediante worker/profile de
la ejecución directa en la nube.

No codifica proveedores concretos, modelos concretos, credenciales, tokens, payloads de
autenticación ni rutas absolutas específicas de una estación de trabajo como verdad de
producto de SoftOS.

## 1. Límites de propiedad

| Superficie | Posee | No debe poseer |
| --- | --- | --- |
| SoftOS Core / política / adapters | IDs de recursos lógicos, capacidades, disponibilidad, capacidad, nivel de coste, prioridad de selección, semántica de fallos, invocación agnóstica al modelo | Ramas por identidad de proveedor/modelo, flags CLI `--model` / `--provider` / `--resource`, credenciales |
| Registro de executors + recursos de `workspace.config.json` | IDs de harness executor, ejecutables subyacentes, metadatos de recursos lógicos (incluida la capacidad local `1`) | Tokens, nombres de modelos Free/Go permanentes, cuerpo del prompt/profile del worker local |
| `opencode.json` del repositorio | Profile portable `softos-local-worker` (configuración acotada del worker local) | Secretos, rutas absolutas específicas de máquina, contratos de producto con proveedor/modelo concreto |
| Harness de ejecución de procesos | Selección de recursos antes del lanzamiento, propagación del ID de recurso lógico, merge validado del overlay de entorno local al proceso | Reemplazo completo del entorno, serialización de credenciales, flags de modelo en argv del adapter |
| `~/.config/opencode/**`, wrappers, almacenes de auth, overrides de env | Materialización local de máquina (auth, inventario temporal de modelos, endpoints locales, wrappers opcionales de estación de trabajo) | Política canónica de producto de SoftOS |

`docs/opencode-local-executor.md` conserva notas históricas de diagnóstico de estaciones
de trabajo. Este documento es el contrato de recursos V1.

## 2. Recursos lógicos

SoftOS representa tres recursos lógicos detrás de la familia de adapters `opencode`
existente. Los IDs de executor siguen siendo identidades del harness; los recursos
lógicos hacen referencia a un executor subyacente.

| Recurso lógico | Coste/nivel | Capacidad | Executor subyacente | Resolución de modelo |
| --- | --- | ---: | --- | --- |
| `opencode-local` | local | **1** | executor wrapper local (`opencode-softos`) | Propiedad del profile `softos-local-worker` del repositorio; Core no ramifica según identidad de modelo o proveedor |
| `opencode-free` | cloud/free | conservadora | OpenCode directo genérico (`opencode`) | Selección dinámica entre candidatos Free disponibles actualmente; sin nombre permanente de modelo Free |
| `opencode-go` | cloud/paid-low | conservadora | El mismo OpenCode directo genérico cuando existe evidencia de auth | Dinámica tras autenticación gestionada por OpenCode; inicia en `AUTH_UNCONFIGURED`; sin nombre permanente de modelo Go |

Core y los adapters genéricos permanecen agnósticos de modelo/proveedor. SoftOS no añade
flags CLI `--resource`, `--model` ni `--provider` en V1. El legado
`flow agent run <executor-id> ...` continúa funcionando; un selector posicional puede
resolverse primero como ID de recurso lógico y luego como su executor subyacente.

## 3. Ejecución mediante worker/profile local (`opencode-local`)

Ruta de ejecución local:

```text
SoftOS selecciona el recurso lógico opencode-local
  -> executor subyacente opencode-local (ejecutable: opencode-softos)
  -> profile softos-local-worker del repositorio desde opencode.json
  -> el proceso OpenCode usa ese worker/profile
  -> la selección de modelo/proveedor permanece dentro del worker/profile + estado OpenCode local de máquina
```

Contrato:

- `opencode.json` es la **fuente portable canónica** de la definición de
  `softos-local-worker` (prompt acotado, modo, presupuesto de pasos, permisos).
- El profile omite deliberadamente campos de producto `model` / `provider` concretos
  para que SoftOS Core permanezca agnóstico de identidad. Cualquier endpoint local o
  elección concreta de modelo es materialización local de OpenCode en la máquina, no un
  contrato del registro de SoftOS.
- La capacidad lógica se mantiene en **1**. Prefiera una sesión fresca y acotada de
  worker por Patch Unit adecuado; no asigne monolíticamente un slice completo de producto
  al recurso local.
- SoftOS no codifica permanentemente el nombre del worker en argv del adapter. Los
  lanzamientos locales de SoftOS usan la ruta local wrapper/executor para que el proceso
  seleccione `softos-local-worker` sin flags de modelo genéricos.
- La configuración del repositorio no define un `default_agent` de todo el proyecto que
  los procesos Free/Go de nube puedan heredar. La selección del worker para ejecuciones
  locales de SoftOS se limita al proceso de la ruta del recurso local.

## 4. Ejecución directa en la nube (`opencode-free` / `opencode-go`)

Ruta de ejecución en la nube:

```text
SoftOS selecciona el recurso lógico opencode-free u opencode-go
  -> executor genérico subyacente opencode (ejecutable: opencode)
  -> resolución dinámica del modelo para ese recurso de nube
  -> overlay validado OPENCODE_CONFIG_CONTENT, local al proceso, transporta solo el modelo resuelto
  -> lanzamiento del subproceso (sin herencia de softos-local-worker / wrapper local)
```

Contrato:

- Free y Go permanecen recursos OpenCode de nube **genéricos/directos**. No deben
  ejecutarse mediante `opencode-softos` / `softos-local-worker`, ni heredar la
  configuración de modelo/proveedor/profile del worker local salvo que el mismo
  modelo/proveedor haya sido resuelto independientemente para ese recurso de nube.
- Los modelos Free/Go resueltos deben afectar al **proceso OpenCode generado**, no solo
  a diagnósticos. El harness aplica un overlay validado de entorno local al proceso
  (normalmente `OPENCODE_CONFIG_CONTENT` con el objeto de modelo resuelto).
- El overlay es solo local al proceso: nunca se persiste en Git ni en evidencia; no
  contiene credenciales; no persiste payloads de proveedor/auth sin procesar; hace merge
  sobre una copia del entorno heredado en lugar de reemplazarlo por completo; y limpia
  carriers de configuración OpenCode local para que Free/Go no adopten la selección del
  worker/profile local.
- `opencode-go` no puede lanzarse mientras su disponibilidad sea `AUTH_UNCONFIGURED`.
  La autenticación sigue siendo externa y local a la máquina; SoftOS no inventa nombres
  de token, almacena secretos ni declara auth sin evidencia OpenCode admitida.

## 5. Configuración portable del repositorio frente a estado local de máquina

Canónico (repositorio):

- `opencode.json` — profile portable `softos-local-worker` y activación MCP existente
  del proyecto.
- `workspace.config.json` — executors agnósticos al modelo y metadatos de recursos
  lógicos.

Local de máquina (no es verdad canónica del producto):

- `~/.config/opencode/**`
- wrappers de estación de trabajo como `opencode-softos`
- almacenes de autenticación e inventarios temporales de modelos
- overrides de entorno y endpoints locales

No trate `~/.config/opencode` como la fuente portable de verdad de SoftOS. No haga
commit de credenciales, tokens, payloads de auth ni rutas absolutas específicas de
máquina.

## 6. No objetivos explícitos de este contrato

- Este documento no implica cambios en scheduler durable, leases, base de datos de runs,
  Gateway, LangGraph, secret store, comportamiento de merge ni de release.
- Ninguna identidad concreta de modelo o proveedor de un vendor (incluidos experimentos
  temporales de estación de trabajo) es un contrato de producto de SoftOS.
- No hay expansión de la CLI de SoftOS para `--resource`, `--model` ni `--provider`.
- Instalar o autenticar OpenCode sigue siendo responsabilidad del operador fuera de Git.
