from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from flowctl.specs import frontmatter_status_allows_execution

SEMVER_TAG_PATTERN = re.compile(r"^v(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)$")
CONVENTIONAL_COMMIT_PATTERN = re.compile(
    r"^(?P<type>[a-z]+)(?:\([^)]+\))?(?P<breaking>!)?: (?P<description>.+)$"
)

CONVENTIONAL_SECTIONS = {
    "feat": "Added",
    "fix": "Fixed",
    "perf": "Changed",
    "refactor": "Changed",
    "build": "Changed",
    "ci": "Changed",
    "chore": "Changed",
    "docs": "Docs",
    "test": "Tests",
    "revert": "Changed",
}


def _provider_auth_env() -> dict[str, str]:
    env: dict[str, str] = {}
    gh_token = os.environ.get("GH_TOKEN", "").strip()
    github_token = os.environ.get("GITHUB_TOKEN", "").strip()
    softos_token = os.environ.get("SOFTOS_GITHUB_TOKEN", "").strip()

    if gh_token:
        env["GH_TOKEN"] = gh_token
    elif softos_token:
        env["GH_TOKEN"] = softos_token

    if github_token:
        env["GITHUB_TOKEN"] = github_token
    elif softos_token:
        env["GITHUB_TOKEN"] = softos_token

    if softos_token:
        env["SOFTOS_GITHUB_TOKEN"] = softos_token

    return env


def _as_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if not text:
        return default
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _provider_release_contract(provider_config: dict[str, object]) -> dict[str, object]:
    contract = provider_config.get("contract", {})
    if not isinstance(contract, dict):
        contract = {}
    verify_mode = str(contract.get("verify_mode", "")).strip().lower()
    return {
        "requires_source_ref": _as_bool(contract.get("requires_source_ref")),
        "requires_target_ref": _as_bool(contract.get("requires_target_ref")),
        "supports_pr_promotion": _as_bool(contract.get("supports_pr_promotion")),
        "requires_post_deploy_verify": _as_bool(contract.get("requires_post_deploy_verify")),
        "verify_mode": verify_mode,
    }


def _repo_deploy_contract(repo_payload: dict[str, object], environment: str) -> dict[str, object]:
    deploy = repo_payload.get("deploy")
    if not isinstance(deploy, dict):
        return {
            "promotion_mode": "direct",
            "deploy_requires_pr": False,
            "deploy_requires_healthcheck": False,
            "post_deploy_smoke_required": False,
            "healthcheck_retry": {},
        }

    contract = deploy.get("contract", {})
    if not isinstance(contract, dict):
        contract = {}
    by_env = deploy.get("contract_by_env")
    if isinstance(by_env, dict):
        env_contract = by_env.get(environment, {})
        if isinstance(env_contract, dict):
            contract = {**contract, **env_contract}

    promotion_strategy = deploy.get("promotion_strategy", {})
    if not isinstance(promotion_strategy, dict):
        promotion_strategy = {}
    promotion_mode = str(
        promotion_strategy.get("mode", contract.get("promotion_mode", ""))
    ).strip().lower()
    if not promotion_mode:
        promotion_mode = "pull_request" if _as_bool(contract.get("deploy_requires_pr")) else "direct"

    verify = deploy.get("verify", {})
    if not isinstance(verify, dict):
        verify = {}
    verify_by_env = deploy.get("verify_by_env")
    if isinstance(verify_by_env, dict):
        env_verify = verify_by_env.get(environment, {})
        if isinstance(env_verify, dict):
            verify = {**verify, **env_verify}
    retry = verify.get("retry", {})
    if not isinstance(retry, dict):
        retry = {}

    return {
        "promotion_mode": promotion_mode,
        "deploy_requires_pr": _as_bool(contract.get("deploy_requires_pr"), promotion_mode == "pull_request"),
        "deploy_requires_healthcheck": _as_bool(
            contract.get("deploy_requires_healthcheck"),
            str(verify.get("mode", "")).strip().lower() == "healthcheck",
        ),
        "post_deploy_smoke_required": _as_bool(contract.get("post_deploy_smoke_required")),
        "healthcheck_retry": retry,
    }

def _repo_deploy_provider(repo_payload: dict[str, object], environment: str) -> str:
    deploy = repo_payload.get("deploy")
    if not isinstance(deploy, dict):
        return ""
    by_env = deploy.get("providers_by_env")
    if isinstance(by_env, dict):
        scoped = str(by_env.get(environment, "")).strip()
        if scoped:
            return scoped
    return str(deploy.get("provider", "")).strip()


def _repo_deploy_env(repo_payload: dict[str, object], environment: str) -> dict[str, str]:
    deploy = repo_payload.get("deploy")
    if not isinstance(deploy, dict):
        return {}
    scoped: dict[str, str] = {}
    by_env = deploy.get("env_by_env")
    if isinstance(by_env, dict):
        raw_env = by_env.get(environment, {})
        if isinstance(raw_env, dict):
            for key, value in raw_env.items():
                scoped[str(key)] = str(value)
    raw_common = deploy.get("env")
    if isinstance(raw_common, dict):
        for key, value in raw_common.items():
            scoped[str(key)] = str(value)
    return scoped


def _promotion_strategy_mode(repo_payload: dict[str, object], environment: str) -> str:
    contract = _repo_deploy_contract(repo_payload, environment)
    return str(contract.get("promotion_mode", "direct")).strip().lower() or "direct"


def _resolve_release_provider_from_workspace(
    *,
    args,
    manifest: dict[str, object],
    workspace_config: dict[str, object],
    root_repo: str,
) -> tuple[str, dict[str, str], list[str]]:
    if getattr(args, "provider", None):
        return str(args.provider).strip(), {}, []

    repos_section = workspace_config.get("repos", {})
    if not isinstance(repos_section, dict):
        return "", {}, []

    manifest_repos = manifest.get("repos", {})
    if not isinstance(manifest_repos, dict):
        return "", {}, []

    candidate_repos = [str(repo).strip() for repo in manifest_repos if str(repo).strip()]
    deploy_repo = str(getattr(args, "deploy_repo", "") or "").strip()
    if deploy_repo:
        if deploy_repo not in candidate_repos:
            raise SystemExit(
                f"`--deploy-repo {deploy_repo}` no pertenece al release `{args.version}`."
            )
        candidate_repos = [deploy_repo]

    non_root_candidates = [repo for repo in candidate_repos if repo != root_repo]
    if non_root_candidates:
        candidate_repos = non_root_candidates

    selected: list[tuple[str, str]] = []
    merged_env: dict[str, str] = {}
    for repo in candidate_repos:
        repo_payload = repos_section.get(repo)
        if not isinstance(repo_payload, dict):
            continue
        provider = _repo_deploy_provider(repo_payload, args.environment)
        if not provider:
            continue
        selected.append((repo, provider))
        merged_env.update(_repo_deploy_env(repo_payload, args.environment))

    unique_providers = sorted({provider for _, provider in selected})
    if len(unique_providers) > 1:
        details = ", ".join(f"{repo}:{provider}" for repo, provider in selected)
        raise SystemExit(
            "Hay multiples providers de deploy en el release. "
            f"Usa `--provider` o `--deploy-repo`. Detectados: {details}."
        )
    if len(unique_providers) == 1:
        return unique_providers[0], merged_env, [repo for repo, _ in selected]
    return "", merged_env, []


def _release_slice_findings(
    slug: str,
    state: dict[str, object],
    *,
    plan_root: Path,
    root: Path,
    rel: Callable[[Path], str],
) -> list[str]:
    plan_path = plan_root / f"{slug}.json"
    if not plan_path.exists():
        return [f"No existe plan para `{slug}`. Ejecuta `python3 ./flow plan {slug}` antes del release."]

    try:
        plan_payload = json.loads(plan_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"El plan `{rel(plan_path)}` no contiene JSON valido: {exc}."]

    slices = plan_payload.get("slices", [])
    if not isinstance(slices, list) or not slices:
        return [f"El plan `{rel(plan_path)}` no declara slices verificables."]

    slice_results = state.get("slice_results", {})
    if not isinstance(slice_results, dict):
        slice_results = {}

    findings: list[str] = []
    for slice_payload in slices:
        if not isinstance(slice_payload, dict):
            continue
        slice_name = str(slice_payload.get("name", "")).strip()
        if not slice_name:
            continue
        result = slice_results.get(slice_name)
        if not isinstance(result, dict):
            findings.append(f"La slice `{slice_name}` no tiene verificacion registrada.")
            continue
        if str(result.get("status", "")).strip() != "passed":
            findings.append(f"La slice `{slice_name}` no paso su verificacion mas reciente.")
        report = str(result.get("report", "")).strip()
        if not report:
            findings.append(f"La slice `{slice_name}` no registro un reporte de verificacion.")
            continue
        if not (root / report).exists():
            findings.append(f"La slice `{slice_name}` referencia un reporte inexistente: `{report}`.")
    return findings


def _run_command(command: list[str], cwd: Path) -> tuple[int, str, str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def _run_command_raw(command: list[str], cwd: Path) -> tuple[int, str, str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, result.stdout, result.stderr


def _remote_tracking_refs_for_sha(
    *,
    repo_path: Path,
    repo_sha: str,
    remote_name: str,
    root: Path,
) -> list[str]:
    refs_rc, refs_stdout, _refs_stderr = _run_command(
        ["git", "-C", str(repo_path), "for-each-ref", "--format=%(refname:short)", f"refs/remotes/{remote_name}"],
        cwd=root,
    )
    if refs_rc != 0:
        return []

    refs = [line.strip() for line in refs_stdout.splitlines() if line.strip()]
    matching_refs: list[str] = []
    for ref in refs:
        contains_rc, _, _ = _run_command(
            ["git", "-C", str(repo_path), "merge-base", "--is-ancestor", repo_sha, ref],
            cwd=root,
        )
        if contains_rc == 0:
            matching_refs.append(ref)
    return sorted(matching_refs)


def _remote_tracking_refs_containing_sha(
    *,
    repo_path: Path,
    repo_sha: str,
    remote_name: str,
    root: Path,
) -> tuple[bool, str]:
    refs_rc, refs_stdout, refs_stderr = _run_command(
        ["git", "-C", str(repo_path), "for-each-ref", "--format=%(refname:short)", f"refs/remotes/{remote_name}"],
        cwd=root,
    )
    if refs_rc != 0:
        return False, refs_stderr or "no pude enumerar refs remotas"

    refs = [line.strip() for line in refs_stdout.splitlines() if line.strip()]
    if not refs:
        return False, "sin refs de tracking local para el remote"

    matching_refs = _remote_tracking_refs_for_sha(
        repo_path=repo_path,
        repo_sha=repo_sha,
        remote_name=remote_name,
        root=root,
    )

    if matching_refs:
        return True, ", ".join(sorted(matching_refs))
    return False, "ninguna ref remota contiene el commit"


def _github_repo_slug_from_remote(remote_url: str) -> str:
    url = remote_url.strip()
    if not url:
        return ""
    if url.startswith("git@github.com:"):
        slug = url.removeprefix("git@github.com:")
        return slug.removesuffix(".git").strip("/")
    if url.startswith("ssh://git@github.com/"):
        slug = url.removeprefix("ssh://git@github.com/")
        return slug.removesuffix(".git").strip("/")
    if url.startswith("https://github.com/") or url.startswith("http://github.com/"):
        parsed = urlparse(url)
        slug = parsed.path.strip("/")
        return slug.removesuffix(".git")
    return ""


def _branch_name_from_remote_ref(ref: str) -> str:
    value = str(ref).strip()
    if value.startswith("origin/"):
        return value.removeprefix("origin/")
    return value


def _manifest_repo_source_ref(repo_payload: dict[str, object]) -> str:
    raw_release_ref = repo_payload.get("release_ref", "")
    release_ref = raw_release_ref.strip() if isinstance(raw_release_ref, str) else ""
    if release_ref:
        return release_ref
    candidates = repo_payload.get("remote_ref_candidates", [])
    if not isinstance(candidates, list):
        return ""
    normalized = [_branch_name_from_remote_ref(candidate) for candidate in candidates if str(candidate).strip()]
    unique = sorted({item for item in normalized if item})
    if len(unique) == 1:
        return unique[0]
    return ""


def _release_blocking_verification_profiles(
    manifest: dict[str, object],
    environment: str,
) -> list[dict[str, str]]:
    matches: list[dict[str, str]] = []
    features = manifest.get("features", [])
    if not isinstance(features, list):
        return matches
    for feature in features:
        if not isinstance(feature, dict):
            continue
        slug = str(feature.get("slug", "")).strip() or "<sin-slug>"
        profiles = feature.get("verification_matrix", [])
        if not isinstance(profiles, list):
            continue
        for profile in profiles:
            if not isinstance(profile, dict):
                continue
            blocking_on = {str(item).strip() for item in profile.get("blocking_on", []) if str(item).strip()}
            environments = {str(item).strip() for item in profile.get("environments", []) if str(item).strip()}
            if "release" not in blocking_on:
                continue
            if environments and environment not in environments:
                continue
            matches.append(
                {
                    "slug": slug,
                    "name": str(profile.get("name", "")).strip() or "<sin-nombre>",
                }
            )
    return matches


def _release_promote_preflight_findings(
    *,
    args,
    manifest: dict[str, object],
    workspace_config: dict[str, object],
    provider_config: dict[str, object],
    deploy_env: dict[str, str],
    provider_repos: list[str],
) -> list[str]:
    findings: list[str] = []
    provider_contract = _provider_release_contract(provider_config)
    repos_section = workspace_config.get("repos", {})
    if not isinstance(repos_section, dict):
        repos_section = {}

    target_repos = provider_repos or [
        str(repo).strip()
        for repo in manifest.get("repos", {})
        if str(repo).strip()
    ]
    repo_contracts: list[tuple[str, dict[str, object]]] = []
    for repo in target_repos:
        repo_payload = repos_section.get(repo, {})
        if not isinstance(repo_payload, dict):
            continue
        repo_contracts.append((repo, _repo_deploy_contract(repo_payload, args.environment)))

    if any(contract.get("deploy_requires_pr") for _, contract in repo_contracts):
        if not bool(provider_contract.get("supports_pr_promotion")):
            findings.append("El repo declara `deploy_requires_pr`, pero el provider no soporta `pull_request` promotion.")

    source_ref = str(deploy_env.get("FLOW_DEPLOY_SOURCE_REF", "")).strip()
    if bool(provider_contract.get("requires_source_ref")) and not source_ref:
        manifest_repos = manifest.get("repos", {})
        if not isinstance(manifest_repos, dict):
            manifest_repos = {}
        derived_refs: set[str] = set()
        unresolved: list[str] = []
        for repo in target_repos:
            repo_manifest = manifest_repos.get(repo, {})
            if not isinstance(repo_manifest, dict):
                unresolved.append(repo)
                continue
            derived_ref = _manifest_repo_source_ref(repo_manifest)
            if not derived_ref:
                unresolved.append(repo)
                continue
            derived_refs.add(derived_ref)
        if unresolved:
            findings.append(
                "El provider requiere `source_ref` y SoftOS no pudo derivarlo de forma unica para: "
                + ", ".join(f"`{repo}`" for repo in unresolved)
                + "."
            )
        elif len(derived_refs) != 1:
            findings.append(
                "El provider requiere `source_ref` pero el manifest expone multiples refs candidatas: "
                + ", ".join(f"`{ref}`" for ref in sorted(derived_refs))
                + "."
            )
        else:
            deploy_env["FLOW_DEPLOY_SOURCE_REF"] = next(iter(derived_refs))

    target_ref = str(deploy_env.get("FLOW_DEPLOY_GITHUB_REF", "")).strip()
    if bool(provider_contract.get("requires_target_ref")) and not target_ref:
        findings.append("El provider requiere `target_ref` y no existe `FLOW_DEPLOY_GITHUB_REF` configurado.")

    requires_post_deploy_verify = bool(provider_contract.get("requires_post_deploy_verify"))
    if requires_post_deploy_verify and bool(getattr(args, "skip_verify", False)):
        findings.append("El provider requiere verificacion post-deploy; `--skip-verify` no es valido.")

    verify_mode = str(provider_contract.get("verify_mode", "")).strip().lower()
    if verify_mode == "healthcheck":
        for repo, contract in repo_contracts:
            if not contract.get("deploy_requires_healthcheck"):
                continue
            retry = contract.get("healthcheck_retry", {})
            if not isinstance(retry, dict):
                retry = {}
            attempts = int(retry.get("attempts", 0) or 0)
            if attempts < 1:
                findings.append(
                    f"`{repo}` requiere healthcheck post-deploy pero no declara una estrategia de retry valida."
                )

    if any(contract.get("post_deploy_smoke_required") for _, contract in repo_contracts):
        matching_profiles = _release_blocking_verification_profiles(manifest, args.environment)
        if not matching_profiles:
            findings.append(
                "El repo exige `post_deploy_smoke_required`, pero el release no declara perfiles de verificacion bloqueantes sobre `release` para este entorno."
            )

    return findings


def _is_semver_tag(value: str) -> bool:
    return SEMVER_TAG_PATTERN.match(value.strip()) is not None


def _semver_tuple(value: str) -> tuple[int, int, int]:
    match = SEMVER_TAG_PATTERN.match(value.strip())
    if not match:
        raise ValueError(f"`{value}` no es un tag semver valido (`vX.Y.Z`).")
    return (
        int(match.group("major")),
        int(match.group("minor")),
        int(match.group("patch")),
    )


def _next_semver_version(current: str | None, bump: str) -> str:
    if current is None:
        base = (0, 0, 0)
    else:
        base = _semver_tuple(current)
    major, minor, patch = base
    if bump == "major":
        major += 1
        minor = 0
        patch = 0
    elif bump == "minor":
        minor += 1
        patch = 0
    else:
        patch += 1
    return f"v{major}.{minor}.{patch}"


def _latest_semver_tag(*, run_command, root: Path) -> str | None:
    rc, stdout, stderr = run_command(["git", "-C", str(root), "tag", "--list", "v*"], root)
    if rc != 0:
        raise SystemExit(stderr or "No pude listar tags semver.")
    tags = [line.strip() for line in stdout.splitlines() if _is_semver_tag(line.strip())]
    if not tags:
        return None
    return max(tags, key=_semver_tuple)


def _collect_commit_entries(*, run_command, root: Path, since_tag: str | None) -> list[dict[str, object]]:
    command = ["git", "-C", str(root), "log", "--format=%H%x1f%s%x1f%b%x1e"]
    if since_tag:
        command.append(f"{since_tag}..HEAD")
    rc, stdout, stderr = _run_command_raw(command, root)
    if rc != 0:
        raise SystemExit(stderr or "No pude leer commits para el release.")

    commits: list[dict[str, object]] = []
    for raw_entry in stdout.split("\x1e"):
        entry = raw_entry.rstrip("\r\n")
        if not entry:
            continue
        parts = entry.split("\x1f")
        if len(parts) != 3:
            continue
        sha, subject, body = (part.strip() for part in parts)
        parsed = _parse_conventional_commit(subject, body)
        commits.append(
            {
                "sha": sha,
                "subject": subject,
                "body": body,
                "type": parsed["type"],
                "description": parsed["description"],
                "breaking": parsed["breaking"],
                "conventional": parsed["conventional"],
            }
        )
    return commits


def _parse_conventional_commit(subject: str, body: str) -> dict[str, object]:
    match = CONVENTIONAL_COMMIT_PATTERN.match(subject.strip())
    breaking = "BREAKING CHANGE" in body or "BREAKING-CHANGE" in body
    if not match:
        return {
            "type": "",
            "description": subject.strip(),
            "breaking": breaking,
            "conventional": False,
        }
    commit_type = str(match.group("type") or "").strip()
    return {
        "type": commit_type,
        "description": str(match.group("description") or "").strip(),
        "breaking": breaking or bool(match.group("breaking")),
        "conventional": True,
    }


def _infer_semver_bump(commits: list[dict[str, object]]) -> str:
    if any(bool(commit.get("breaking")) for commit in commits):
        return "major"
    if any(str(commit.get("type", "")).strip() == "feat" for commit in commits):
        return "minor"
    return "patch"


def _render_release_sections(commits: list[dict[str, object]]) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {
        "Added": [],
        "Changed": [],
        "Fixed": [],
        "Docs": [],
        "Tests": [],
    }
    for commit in commits:
        commit_type = str(commit.get("type", "")).strip()
        description = str(commit.get("description", "")).strip() or str(commit.get("subject", "")).strip()
        section = CONVENTIONAL_SECTIONS.get(commit_type, "Changed")
        sections.setdefault(section, []).append(description)
    return {name: items for name, items in sections.items() if items}


def _render_release_notes(*, version: str, release_date: str, sections: dict[str, list[str]]) -> tuple[str, str]:
    changelog_lines = [f"## {version} - {release_date}", ""]
    release_lines = [f"{version}", ""]
    for section_name in ["Added", "Changed", "Fixed", "Docs", "Tests"]:
        items = sections.get(section_name, [])
        if not items:
            continue
        changelog_lines.append(f"### {section_name}")
        changelog_lines.append("")
        release_lines.append(f"### {section_name}")
        release_lines.append("")
        for item in items:
            changelog_lines.append(f"- {item}")
            release_lines.append(f"- {item}")
        changelog_lines.append("")
        release_lines.append("")
    return "\n".join(changelog_lines).rstrip() + "\n", "\n".join(release_lines).rstrip()


def _prepend_changelog_entry(*, changelog_path: Path, entry: str) -> None:
    current = changelog_path.read_text(encoding="utf-8")
    first_release_header = current.find("\n## ")
    if first_release_header == -1:
        updated = current.rstrip() + "\n\n" + entry.strip() + "\n"
    else:
        insertion_point = first_release_header + 1
        updated = current[:insertion_point] + entry.strip() + "\n\n" + current[insertion_point:]
    changelog_path.write_text(updated, encoding="utf-8")


def _require_clean_git_tree(*, run_command, root: Path) -> None:
    rc, stdout, stderr = run_command(["git", "-C", str(root), "status", "--short"], root)
    if rc != 0:
        raise SystemExit(stderr or "No pude inspeccionar el estado de git.")
    if stdout.strip():
        raise SystemExit(
            "El repo tiene cambios sin commit; deja el arbol limpio antes de `flow release publish`."
        )


def _require_tag_absent(*, run_command, root: Path, version: str, check_remote: bool = True) -> None:
    rc, stdout, stderr = run_command(
        ["git", "-C", str(root), "rev-parse", "-q", "--verify", f"refs/tags/{version}"],
        root,
    )
    if rc == 0 and stdout.strip():
        raise SystemExit(f"El tag `{version}` ya existe localmente.")
    if not check_remote:
        return
    remote_rc, remote_stdout, remote_stderr = run_command(
        ["git", "-C", str(root), "ls-remote", "--tags", "origin", f"refs/tags/{version}"],
        root,
    )
    if remote_rc != 0:
        raise SystemExit(remote_stderr or "No pude consultar tags remotos en origin.")
    if remote_stdout.strip():
        raise SystemExit(f"El tag `{version}` ya existe en origin.")


def _verify_release_from_manifest(
    *,
    version: str,
    environment: str,
    manifest: dict[str, object],
    root: Path,
    utc_now: Callable[[], str],
    require_pipelines: bool,
) -> dict[str, object]:
    repos = manifest.get("repos", {})
    features = manifest.get("features", [])
    payload: dict[str, object] = {
        "version": version,
        "environment": environment,
        "verified_at": utc_now(),
        "require_pipelines": require_pipelines,
        "status": "passed",
        "repos": [],
        "features": [],
        "findings": [],
    }
    if not isinstance(repos, dict):
        payload["status"] = "failed"
        payload["findings"] = ["El manifest no contiene `repos` valido para verificar."]
        return payload

    gh_available = shutil.which("gh") is not None
    repo_findings: list[str] = []

    for repo_name in sorted(repos):
        repo_payload = repos.get(repo_name, {})
        repo_item: dict[str, object] = {
            "repo": str(repo_name),
            "status": "passed",
            "pipeline_status": "unavailable",
            "pipeline_required": require_pipelines,
        }
        if not isinstance(repo_payload, dict):
            repo_item["status"] = "failed"
            repo_item["finding"] = "Entrada de repo invalida en manifest."
            repo_findings.append(f"`{repo_name}`: entrada de repo invalida en manifest.")
            payload["repos"].append(repo_item)
            continue

        repo_path_text = str(repo_payload.get("path", "")).strip()
        repo_sha = str(repo_payload.get("sha", "")).strip()
        repo_item["path"] = repo_path_text
        repo_item["sha"] = repo_sha

        if not repo_path_text or not repo_sha:
            repo_item["status"] = "failed"
            repo_item["finding"] = "Falta `path` o `sha` en el manifest."
            repo_findings.append(f"`{repo_name}`: falta `path` o `sha` en el manifest.")
            payload["repos"].append(repo_item)
            continue

        repo_path = Path(repo_path_text)
        if not repo_path.is_absolute():
            repo_path = (root / repo_path).resolve()
        repo_item["path"] = str(repo_path)

        if not repo_path.is_dir():
            repo_item["status"] = "failed"
            repo_item["finding"] = "El path del repo no existe localmente."
            repo_findings.append(f"`{repo_name}`: el path `{repo_path}` no existe localmente.")
            payload["repos"].append(repo_item)
            continue

        remote_rc, remote_stdout, remote_stderr = _run_command(
            ["git", "-C", str(repo_path), "config", "--get", "remote.origin.url"],
            cwd=root,
        )
        remote_url = remote_stdout.strip() if remote_rc == 0 else ""
        if not remote_url:
            repo_item["status"] = "failed"
            repo_item["finding"] = "No pude resolver remote.origin.url."
            details = remote_stderr or "remote.origin.url vacio"
            repo_findings.append(f"`{repo_name}`: no pude resolver remote.origin.url ({details}).")
            payload["repos"].append(repo_item)
            continue
        repo_item["remote"] = remote_url

        remote_sha_present, remote_sha_details = _remote_tracking_refs_containing_sha(
            repo_path=repo_path,
            repo_sha=repo_sha,
            remote_name="origin",
            root=root,
        )
        repo_item["remote_sha_present"] = remote_sha_present
        repo_item["remote_refs"] = remote_sha_details if remote_sha_present else None
        if not repo_item["remote_sha_present"]:
            repo_item["status"] = "failed"
            repo_item["finding"] = "El commit del manifest no existe en origin."
            details = remote_sha_details
            repo_findings.append(
                f"`{repo_name}`: `{repo_sha}` no existe en origin ({details})."
            )
            payload["repos"].append(repo_item)
            continue

        github_slug = _github_repo_slug_from_remote(remote_url)
        repo_item["github_repo"] = github_slug or None

        if not github_slug:
            repo_item["pipeline_status"] = "unavailable"
            if require_pipelines:
                repo_item["status"] = "failed"
                repo_item["finding"] = "No pude inferir repo GitHub para verificar pipelines."
                repo_findings.append(
                    f"`{repo_name}`: remote `{remote_url}` no es GitHub; no puedo verificar pipelines."
                )
            payload["repos"].append(repo_item)
            continue

        if not gh_available:
            repo_item["pipeline_status"] = "unavailable"
            if require_pipelines:
                repo_item["status"] = "failed"
                repo_item["finding"] = "No encontre `gh` en PATH para verificar pipelines."
                repo_findings.append(
                    f"`{repo_name}`: falta `gh` para verificar pipelines de `{github_slug}`."
                )
            payload["repos"].append(repo_item)
            continue

        checks_rc, checks_stdout, checks_stderr = _run_command(
            ["gh", "api", f"repos/{github_slug}/commits/{repo_sha}/check-runs?per_page=100"],
            cwd=root,
        )
        if checks_rc != 0:
            repo_item["pipeline_status"] = "failed"
            repo_item["status"] = "failed"
            details = checks_stderr or checks_stdout or "gh api fallo"
            repo_item["finding"] = "No pude consultar check-runs del commit."
            repo_findings.append(
                f"`{repo_name}`: no pude consultar check-runs de `{github_slug}@{repo_sha}` ({details})."
            )
            payload["repos"].append(repo_item)
            continue

        try:
            checks_payload = json.loads(checks_stdout or "{}")
        except json.JSONDecodeError:
            repo_item["pipeline_status"] = "failed"
            repo_item["status"] = "failed"
            repo_item["finding"] = "La respuesta de check-runs no es JSON valido."
            repo_findings.append(
                f"`{repo_name}`: respuesta invalida al consultar check-runs de `{github_slug}`."
            )
            payload["repos"].append(repo_item)
            continue

        check_runs = checks_payload.get("check_runs", [])
        if not isinstance(check_runs, list):
            check_runs = []
        total_runs = len(check_runs)
        repo_item["check_runs_total"] = total_runs
        if total_runs == 0:
            repo_item["pipeline_status"] = "missing"
            if require_pipelines:
                repo_item["status"] = "failed"
                repo_item["finding"] = "No hay check-runs para el commit."
                repo_findings.append(
                    f"`{repo_name}`: no hay check-runs en `{github_slug}` para `{repo_sha}`."
                )
            payload["repos"].append(repo_item)
            continue

        non_completed = 0
        non_passing = 0
        for check in check_runs:
            if not isinstance(check, dict):
                continue
            status = str(check.get("status", "")).strip()
            conclusion = str(check.get("conclusion", "")).strip()
            if status != "completed":
                non_completed += 1
            elif conclusion not in {"success", "neutral", "skipped"}:
                non_passing += 1
        repo_item["check_runs_non_completed"] = non_completed
        repo_item["check_runs_non_passing"] = non_passing

        if non_completed > 0 or non_passing > 0:
            repo_item["pipeline_status"] = "failed"
            repo_item["status"] = "failed"
            repo_item["finding"] = (
                f"Check-runs no satisfactorios (non_completed={non_completed}, non_passing={non_passing})."
            )
            repo_findings.append(
                f"`{repo_name}`: check-runs no satisfactorios "
                f"(non_completed={non_completed}, non_passing={non_passing})."
            )
        else:
            repo_item["pipeline_status"] = "passed"

        payload["repos"].append(repo_item)

    feature_findings: list[str] = []
    if isinstance(features, list):
        for feature in features:
            if not isinstance(feature, dict):
                continue
            slug = str(feature.get("slug", "")).strip() or "<sin-slug>"
            profiles = feature.get("verification_matrix", [])
            if not isinstance(profiles, list):
                profiles = []
            feature_item: dict[str, object] = {
                "slug": slug,
                "status": "passed",
                "verification_profiles": [],
            }
            applicable_count = 0
            for profile in profiles:
                if not isinstance(profile, dict):
                    continue
                blocking_on = [
                    str(item).strip()
                    for item in profile.get("blocking_on", [])
                    if str(item).strip()
                ]
                environments = [
                    str(item).strip()
                    for item in profile.get("environments", [])
                    if str(item).strip()
                ]
                profile_name = str(profile.get("name", "")).strip() or "<sin-nombre>"
                profile_item: dict[str, object] = {
                    "name": profile_name,
                    "level": str(profile.get("level", "")).strip(),
                    "status": "skipped",
                }
                if "release" not in blocking_on:
                    profile_item["reason"] = "not-blocking-on-release"
                    feature_item["verification_profiles"].append(profile_item)
                    continue
                if environments and environment not in environments:
                    profile_item["reason"] = "environment-not-applicable"
                    feature_item["verification_profiles"].append(profile_item)
                    continue

                applicable_count += 1
                command = str(profile.get("command", "")).strip()
                if not command:
                    profile_item["status"] = "failed"
                    profile_item["reason"] = "missing-command"
                    feature_item["verification_profiles"].append(profile_item)
                    feature_item["status"] = "failed"
                    feature_findings.append(
                        f"`{slug}`: el perfil de verificacion `{profile_name}` no declara `command`."
                    )
                    continue

                execution = subprocess.run(
                    shlex.split(command),
                    cwd=root,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                combined = (execution.stdout + "\n" + execution.stderr).strip()
                profile_item["command"] = command
                profile_item["output_tail"] = "\n".join(combined.splitlines()[-40:]) if combined else ""
                if execution.returncode == 0:
                    profile_item["status"] = "passed"
                else:
                    profile_item["status"] = "failed"
                    profile_item["returncode"] = execution.returncode
                    feature_item["status"] = "failed"
                    feature_findings.append(
                        f"`{slug}`: el perfil de verificacion `{profile_name}` fallo durante `release verify`."
                    )
                feature_item["verification_profiles"].append(profile_item)

            if applicable_count == 0:
                feature_item["status"] = "skipped"
            payload["features"].append(feature_item)

    payload["findings"] = repo_findings + feature_findings
    payload["status"] = "failed" if payload["findings"] else "passed"
    return payload


def command_release_cut(
    args,
    *,
    require_dirs: Callable[[], None],
    release_default_version: Callable[[], str],
    release_manifest_path: Callable[[str], Path],
    resolve_spec,
    releasable_feature_specs: Callable[[], list[Path]],
    ensure_spec_ready_for_approval,
    rel: Callable[[Path], str],
    spec_slug: Callable[[Path], str],
    read_state,
    root: Path,
    root_repo: str,
    workspace_config: dict[str, object],
    plan_root: Path,
    git_changed_files: Callable[[Path], tuple[list[str], str | None]],
    repo_head_sha: Callable[[str], str],
    repo_root,
    release_manifest_root: Path,
    utc_now: Callable[[], str],
    write_json,
    write_state,
    json_dumps: Callable[[object], str],
) -> int:
    require_dirs()
    version = args.version or release_default_version()
    manifest_path = release_manifest_path(version)
    if manifest_path.exists() and not args.force:
        raise SystemExit(f"Ya existe un manifest para `{version}`. Usa `--force` para regenerarlo.")

    if args.spec:
        spec_paths = [resolve_spec(identifier) for identifier in args.spec]
    elif args.all_approved:
        spec_paths = releasable_feature_specs()
    else:
        raise SystemExit("Debes indicar `--spec` o `--all-approved` para cortar un release.")

    if not spec_paths:
        raise SystemExit("No encontre specs aprobadas para incluir en el release.")

    features: list[dict[str, object]] = []
    repos_involved = {root_repo}

    for spec_path in spec_paths:
        analysis = ensure_spec_ready_for_approval(spec_path)
        if not frontmatter_status_allows_execution(analysis["frontmatter"].get("status")):
            raise SystemExit(f"La spec `{rel(spec_path)}` debe estar en `approved` para entrar en un release.")
        repos = sorted(analysis["target_index"])
        repos_involved.update(repos)
        slug = spec_slug(spec_path)
        state = read_state(slug)
        slice_findings = _release_slice_findings(
            slug,
            state,
            plan_root=plan_root,
            root=root,
            rel=rel,
        )
        if slice_findings:
            joined = "\n".join(f"- {finding}" for finding in slice_findings)
            raise SystemExit(f"La feature `{slug}` no esta lista para release:\n{joined}")
        features.append(
            {
                "slug": slug,
                "spec_path": rel(spec_path),
                "state_status": state.get("status", "unknown"),
                "repos": repos,
                "targets": analysis["targets"],
                "test_refs": analysis["test_refs"],
                "verification_matrix": analysis["verification_matrix"],
            }
        )

    dirty_repo_findings: list[str] = []
    for repo in sorted(repos_involved):
        changed_files, git_error = git_changed_files(repo_root(repo))
        if git_error:
            dirty_repo_findings.append(f"No pude inspeccionar cambios locales de `{repo}`: {git_error}")
            continue
        if not changed_files:
            continue
        preview = ", ".join(f"`{path}`" for path in changed_files[:5])
        suffix = " ..." if len(changed_files) > 5 else ""
        dirty_repo_findings.append(f"`{repo}` tiene cambios sin commit: {preview}{suffix}")
    if dirty_repo_findings:
        joined = "\n".join(f"- {finding}" for finding in dirty_repo_findings)
        raise SystemExit(f"No puedo cortar un release con cambios locales sin commit:\n{joined}")

    repos_section = workspace_config.get("repos", {})
    if not isinstance(repos_section, dict):
        repos_section = {}

    manifest_repos: dict[str, dict[str, object]] = {}
    for repo in sorted(repos_involved):
        repo_path = repo_root(repo)
        repo_sha = repo_head_sha(repo)
        remote_ref_candidates = _remote_tracking_refs_for_sha(
            repo_path=repo_path,
            repo_sha=repo_sha,
            remote_name="origin",
            root=root,
        )
        release_ref = ""
        normalized_refs = sorted({_branch_name_from_remote_ref(ref) for ref in remote_ref_candidates if str(ref).strip()})
        if len(normalized_refs) == 1:
            release_ref = normalized_refs[0]
        repo_workspace_payload = repos_section.get(repo, {})
        promotion_strategy = {"mode": "direct"}
        if isinstance(repo_workspace_payload, dict):
            promotion_strategy = {
                "mode": _promotion_strategy_mode(repo_workspace_payload, "production"),
            }
        manifest_repos[repo] = {
            "path": str(repo_path),
            "sha": repo_sha,
            "remote_ref_candidates": remote_ref_candidates,
            "release_ref": release_ref or None,
            "promotion_strategy": promotion_strategy,
        }

    manifest = {
        "version": version,
        "generated_at": utc_now(),
        "root_sha": repo_head_sha(root_repo),
        "repos": manifest_repos,
        "features": features,
        "promotions": [],
    }
    write_json(manifest_path, manifest)

    summary_path = release_manifest_root / f"{version}.md"
    lines = [
        f"# Release Manifest {version}",
        "",
        f"- Root SHA: `{manifest['root_sha']}`",
        "",
        "## Repos",
        "",
    ]
    for repo, payload in manifest["repos"].items():
        lines.append(f"- `{repo}`: `{payload['sha']}`")
    lines.extend(["", "## Features", ""])
    for feature in features:
        lines.append(
            f"- `{feature['slug']}`: `{feature['state_status']}` "
            f"({', '.join(feature['repos'])})"
        )
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    for feature in features:
        state = read_state(feature["slug"])
        if state:
            state["release_candidate"] = version
            if "created_at" not in state:
                state["created_at"] = utc_now()
            write_state(feature["slug"], state)

    payload = {
        "version": version,
        "manifest": rel(manifest_path),
        "summary": rel(summary_path),
        "features": [feature["slug"] for feature in features],
        "repos": sorted(repos_involved),
    }
    if bool(getattr(args, "json", False)):
        print(json_dumps(payload))
        return 0
    print(rel(manifest_path))
    print(rel(summary_path))
    return 0


def command_release_manifest(
    args,
    *,
    load_release_manifest,
    release_manifest_path: Callable[[str], Path],
    rel: Callable[[Path], str],
    json_dumps: Callable[[object], str],
) -> int:
    manifest = load_release_manifest(args.version)
    if bool(getattr(args, "json", False)):
        print(json_dumps(manifest))
        return 0
    print(rel(release_manifest_path(args.version)))
    return 0


def command_release_status(
    args,
    *,
    load_release_manifest,
    json_dumps: Callable[[object], str],
) -> int:
    manifest = load_release_manifest(args.version)
    payload = {
        "version": manifest.get("version"),
        "root_sha": manifest.get("root_sha"),
        "features": manifest.get("features", []),
        "promotions": manifest.get("promotions", []),
        "verifications": manifest.get("verifications", []),
    }
    if bool(getattr(args, "json", False)):
        print(json_dumps(payload))
        return 0
    print(f"- version: {manifest.get('version')}")
    print(f"- root_sha: {manifest.get('root_sha')}")
    print(f"- features: {len(manifest.get('features', []))}")
    promotions = manifest.get("promotions", [])
    if promotions:
        for promotion in promotions:
            print(
                f"- promotion {promotion.get('environment')}: "
                f"{promotion.get('status')} at {promotion.get('promoted_at')}"
            )
    else:
        print("- promotions: none")
    verifications = manifest.get("verifications", [])
    if isinstance(verifications, list) and verifications:
        for verification in verifications:
            if not isinstance(verification, dict):
                continue
            print(
                f"- verification {verification.get('environment')}: "
                f"{verification.get('status')} at {verification.get('verified_at')}"
            )
    else:
        print("- verifications: none")
    return 0


def command_release_verify(
    args,
    *,
    load_release_manifest,
    release_manifest_path: Callable[[str], Path],
    release_verification_path: Callable[[str, str], Path],
    root: Path,
    rel: Callable[[Path], str],
    utc_now: Callable[[], str],
    write_json,
    json_dumps: Callable[[object], str],
) -> int:
    manifest = load_release_manifest(args.version)
    verification_payload = _verify_release_from_manifest(
        version=args.version,
        environment=args.environment,
        manifest=manifest,
        root=root,
        utc_now=utc_now,
        require_pipelines=bool(getattr(args, "require_pipelines", False)),
    )
    verif_path = release_verification_path(args.version, args.environment)
    write_json(verif_path, verification_payload)

    verifications = manifest.setdefault("verifications", [])
    if isinstance(verifications, list):
        verifications.append(verification_payload)
    write_json(release_manifest_path(args.version), manifest)

    if bool(getattr(args, "json", False)):
        payload = dict(verification_payload)
        payload["path"] = rel(verif_path)
        print(json_dumps(payload))
    else:
        print(rel(verif_path))
        print(f"status={verification_payload.get('status')}")

    return 1 if str(verification_payload.get("status", "")) != "passed" else 0


def command_release_promote(
    args,
    *,
    load_release_manifest,
    workspace_config: dict[str, object],
    root_repo: str,
    load_providers_config,
    select_provider,
    provider_entrypoint_path,
    run_provider,
    release_manifest_path: Callable[[str], Path],
    release_promotion_path: Callable[[str, str], Path],
    release_verification_path: Callable[[str, str], Path],
    root: Path,
    rel: Callable[[Path], str],
    utc_now: Callable[[], str],
    write_json,
    read_state,
    write_state,
    replace_frontmatter_status: Callable[[Path, str], None],
    auto_worktree_cleanup: Callable[[], dict[str, object]] | None,
    json_dumps: Callable[[object], str],
) -> int:
    manifest = load_release_manifest(args.version)
    if args.environment in {"staging", "production"} and not args.approver:
        raise SystemExit("`--approver` es obligatorio para staging y production.")

    providers_payload = load_providers_config()
    inferred_provider, deploy_env, provider_repos = _resolve_release_provider_from_workspace(
        args=args,
        manifest=manifest,
        workspace_config=workspace_config,
        root_repo=root_repo,
    )
    explicit_provider = str(getattr(args, "provider", "") or "").strip() or inferred_provider or None
    provider_name, provider_config_payload = select_provider(providers_payload, "release", explicit=explicit_provider)
    preflight_findings = _release_promote_preflight_findings(
        args=args,
        manifest=manifest,
        workspace_config=workspace_config,
        provider_config=provider_config_payload,
        deploy_env=deploy_env,
        provider_repos=provider_repos,
    )
    if preflight_findings:
        joined = "\n".join(f"- {finding}" for finding in preflight_findings)
        raise SystemExit(f"La promocion `{args.environment}` no paso preflight:\n{joined}")
    promotion_payload = {
        "version": args.version,
        "environment": args.environment,
        "promoted_at": utc_now(),
        "approver": args.approver,
        "status": "recorded",
        "provider": provider_name,
        "entrypoint": rel(provider_entrypoint_path(provider_config_payload)),
    }
    if inferred_provider:
        promotion_payload["provider_resolution"] = {
            "mode": "workspace-deploy",
            "repos": provider_repos,
        }

    execution = run_provider(
        "release",
        "promote",
        provider_name,
        provider_config_payload,
        {
            **_provider_auth_env(),
            "FLOW_RELEASE_VERSION": args.version,
            "FLOW_RELEASE_ENV": args.environment,
            "FLOW_RELEASE_MANIFEST": str(release_manifest_path(args.version).resolve()),
            "FLOW_RELEASE_APPROVER": args.approver or "",
            **deploy_env,
        },
    )
    promotion_payload["output_tail"] = execution["output_tail"]
    if int(execution["returncode"]) != 0:
        promotion_payload["status"] = "failed"
        write_json(release_promotion_path(args.version, args.environment), promotion_payload)
        raise SystemExit(
            f"La promocion `{args.environment}` fallo con `{execution['provider']}` ({execution['entrypoint']})."
        )

    promotion_payload["status"] = "executed"

    promotions = manifest.setdefault("promotions", [])
    if isinstance(promotions, list):
        promotions.append(promotion_payload)
    verification_payload: dict[str, object] | None = None
    verification_path_text = ""
    should_verify = not bool(getattr(args, "skip_verify", False))
    if should_verify:
        verification_payload = _verify_release_from_manifest(
            version=args.version,
            environment=args.environment,
            manifest=manifest,
            root=root,
            utc_now=utc_now,
            require_pipelines=bool(getattr(args, "require_pipelines", False)),
        )
        verification_path = release_verification_path(args.version, args.environment)
        write_json(verification_path, verification_payload)
        verification_path_text = rel(verification_path)
        verifications = manifest.setdefault("verifications", [])
        if isinstance(verifications, list):
            verifications.append(verification_payload)
        promotion_payload["verification"] = {
            "status": verification_payload.get("status"),
            "path": verification_path_text,
        }
    else:
        promotion_payload["verification"] = {"status": "skipped"}

    write_json(release_manifest_path(args.version), manifest)
    write_json(release_promotion_path(args.version, args.environment), promotion_payload)

    verification_passed = (
        verification_payload is not None
        and str(verification_payload.get("status", "")).strip() == "passed"
    )
    if args.environment == "production" and verification_passed:
        for feature in manifest.get("features", []):
            slug = str(feature.get("slug", ""))
            if not slug:
                continue
            state = read_state(slug)
            if not state:
                continue
            state["status"] = "released"
            state["released_in"] = args.version
            write_state(slug, state)
            spec_path_text = str(feature.get("spec_path", "")).strip() or str(state.get("spec_path", "")).strip()
            if spec_path_text:
                spec_path = Path(spec_path_text)
                if not spec_path.is_absolute():
                    spec_path = (root / spec_path).resolve()
                if spec_path.exists():
                    replace_frontmatter_status(spec_path, "released")

    if should_verify and not verification_passed:
        raise SystemExit(
            "La promocion se ejecuto, pero la verificacion post-release fallo. "
            f"Revisa `{verification_path_text}`."
        )
    if args.environment == "production" and not should_verify:
        print(
            "La promocion a production se ejecuto sin verificacion (`--skip-verify`), "
            "por lo que la feature no se marco como `released`."
        )

    if not bool(getattr(args, "no_worktree_cleanup", False)) and auto_worktree_cleanup is not None:
        promotion_payload["worktree_cleanup"] = auto_worktree_cleanup()

    promotion_path = rel(release_promotion_path(args.version, args.environment))
    if bool(getattr(args, "json", False)):
        promotion_payload["path"] = promotion_path
        print(json_dumps(promotion_payload))
        return 0
    print(promotion_path)
    return 0


def command_release_publish(
    args,
    *,
    root: Path,
    changelog_path: Path,
    auto_worktree_cleanup: Callable[[], dict[str, object]] | None,
    utc_now: Callable[[], str],
    json_dumps: Callable[[object], str],
    run_command: Callable[[list[str], Path], tuple[int, str, str]] = _run_command,
) -> int:
    _require_clean_git_tree(run_command=run_command, root=root)

    if args.version:
        version = str(args.version).strip()
        if not _is_semver_tag(version):
            raise SystemExit("`--version` debe usar semver con prefijo `v` (por ejemplo `v0.1.3`).")
        since_tag = str(getattr(args, "since_tag", "") or "").strip() or _latest_semver_tag(
            run_command=run_command,
            root=root,
        )
        selected_bump = str(args.bump).strip()
    else:
        since_tag = str(getattr(args, "since_tag", "") or "").strip() or _latest_semver_tag(
            run_command=run_command,
            root=root,
        )
        commits_for_bump = _collect_commit_entries(run_command=run_command, root=root, since_tag=since_tag)
        if not commits_for_bump:
            raise SystemExit("No encontre commits nuevos para publicar desde el ultimo tag semver.")
        selected_bump = _infer_semver_bump(commits_for_bump) if args.bump == "auto" else str(args.bump).strip()
        version = _next_semver_version(since_tag, selected_bump)

    _require_tag_absent(
        run_command=run_command,
        root=root,
        version=version,
        check_remote=not bool(args.dry_run),
    )

    commits = _collect_commit_entries(run_command=run_command, root=root, since_tag=since_tag)
    if not commits:
        raise SystemExit("No encontre commits nuevos para publicar.")

    release_date = utc_now().split("T", 1)[0]
    sections = _render_release_sections(commits)
    changelog_entry, release_notes = _render_release_notes(
        version=version,
        release_date=release_date,
        sections=sections,
    )
    payload = {
        "version": version,
        "since_tag": since_tag,
        "bump": selected_bump,
        "commit_count": len(commits),
        "changelog": str(changelog_path),
        "release_notes": release_notes,
        "github_release": not bool(args.skip_github),
        "dry_run": bool(args.dry_run),
    }

    if bool(args.dry_run):
        if bool(getattr(args, "json", False)):
            print(json_dumps(payload))
            return 0
        print(release_notes)
        return 0

    if not changelog_path.exists():
        raise SystemExit(f"No existe changelog versionado en `{changelog_path}`.")

    changelog_contents = changelog_path.read_text(encoding="utf-8")
    if f"## {version} - " in changelog_contents:
        raise SystemExit(f"El changelog ya contiene una entrada para `{version}`.")

    _prepend_changelog_entry(changelog_path=changelog_path, entry=changelog_entry)

    add_rc, _, add_stderr = run_command(["git", "-C", str(root), "add", str(changelog_path)], root)
    if add_rc != 0:
        raise SystemExit(add_stderr or "No pude hacer `git add` del changelog.")

    commit_message = f"docs(changelog): add {version} release notes"
    commit_rc, commit_stdout, commit_stderr = run_command(
        ["git", "-C", str(root), "commit", "-m", commit_message],
        root,
    )
    if commit_rc != 0:
        raise SystemExit(commit_stderr or commit_stdout or "No pude crear el commit del changelog.")

    tag_rc, _, tag_stderr = run_command(
        ["git", "-C", str(root), "tag", "-a", version, "-m", version],
        root,
    )
    if tag_rc != 0:
        raise SystemExit(tag_stderr or f"No pude crear el tag `{version}`.")

    push_main_rc, _, push_main_stderr = run_command(["git", "-C", str(root), "push", "origin", "main"], root)
    if push_main_rc != 0:
        raise SystemExit(push_main_stderr or "No pude empujar `main` a origin.")

    push_tag_rc, _, push_tag_stderr = run_command(["git", "-C", str(root), "push", "origin", version], root)
    if push_tag_rc != 0:
        raise SystemExit(push_tag_stderr or f"No pude empujar el tag `{version}` a origin.")

    release_url = ""
    if not bool(args.skip_github):
        if shutil.which("gh") is None:
            raise SystemExit(
                "No encontre `gh`; usa `--skip-github` o ejecuta el comando donde `gh` este disponible."
            )
        gh_rc, gh_stdout, gh_stderr = run_command(
            ["gh", "release", "create", version, "--title", version, "--notes", release_notes],
            root,
        )
        if gh_rc != 0:
            raise SystemExit(gh_stderr or gh_stdout or f"No pude crear el GitHub Release `{version}`.")
        release_url = (gh_stdout or "").strip()

    payload["commit_message"] = commit_message
    payload["release_url"] = release_url or None
    if not bool(getattr(args, "no_worktree_cleanup", False)) and auto_worktree_cleanup is not None:
        payload["worktree_cleanup"] = auto_worktree_cleanup()
    if bool(getattr(args, "json", False)):
        print(json_dumps(payload))
        return 0
    print(version)
    if release_url:
        print(release_url)
    return 0
