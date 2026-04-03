FLOW = python3 ./flow

# ── Init ─────────────────────────────────────────────────────────────

.PHONY: init first-run submodules hooks-install

init: submodules hooks-install first-run ## Bootstrap root-only: submódulos + hooks + flow init

first-run:
	$(FLOW) init $(ARGS)

submodules:
	git submodule update --init --recursive

hooks-install:
	git config core.hooksPath scripts/git-hooks

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

.PHONY: sh sh-service sh-db

sh:
	$(FLOW) stack sh workspace

sh-service:
	@if [ -z "$(SERVICE)" ]; then echo "usage: make sh-service SERVICE=<compose_service>"; exit 2; fi
	$(FLOW) stack sh $(SERVICE)

sh-db:
	$(FLOW) stack exec db -- mysql -u app -papp app_dev

# ── Dev servers ──────────────────────────────────────────────────────

.PHONY: serve

serve:
	@echo "Root-only chassis: define explicit service command."
	@echo "Example: make flow ARGS='stack exec <service> -- <command>'"

# ── Dependencias ─────────────────────────────────────────────────────

.PHONY: install install-service

install:
	$(FLOW) stack exec workspace -- sh -lc 'if [ -f composer.json ]; then composer install; elif [ -f package.json ]; then pnpm install; else echo "skip install: no composer.json/package.json in workspace root"; fi'

install-service:
	@if [ -z "$(SERVICE)" ]; then echo "usage: make install-service SERVICE=<compose_service>"; exit 2; fi
	$(FLOW) stack exec $(SERVICE) -- sh -lc 'if [ -f composer.json ]; then composer install; elif [ -f package.json ]; then pnpm install; else echo "skip install: no composer.json/package.json"; fi'

# ── Cleanup ──────────────────────────────────────────────────────────

.PHONY: clean nuke

clean:
	$(FLOW) stack down

nuke: ## Borra contenedores, volúmenes e imágenes del proyecto
	$(FLOW) stack down --volumes --rmi-local

# ── Help ─────────────────────────────────────────────────────────────

.PHONY: help
.PHONY: flow flow-doctor flow-status workspace stack tessl bmad skills providers submodule-doctor submodule-sync secrets drift ci release infra

flow:
	$(FLOW) $(ARGS)

flow-doctor:
	$(FLOW) doctor

flow-status:
	$(FLOW) status

stack:
	$(FLOW) stack $(ARGS)

workspace:
	$(FLOW) workspace exec -- $(ARGS)

tessl:
	$(FLOW) tessl -- $(ARGS)

bmad:
	$(FLOW) bmad -- $(ARGS)

skills:
	$(FLOW) skills $(ARGS)

providers:
	$(FLOW) providers $(ARGS)

submodule-doctor:
	$(FLOW) submodule doctor $(ARGS)

submodule-sync:
	$(FLOW) submodule sync $(ARGS)

secrets:
	$(FLOW) secrets $(ARGS)

drift:
	$(FLOW) drift $(ARGS)

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
	@echo "    make init            Bootstrap root-only (submódulos + hooks + flow init)"
	@echo "    make first-run       Ejecuta flow init (secrets + stack + doctor + status)"
	@echo "    make submodules      Inicializa/actualiza submódulos git"
	@echo "    make hooks-install   Configura hooks versionados del workspace"
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
	@echo "    make sh-service SERVICE=<svc> Shell en un servicio especifico"
	@echo "    make sh-db           Consola MySQL"
	@echo ""
	@echo "  Dev servers:"
	@echo "    make serve           Muestra uso para ejecutar comandos por servicio"
	@echo ""
	@echo "  Dependencias:"
	@echo "    make install           Instala deps en workspace root (si aplica)"
	@echo "    make install-service SERVICE=<svc> Instala deps en servicio especifico"
	@echo ""
	@echo "  Cleanup:"
	@echo "    make clean           Detiene y elimina contenedores"
	@echo "    make nuke            Detiene, elimina volúmenes e imágenes"
	@echo ""
	@echo "  Stack Control Plane:"
	@echo "    make workspace ARGS='python3 ./flow ci spec --all' Ejecuta un comando arbitrario dentro del workspace"
	@echo "    make stack ARGS='ps'            Ejecuta flow stack"
	@echo "    make tessl ARGS='whoami'        Ejecuta Tessl via flow"
	@echo "    make bmad ARGS='--help'         Ejecuta BMAD via flow"
	@echo "    make skills ARGS='doctor'       Gestiona skills versionadas del workspace"
	@echo "    make providers ARGS='doctor'    Gestiona providers de release e infra"
	@echo "    make submodule-doctor           Valida estado/punteros de submódulos"
	@echo "    make submodule-sync             Sincroniza submódulos y stagea gitlinks"
	@echo "    make secrets ARGS='doctor'      Gestiona secrets por adapters agnósticos"
	@echo "    make drift ARGS='check --all'   Ejecuta drift detection estático"
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
