from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Callable


SECRET_SCAN_BINARY_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".pdf",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".zip",
    ".gz",
    ".tar",
    ".tgz",
    ".jar",
    ".pyc",
}
SECRET_SCAN_ALLOWED_ENV_NAMES = {
    ".env.example",
    ".env.sample",
    ".env.template",
    ".env.generated",
}
SECRET_SCAN_FILENAME_RE = re.compile(r"(^|/)\.env(\.[^/]+)?$", flags=re.IGNORECASE)
SECRET_SCAN_CONTENT_PATTERNS = [
    ("private-key", re.compile(r"-----BEGIN (?:[A-Z ]+)?PRIVATE KEY-----")),
    ("github-token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b")),
    ("openai-key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    (
        "generic-secret",
        re.compile(
            r"(?i)\b(api[_-]?key|secret|token|password|passwd|private[_-]?key)\b\s*[:=]\s*['\"]?([^\s'\"`]{8,})"
        ),
    ),
]


def is_advisory_secret_finding(finding: str) -> bool:
    return str(finding).strip().lower().startswith("advisory:")


def secret_value_looks_placeholder(value: str) -> bool:
    normalized = value.strip().strip("'\"")
    lower = normalized.lower()
    if not normalized:
        return True
    if normalized.startswith("<") or normalized.startswith("&lt;"):
        # Looks like HTML/JSX markup, not a literal secret value.
        return True
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)+", normalized):
        # Looks like a Python/JS attribute chain (e.g. settings.github_webhook_secret).
        return True
    if re.search(r"[()\[\]{}]", normalized):
        # Looks like code invocation/indexing, not a literal secret.
        return True
    if any(token in normalized for token in ("${", "env:", "settings.", "request.", "payload.", "self.", "args.", "kwargs.")):
        return True
    if lower in {"none", "null", "true", "false"}:
        return True
    if normalized.startswith("${") or normalized.startswith("op://") or normalized.startswith("sops://"):
        return True
    placeholders = ("example", "sample", "changeme", "replace", "dummy", "placeholder", "fake", "test")
    if any(token in lower for token in placeholders):
        return True
    extra = os.environ.get("FLOW_SECRET_SCAN_EXTRA_PLACEHOLDER_SUBSTRINGS", "")
    for token in extra.split(","):
        t = token.strip().lower()
        if t and t in lower:
            return True
    return False


def _line_for_offset(text: str, offset: int) -> str:
    start = text.rfind("\n", 0, offset)
    if start == -1:
        start = 0
    else:
        start += 1
    end = text.find("\n", offset)
    if end == -1:
        end = len(text)
    return text[start:end]


def _looks_ui_placeholder_context(text: str, offset: int) -> bool:
    line = _line_for_offset(text, offset).lower()
    marker_tokens = ("placeholder", "helpertext", "helper_text", "description", "label", "hint", "example")
    return any(token in line for token in marker_tokens)


def candidate_secret_file_findings(relative_path: str) -> list[str]:
    path = Path(relative_path)
    name = path.name.lower()
    findings: list[str] = []
    if SECRET_SCAN_FILENAME_RE.search(relative_path.replace("\\", "/")) and name not in SECRET_SCAN_ALLOWED_ENV_NAMES:
        findings.append("advisory: archivo `.env*` trackeado; valida que no contenga secretos reales")
    if path.suffix.lower() in {".pem", ".p12", ".pfx", ".key"}:
        findings.append(f"archivo sensible `{path.suffix.lower()}` detectado")
    return findings


def content_secret_findings(text: str) -> list[str]:
    findings: list[str] = []
    for label, pattern in SECRET_SCAN_CONTENT_PATTERNS:
        for match in pattern.finditer(text):
            if label == "generic-secret":
                if _looks_ui_placeholder_context(text, match.start()):
                    continue
                secret_value = match.group(2) if match.lastindex and match.lastindex >= 2 else match.group(0)
                if secret_value_looks_placeholder(secret_value):
                    continue
            findings.append(f"patron `{label}` detectado")
            break
    return findings


def scan_secret_paths(
    repo: str,
    repo_path: Path,
    relative_paths: list[str],
    *,
    read_text: Callable[[Path], str],
) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for relative_path in sorted(dict.fromkeys(relative_paths)):
        absolute_path = repo_path / relative_path
        file_findings = candidate_secret_file_findings(relative_path)
        if absolute_path.is_file() and absolute_path.suffix.lower() not in SECRET_SCAN_BINARY_SUFFIXES:
            file_findings.extend(content_secret_findings(read_text(absolute_path)))
        if file_findings:
            findings.append(
                {
                    "repo": repo,
                    "path": relative_path,
                    "findings": sorted(dict.fromkeys(file_findings)),
                }
            )
    return findings
