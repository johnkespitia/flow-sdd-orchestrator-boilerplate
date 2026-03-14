# AGENTS.md

## Scope

Estas reglas aplican a `frontend/**`.

## Role

`frontend` es un repo de implementacion de codigo.

## Required reading order

1. la spec del root que dispara el trabajo
2. `workspace-root/specs/000-foundation/**` relevantes
3. este archivo

## Rules

- no crear specs locales como fuente de verdad paralela
- implementar solo lo que este cubierto por `targets` del root
- mantener tests y codigo alineados con la spec del root
- si el cambio requiere ampliar alcance, actualizar primero la spec del root
