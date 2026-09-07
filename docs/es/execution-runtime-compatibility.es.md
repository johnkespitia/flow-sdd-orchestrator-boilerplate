# Compatibilidad del Runtime de Ejecucion y Limite del Sandbox del Supervisor

English source: [Execution Runtime Compatibility and Supervisor Sandbox Boundary](../execution-runtime-compatibility.md)

Source: `docs/execution-runtime-compatibility.md`
Last updated: 2026-09-07

Este documento registra el limite de plataforma de SoftOS que hoy esta validado entre un supervisor y un runtime de ejecucion.
Complementa `docs/opencode-execution-resources.md` y `specs/features/coding-execution-runtime-v1.spec.md`.

Documenta el comportamiento observado y el contrato arquitectonico. No implementa el limite del runtime.

## Ubicaciones canonicas

- Configuracion base de ejecucion del workspace: `workspace.config.json`
- Spec V1 de Coding Execution Runtime: `specs/features/coding-execution-runtime-v1.spec.md`
- Contrato de recursos de Coding Execution Runtime: `docs/opencode-execution-resources.md`
- Base de compatibilidad runtime/plataforma: este documento

## Comportamiento actual validado

Validado en Codex CLI 0.153.4 sobre WSL/Linux.

| Comando u observacion | Resultado | Lo que muestra |
| --- | --- | --- |
| `codex doctor` | fs restringido + red restringida; approval `OnRequest`; managed proxy no configurado | El supervisor ya esta en sandbox y no debe asumir alcance tipo host |
| `codex exec -s workspace-write` | approval `never`; sandbox `workspace-write` | La ejecucion con workspace-write sigue dentro de un limite restringido |
| `codex exec -a on-request` | rechazado | `codex exec` no acepta esa forma de flag de approval |
| `codex exec -c 'approval_policy="on-request"'` | aceptado por el parseo estricto, pero approval sigue `never` | Aceptar el parseo no implica cambiar el limite de ejecucion |
| `codex exec --approve-for-me --sandbox workspace-write` | rechazado como combinacion invalida | Los flags de conveniencia no anulan la seleccion explicita del sandbox |
| `getent hosts api2.cursor.sh` y `curl https://api2.cursor.sh` dentro de workspace-write | DNS/HTTPS bloqueados; `GETENT_EXIT=2`, `CURL_EXIT=6` | La conectividad esta limitada por el sandbox del supervisor |
| ejecutores hijo lanzados por Codex | heredan el limite de sandbox/red del supervisor | Disponibilidad de executor no es lo mismo que compatibilidad con el runtime |
| la politica de shell del router | puede rechazar patrones de shell peligrosos de forma independiente al sandbox de Linux | El rechazo por politica de comando y el rechazo por sandbox son controles distintos |

Estas observaciones son evidencia especifica de la version y del entorno. Son la base actual de validacion, no una garantia para futuros hosts o futuras versiones del CLI.

## Contrato arquitectonico

SoftOS trata la disponibilidad del executor y la compatibilidad con el runtime como preocupaciones separadas.

- La disponibilidad del executor responde si un CLI configurado existe y puede invocarse.
- La compatibilidad del runtime responde si el runtime de ejecucion seleccionado puede satisfacer las capacidades requeridas del host.
- Un supervisor no debe asumir acceso irrestricto a red, Docker daemon, GPU, capacidades privilegiadas del host o conectividad arbitraria con executors externos.
- Esas capacidades pertenecen al limite del runtime de ejecucion, no a la politica de SoftOS Core.

Vocabulario de capacidades:

| Capability | Meaning |
| --- | --- |
| `network_required` | El trabajo necesita acceso a red mediado por el runtime, no una suposicion implicita de alcance del host |
| `docker_required` | El trabajo necesita Docker o mediacion equivalente de runtime de contenedor |
| `gpu_required` | El trabajo necesita acceso a GPU o mediacion de runtime con GPU |
| `local_service_required` | El trabajo necesita un servicio local o endpoint local provisto por la politica del runtime o de la maquina |

SoftOS registra los requerimientos de capacidad como etiquetas abstractas. Los destinos reales, endpoints, allowlists, proxies y reglas de red especificas del host pertenecen a la politica del runtime o de la maquina, no a la politica del producto en el repositorio.
No hardcodear dominios de proveedor, endpoints de proveedor o hostnames especificos de vendors en la documentacion de SoftOS Core.

## Capacidad futura, aun no implementada

Las siguientes son capacidades futuras del runtime, no comportamiento actual de SoftOS:

- mediacion de red administrada
- allowlists por runtime
- ruteo por proxy para clases especificas de executor
- mediacion de puente Docker expuesta al supervisor como solucion generica
- listas de destinos especificas de proveedor embebidas en la politica del repositorio

Si se agregan mas adelante, deben describirse como capacidades del runtime y validarse contra la politica actual del workspace. No deben presentarse como ya configuradas.
