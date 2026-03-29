from __future__ import annotations

import json
import re
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

    matching_refs: list[str] = []
    for ref in refs:
        contains_rc, _, _ = _run_command(
            ["git", "-C", str(repo_path), "merge-base", "--is-ancestor", repo_sha, ref],
            cwd=root,
        )
        if contains_rc == 0:
            matching_refs.append(ref)

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
    payload: dict[str, object] = {
        "version": version,
        "environment": environment,
        "verified_at": utc_now(),
        "require_pipelines": require_pipelines,
        "status": "passed",
        "repos": [],
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

    payload["findings"] = repo_findings
    payload["status"] = "failed" if repo_findings else "passed"
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

    manifest = {
        "version": version,
        "generated_at": utc_now(),
        "root_sha": repo_head_sha(root_repo),
        "repos": {
            repo: {
                "path": str(repo_root(repo)),
                "sha": repo_head_sha(repo),
            }
            for repo in sorted(repos_involved)
        },
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
    if bool(getattr(args, "json", False)):
        print(json_dumps(payload))
        return 0
    print(version)
    if release_url:
        print(release_url)
    return 0
