# Política de reintentos: feedback a providers externos (Ola B / T06)

## Comportamiento

`gateway/app/feedback.py` ejecuta el script del provider (`workspace.providers.json` → `feedback.providers.*.entrypoint`) con reintentos ante fallos **transitorios**.

- **Transitorio:** código de salida ≠ 0 y no clasificado como permanente → se reintenta con backoff exponencial acotado.
- **Permanente (sin reintento adicional):** código de salida `2`, o `stderr` que comience por `PERMANENT:`.

## Configuración

### `workspace.providers.json`

En la sección `feedback`:

- `retry_policy`: aplica a todos los providers (claves opcionales: `max_attempts`, `initial_delay_s`, `max_delay_s`, `backoff_multiplier`).
- Por provider: mismo objeto bajo `providers.<nombre>.retry_policy` para sobrescribir.

### Variables de entorno (override global)

| Variable | Significado |
| --- | --- |
| `SOFTOS_FEEDBACK_RETRY_MAX_ATTEMPTS` | Máximo de intentos (≥ 1). |
| `SOFTOS_FEEDBACK_RETRY_INITIAL_DELAY_S` | Primera espera entre intentos (segundos). |
| `SOFTOS_FEEDBACK_RETRY_MAX_DELAY_S` | Tope de espera entre intentos. |
| `SOFTOS_FEEDBACK_RETRY_BACKOFF_MULTIPLIER` | Multiplicador exponencial (≥ 1). |

El merge es: defaults → env → `feedback.retry_policy` → `providers.<id>.retry_policy`.

## Resultado

La respuesta del último intento incluye `attempts_used` en el diccionario retornado a quien consuma `send_feedback` / `send_feedback_event` (compatibilidad: campos previos `provider`, `return_code`, `stdout`, `stderr` se mantienen).
