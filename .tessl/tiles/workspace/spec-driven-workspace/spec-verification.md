# Spec Verification

## Manual Workflow

1. comparar diff de spec con diff de codigo y tests
2. ejecutar los tests enlazados con `[@test]`
3. revisar los archivos de `targets`
4. actualizar la spec en el mismo cambio si cambia el comportamiento

## Drift

Se considera drift cuando:

- cambia el codigo sin cambiar la spec correspondiente
- aparece un test nuevo sin requerimiento asociado
- un `target` o `[@test]` apunta a una ruta inexistente
