FLOW = python3 ./flow

# ── Init ─────────────────────────────────────────────────────────────

.PHONY: init submodules

init: submodules up install ## Bootstrap completo: submódulos + servicios + dependencias

submodules:
	git submodule update --init --recursive

# ── Lifecycle ────────────────────────────────────────────────────────

.PHONY: up down build rebuild status logs

up:
	$(FLOW) stack up

down:
	$(FLOW) stack down

build:
	$(FLOW) stack build

rebuild:
	$(FLOW) stack build --no-cache

status:
	$(FLOW) stack ps

logs:
	$(FLOW) stack logs

# ── Shells ───────────────────────────────────────────────────────────

.PHONY: sh sh-backend sh-frontend sh-db

sh:
	$(FLOW) stack sh workspace

sh-backend:
	$(FLOW) stack sh backend

sh-frontend:
	$(FLOW) stack sh frontend

sh-db:
	$(FLOW) stack exec db -- mysql -u app -papp app_dev

# ── Dev servers ──────────────────────────────────────────────────────

.PHONY: serve-backend serve-frontend serve

serve-backend:
	$(FLOW) stack exec backend -- php artisan serve --host=0.0.0.0 --port=8000

serve-frontend:
	$(FLOW) stack exec frontend -- pnpm dev --host 0.0.0.0

serve: ## Arranca backend y frontend en paralelo
	@make serve-backend &
	@make serve-frontend

# ── Dependencias ─────────────────────────────────────────────────────

.PHONY: install-backend install-frontend install

install-backend:
	$(FLOW) stack exec backend -- sh -lc 'if [ -f composer.json ]; then composer install; else echo "skip backend install: composer.json missing"; fi'

install-frontend:
	$(FLOW) stack exec frontend -- sh -lc 'if [ -f package.json ]; then pnpm install; else echo "skip frontend install: package.json missing"; fi'

install: install-backend install-frontend

# ── Cleanup ──────────────────────────────────────────────────────────

.PHONY: clean nuke

clean:
	$(FLOW) stack down

nuke: ## Borra contenedores, volúmenes e imágenes del proyecto
	$(FLOW) stack down --volumes --rmi-local

# ── Help ─────────────────────────────────────────────────────────────

.PHONY: help
.PHONY: flow flow-doctor flow-status stack tessl bmad ci release infra

flow:
	$(FLOW) $(ARGS)

flow-doctor:
	$(FLOW) doctor

flow-status:
	$(FLOW) status

stack:
	$(FLOW) stack $(ARGS)

tessl:
	$(FLOW) tessl -- $(ARGS)

bmad:
	$(FLOW) bmad -- $(ARGS)

ci:
	$(FLOW) ci $(ARGS)

release:
	$(FLOW) release $(ARGS)

infra:
	$(FLOW) infra $(ARGS)

help:
	@echo ""
	@echo "  Spec-Driven Workspace — Comandos disponibles"
	@echo "  ─────────────────────────────────────────"
	@echo ""
	@echo "  Init:"
	@echo "    make init            Bootstrap completo (submódulos + up + install)"
	@echo "    make submodules      Inicializa/actualiza submódulos git"
	@echo ""
	@echo "  Lifecycle:"
	@echo "    make up              Levanta todos los servicios"
	@echo "    make down            Detiene todos los servicios"
	@echo "    make build           Construye las imágenes"
	@echo "    make rebuild         Construye sin cache"
	@echo "    make status          Muestra estado de los servicios"
	@echo "    make logs            Muestra logs en tiempo real"
	@echo ""
	@echo "  Shells:"
	@echo "    make sh              Shell en workspace"
	@echo "    make sh-backend      Shell en backend"
	@echo "    make sh-frontend     Shell en frontend"
	@echo "    make sh-db           Consola MySQL"
	@echo ""
	@echo "  Dev servers:"
	@echo "    make serve-backend   Laravel en :8000"
	@echo "    make serve-frontend  Vite en :5173"
	@echo "    make serve           Ambos en paralelo"
	@echo ""
	@echo "  Dependencias:"
	@echo "    make install-backend   composer install"
	@echo "    make install-frontend  pnpm install"
	@echo "    make install           Ambos"
	@echo ""
	@echo "  Cleanup:"
	@echo "    make clean           Detiene y elimina contenedores"
	@echo "    make nuke            Detiene, elimina volúmenes e imágenes"
	@echo ""
	@echo "  Stack Control Plane:"
	@echo "    make stack ARGS='ps'            Ejecuta flow stack"
	@echo "    make tessl ARGS='whoami'        Ejecuta Tessl via flow"
	@echo "    make bmad ARGS='--help'         Ejecuta BMAD via flow"
	@echo "    make ci ARGS='spec --all'       Ejecuta CI spec-driven"
	@echo "    make release ARGS='status --version v1' Gestiona manifests/promotions"
	@echo "    make infra ARGS='status feature' Gestiona plan/apply de infraestructura"
	@echo ""
	@echo "  Spec-driven flow:"
	@echo "    make flow-doctor     Valida el scaffold SDD del workspace"
	@echo "    make flow-status     Muestra el estado operativo de las features"
	@echo "    make flow ARGS='...' Ejecuta ./flow con argumentos arbitrarios"
	@echo ""

.DEFAULT_GOAL := help
