from __future__ import annotations

from pathlib import Path

from flowctl.ci import _reproducible_install_findings


def test_reproducible_install_findings_flags_manifest_lock_drift(tmp_path: Path) -> None:
    repo_path = tmp_path / "frontend-app"
    repo_path.mkdir()
    (repo_path / "package.json").write_text('{"name":"frontend-app"}\n', encoding="utf-8")
    (repo_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")

    findings = _reproducible_install_findings(
        repo_name="frontend-app",
        repo_path=repo_path,
        repo_payload={
            "test_runner": "pnpm",
            "ci": {
                "install_contract": {
                    "mode": "strict",
                    "manifest_files": ["package.json"],
                    "lock_files": ["pnpm-lock.yaml"],
                }
            },
        },
        changed_files=["package.json"],
        commands=[("Install", ["pnpm", "install", "--frozen-lockfile"])],
    )

    assert any("sin actualizar lockfile" in finding for finding in findings)


def test_reproducible_install_findings_flags_non_strict_install_command(tmp_path: Path) -> None:
    repo_path = tmp_path / "frontend-app"
    repo_path.mkdir()
    (repo_path / "package.json").write_text('{"name":"frontend-app"}\n', encoding="utf-8")
    (repo_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")

    findings = _reproducible_install_findings(
        repo_name="frontend-app",
        repo_path=repo_path,
        repo_payload={
            "test_runner": "pnpm",
            "ci": {
                "install_contract": {
                    "mode": "strict",
                    "manifest_files": ["package.json"],
                    "lock_files": ["pnpm-lock.yaml"],
                }
            },
        },
        changed_files=[],
        commands=[("Install", ["pnpm", "install"])],
    )

    assert any("no es estricto" in finding for finding in findings)
