# Skills Discover

Guía para descubrir, listar e instalar skills en el workspace. Usa este skill cuando necesites buscar skills en tessl.io, skills.sh, o cuando el usuario pida instalar o descubrir skills para un runtime o proyecto.

## Cuándo usar

- El usuario pide buscar skills para un lenguaje o runtime (Go, Python, etc.)
- Necesitas instalar un skill para un proyecto
- Quieres listar skills disponibles en el catálogo del workspace
- El usuario pregunta cómo añadir skills a un proyecto

## Comandos del workspace

```bash
# Buscar skills en tessl.io y skills.sh por término (Skyll API)
python3 ./flow skills discover <query> [--limit 10] [--json]

# Obtener contexto de skills por repo o spec
python3 ./flow skills context --repo <repo> --json
python3 ./flow skills context --spec <spec_slug> --json

# Listar skills del catálogo
python3 ./flow skills list --json

# Instalar un skill (add + sync en un paso)
python3 ./flow skills install <identifier> --provider <tessl|skills-sh> --runtime <runtime>

# Añadir y sincronizar manualmente
python3 ./flow skills add <name> --provider <tessl|skills-sh> --source <source> [--arg=<valor>]...
python3 ./flow skills sync [--provider <tessl|skills-sh>] [--name <entry_name>]
```

## Fuentes externas

- **tessl.io**: Catálogo de tiles y skills de Tessl
- **skills.sh**: Catálogo de skills (ej. `https://github.com/jeffallan/claude-skills` con `--skill golang-pro`)

## Flujo de ejemplo (discovery → add → sync → install)

Ejemplo completo que puedes ejecutar en el workspace:

```bash
# 1. Discovery: buscar skills por término y ver contexto del repo
python3 ./flow skills discover golang --limit 5 --json
python3 ./flow skills context --repo workspace-root --json
python3 ./flow skills list --json

# 2. Add: registrar un skill nuevo (ej. golang-pro desde skills.sh, requiere --arg)
python3 ./flow skills add workspace/my-golang-skill \
  --provider skills-sh \
  --source https://github.com/jeffallan/claude-skills \
  --arg=--skill --arg=golang-pro

# 3. Sync: materializar el skill (ejecuta npx skills add o tessl skill import)
python3 ./flow skills sync --provider skills-sh --name workspace/my-golang-skill --json

# 4. Install (solo cuando el skill no requiere --arg): add + sync + actualizar runtime
python3 ./flow skills install <identifier> --provider tessl --runtime generic

# Alternativa para skills con --arg (ej. golang-pro): tras add+sync, edita
# runtimes/go-api.runtime.json y añade "workspace/my-golang-skill" a agent_skill_refs.
```

Nota: `install` no soporta `--arg`. Para skills.sh con skill concreto (ej. `--skill golang-pro`), usa add + sync y luego añade el nombre del skill a `agent_skill_refs` en `runtimes/<runtime>.runtime.json`. Si el valor de `--arg` empieza con `--`, usa `--arg=valor` (ej. `--arg=--skill`) para evitar que el parser lo interprete como otra opción.

## Prompt para otra IA

Usa este prompt para que otra IA ejecute el flujo y consuma el skill:

```
Tienes acceso al workspace con skills gestionados por `flow`. Tu tarea:

1. Lee el skill `workspace/skills-discover` (contenido en .tessl/tiles/workspace/skills-discover/index.md).
2. Para buscar skills por término: `python3 ./flow skills discover <query> --json` (ej. golang, react, testing).
3. Ejecuta discovery de contexto: `python3 ./flow skills context --repo <repo> --json` para obtener runtime y agent_skill_refs del repo.
4. Ejecuta `python3 ./flow skills list --json` para ver el catálogo actual.
5. Si el usuario pide instalar un skill para un runtime (ej. Go), primero usa `flow skills discover golang --json` para ver candidatos, luego `flow skills add` + `flow skills sync` con source_url y skill_id del candidato elegido.
6. Para consumir el skill: `flow skills context --json` devuelve `agent_skills` con `path` para cada skill. Lee el SKILL.md o index.md en esa ruta (`.agents/skills/<id>/` o `.tessl/tiles/workspace/<tile>/`) y aplica sus instrucciones antes de implementar.
```

## Flujo recomendado

1. Busca skills: `flow skills discover <término>` para ver candidatos por lenguaje o tema
2. Obtén el runtime del repo: `flow skills context --repo <repo> --json`
3. Lista skills del catálogo: `flow skills list --json`
4. Si el skill está en el catálogo, usa `flow skills install` con el identifier y runtime
5. Si no está, usa add + sync con los datos de `flow skills discover --json`

## Próximos pasos sugeridos

- **Detección de runtime**: Si un repo no tiene `runtime` en `workspace.config.json`, inferirlo por el código (go.mod, package.json, etc.) y documentarlo en AGENTS.md.
- **Validación**: `flow skills doctor` ya valida el manifest; extender para verificar que los skills referenciados en runtimes existen en el catálogo.
