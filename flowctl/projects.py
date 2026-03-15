from __future__ import annotations

from typing import Iterable


def repo_placeholder_text(root_repo_name: str, repo_name: str, agent_skill_refs: Iterable[str] | None = None) -> tuple[str, str]:
    skill_refs = [str(item).strip() for item in (agent_skill_refs or []) if str(item).strip()]
    skill_block = []
    if skill_refs:
        skill_block = [
            "## Suggested agent skills",
            "",
            *[f"- `{item}`" for item in skill_refs],
            "",
        ]

    agents = "\n".join(
        [
            "# AGENTS.md",
            "",
            "## Scope",
            "",
            f"Estas reglas aplican a `{repo_name}/**`.",
            "",
            "## Role",
            "",
            f"`{repo_name}` es un repo de implementacion de codigo.",
            "",
            "## Required reading order",
            "",
            "1. la spec del root que dispara el trabajo",
            f"2. `{root_repo_name}/specs/000-foundation/**` relevantes",
            "3. este archivo",
            "",
            *skill_block,
            "## Rules",
            "",
            "- no crear specs locales como fuente de verdad paralela",
            "- implementar solo lo que este cubierto por `targets` del root",
            "- mantener tests y codigo alineados con la spec del root",
            "- si el cambio requiere ampliar alcance, actualizar primero la spec del root",
            "",
        ]
    )
    readme = "\n".join(
        [
            f"# {repo_name}",
            "",
            "Placeholder del repo de implementacion.",
            "",
            "Reemplazalo por un repo real o por un submodulo Git cuando conectes este workspace a un producto.",
            "",
        ]
    )
    return agents, readme
