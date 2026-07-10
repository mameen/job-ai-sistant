#!/usr/bin/env python3
"""Project Career Zazu — Hermes admin (bootstrap, profiles, status).

Usage:
    python agentic/hermes/admin/manage.py bootstrap [--extract-kb] [--skip-setup]
    python agentic/hermes/admin/manage.py install-deps [--kb-extract]
    python agentic/hermes/admin/manage.py setup [--dry-run]
    python agentic/hermes/admin/manage.py status
    python agentic/hermes/admin/manage.py nuke --yes
    python agentic/hermes/admin/manage.py kb-scan [--agent] [--force-extract]
    python agentic/hermes/admin/manage.py kb-extract [--force-organize] [--skip-rag]
    python agentic/hermes/admin/manage.py search -q "Software Engineering Manager" [--jobspy-sites linkedin,indeed,google]
    python agentic/hermes/admin/manage.py apply --from-search
    python agentic/hermes/admin/manage.py applications import-vault
    python agentic/hermes/admin/manage.py applications list
    python agentic/hermes/admin/manage.py secrets unlock|list|set|delete
    python agentic/hermes/admin/manage.py email poll --vault-key gmail_oauth
    python agentic/hermes/admin/manage.py hermes [--] <hermes-cli-args...>
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[3]
HERMES_PKG = Path(__file__).resolve().parents[1]
DOTENV_PATH = REPO / ".env"
CONFIG_DIR = Path(__file__).resolve().parent / "config"
ROLES_PATH = CONFIG_DIR / "hermes_roles.yaml"
ROLES_LOCAL_PATH = CONFIG_DIR / "hermes_roles.local.yaml"
MANIFEST_PATH = CONFIG_DIR / "manifest.yaml"
SOULS_DIR = CONFIG_DIR / "souls"
REPO_ONBOARDING_SRC = REPO / ".agents" / "onboarding" / "hermes-and-repo.md"
RUNTIME = HERMES_PKG / ".runtime"
GENERATED = HERMES_PKG / ".generated"
GENERATED_RESEARCHED = GENERATED / "researched"
GENERATED_RECOMMENDED = GENERATED / "recommended"
GENERATED_PROPOSALS = GENERATED / "proposals"
GENERATED_INTAKE = GENERATED / "intake"
DEFAULT_SEARCH_POSTED_DAYS = 10
HERMES_HOME = Path.home() / ".hermes"
VENV = REPO / ".venv"
REQUIREMENTS = REPO / "requirements.txt"
REQUIREMENTS_KB_EXTRACT = REPO / "requirements-kb-extract.txt"
REQUIREMENTS_EMAIL = REPO / "requirements-email.txt"
KB_ROOT = HERMES_PKG / ".kb"
KB_PUBLIC = KB_ROOT / "public"
KB_PRIVATE = KB_ROOT / "private"
KB_INBOX = KB_ROOT / "inbox"
KB_INDEX = KB_ROOT / "_index"
KB_INDEX_DB = KB_ROOT / "index_db"
KB_SCAFFOLD = HERMES_PKG / "kb" / "scaffold"
KB_MARKER = ".kb_initialized"
LEGACY_KB_DIRS = {
    ".kb_public": "public",
    ".kb_private": "private",
}
LEGACY_KB_ROOT = REPO / ".kb"


def _load_dotenv(path: Path = DOTENV_PATH) -> None:
    """Load repo-root .env into os.environ (does not override existing env)."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = value.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1].strip()
        if not value:
            continue
        os.environ[key] = value


def _deep_merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, val in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(val, dict):
            merged[key] = _deep_merge_dict(merged[key], val)
        else:
            merged[key] = val
    return merged


def _load_roles() -> dict[str, Any]:
    if not ROLES_PATH.is_file():
        print(f"ERROR missing {ROLES_PATH.relative_to(REPO)}", file=sys.stderr)
        sys.exit(1)
    with ROLES_PATH.open(encoding="utf-8") as f:
        spec = yaml.safe_load(f) or {}
    if ROLES_LOCAL_PATH.is_file():
        with ROLES_LOCAL_PATH.open(encoding="utf-8") as f:
            local = yaml.safe_load(f) or {}
        if isinstance(local, dict) and local:
            spec = _deep_merge_dict(spec, local)
    return spec


def _load_manifest() -> dict[str, Any]:
    if not MANIFEST_PATH.is_file():
        return {"ephemeral": {"dirs": ["agentic/hermes/.runtime"]}}
    with MANIFEST_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _hermes_bin() -> str | None:
    return shutil.which("hermes")


def _run_hermes(
    *argv: str,
    profile: str | None = None,
    capture: bool = True,
) -> subprocess.CompletedProcess[str]:
    hermes = _hermes_bin()
    if not hermes:
        raise RuntimeError("hermes not on PATH")
    cmd = [hermes]
    if profile:
        cmd.extend(["-p", profile])
    cmd.extend(argv)
    return subprocess.run(
        cmd,
        cwd=REPO,
        capture_output=capture,
        text=True,
        check=False,
    )


def _ollama_models_at(base_url: str) -> set[str]:
    """List model names from an Ollama HTTP API (tags endpoint)."""
    import urllib.error
    import urllib.request

    tags_url = base_url.rstrip("/").removesuffix("/v1") + "/api/tags"
    try:
        with urllib.request.urlopen(tags_url, timeout=5) as resp:
            payload = json.loads(resp.read().decode())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return set()
    names: set[str] = set()
    for item in payload.get("models") or []:
        name = item.get("name")
        if name:
            names.add(name)
    return names


def _ollama_models() -> set[str]:
    if not shutil.which("ollama"):
        return set()
    proc = subprocess.run(["ollama", "list"], capture_output=True, text=True)
    if proc.returncode != 0:
        return set()
    names: set[str] = set()
    for line in proc.stdout.splitlines()[1:]:
        parts = line.split()
        if parts:
            names.add(parts[0])
    return names


def _resolve_ollama_config(spec: dict[str, Any], *, remote: bool = False) -> dict[str, str]:
    target = (os.environ.get("OLLAMA_TARGET") or "").strip().lower()
    use_remote = remote or target == "remote"
    block = (spec.get("ollama_remote") if use_remote else None) or spec.get("ollama") or {}
    if use_remote and not spec.get("ollama_remote"):
        block = spec.get("ollama") or {}

    provider = (os.environ.get("OLLAMA_PROVIDER") or "").strip() or block.get("provider") or "custom"
    base_url = (os.environ.get("OLLAMA_BASE_URL") or "").strip() or block.get("base_url") or "http://localhost:11434/v1"
    default_model = (os.environ.get("OLLAMA_MODEL") or "").strip() or block.get("default_model") or "llama3.1:latest"
    context_length = (os.environ.get("OLLAMA_CONTEXT_LENGTH") or "").strip() or str(
        block.get("context_length") or 131072
    )

    return {
        "provider": provider,
        "base_url": base_url,
        "default_model": default_model,
        "context_length": context_length,
        "remote": str(use_remote or "192.168.0.100" in base_url),
    }


def _resolve_model(requested: str, fallback: str, installed: set[str]) -> str:
    if not installed or requested in installed:
        return requested
    if fallback in installed:
        print(f"  WARN model {requested!r} not in ollama list — using {fallback!r}")
        return fallback
    print(f"  WARN model {requested!r} not installed — using {fallback!r} anyway")
    return fallback


def _profile_dir(name: str) -> Path:
    return HERMES_HOME / "profiles" / name


def _ensure_venv(*, install_kb_extract: bool = False) -> None:
    created = not (VENV.is_dir() and (VENV / "bin" / "python").is_file())
    if created:
        print("== bootstrap: Python venv ==")
        subprocess.run([sys.executable, "-m", "venv", str(VENV)], cwd=REPO, check=True)
    pip = VENV / "bin" / "pip"
    if REQUIREMENTS.is_file():
        subprocess.run([str(pip), "install", "-r", str(REQUIREMENTS)], cwd=REPO, check=True)
        print(f"  ✓ {VENV.relative_to(REPO)} + requirements.txt")
    elif created:
        print(f"  ✓ {VENV.relative_to(REPO)}")
    if install_kb_extract and REQUIREMENTS_KB_EXTRACT.is_file():
        subprocess.run([str(pip), "install", "-r", str(REQUIREMENTS_KB_EXTRACT)], cwd=REPO, check=True)
        print("  ✓ requirements-kb-extract.txt (unstructured + OCR)")


def _ensure_runtime_dirs() -> None:
    for sub in ("board", "memory", "logs", "artifacts"):
        (RUNTIME / sub).mkdir(parents=True, exist_ok=True)


def _ensure_generated_dirs() -> None:
    for path in (GENERATED_RESEARCHED, GENERATED_RECOMMENDED, GENERATED_PROPOSALS, GENERATED_INTAKE):
        path.mkdir(parents=True, exist_ok=True)


def _ensure_secrets_scaffold() -> None:
    src = KB_SCAFFOLD / "private" / "secrets"
    dest = KB_PRIVATE / "secrets"
    if not src.is_dir():
        return
    dest.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        if not item.is_file():
            continue
        target = dest / item.name
        if not target.is_file():
            shutil.copy2(item, target)


def _ensure_prompts_scaffold() -> None:
    src = KB_SCAFFOLD / "private" / "prompts"
    dest = KB_PRIVATE / "prompts"
    if not src.is_dir():
        return
    dest.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        target = dest / item.name
        if item.is_file() and not target.is_file():
            shutil.copy2(item, target)


def _kb_has_content(path: Path) -> bool:
    marker = path / KB_MARKER
    if marker.is_file():
        return True
    if not path.is_dir():
        return False
    return any(path.iterdir())


def _write_kb_marker(dest: Path) -> None:
    marker = dest / KB_MARKER
    marker.write_text(
        "# DO NOT COMMIT — local Career KB\n"
        "# Created by: python agentic/hermes/admin/manage.py bootstrap\n"
        "# Re-scaffold only with: bootstrap --force-kb (overwrites files)\n",
        encoding="utf-8",
    )


def _copy_kb_scaffold(layer: str, *, force: bool) -> None:
    src = KB_SCAFFOLD / layer
    dest = KB_ROOT / layer
    label = f"agentic/hermes/.kb/{layer}"

    if not src.is_dir():
        print(f"  ERROR missing scaffold {src.relative_to(REPO)}", file=sys.stderr)
        sys.exit(1)

    KB_ROOT.mkdir(parents=True, exist_ok=True)

    if _kb_has_content(dest):
        if not force:
            print(
                f"  SKIP {label} — already exists (contains data or {KB_MARKER}).\n"
                f"       To overwrite: python agentic/hermes/admin/manage.py bootstrap --force-kb",
                file=sys.stderr,
            )
            return
        print(f"  WARN overwriting {label} (--force-kb)", file=sys.stderr)
        shutil.rmtree(dest)

    shutil.copytree(src, dest)
    _write_kb_marker(dest)
    print(f"  ✓ {label} ← scaffold/{layer}")


def _migrate_legacy_kb() -> None:
    for old_name, layer in LEGACY_KB_DIRS.items():
        old = REPO / old_name
        dest = KB_ROOT / layer
        if not old.is_dir() or _kb_has_content(dest):
            continue
        KB_ROOT.mkdir(parents=True, exist_ok=True)
        shutil.move(str(old), str(dest))
        print(f"  ✓ migrated {old_name}/ → agentic/hermes/.kb/{layer}/")

    # Repo-root .kb/ → agentic/hermes/.kb/ (one-time; skip if inner already populated)
    if LEGACY_KB_ROOT.is_dir() and not _kb_has_content(KB_ROOT):
        KB_ROOT.mkdir(parents=True, exist_ok=True)
        for child in LEGACY_KB_ROOT.iterdir():
            target = KB_ROOT / child.name
            if child.name.startswith("."):
                continue
            if child.is_dir():
                shutil.copytree(child, target, dirs_exist_ok=True)
            elif child.is_file():
                shutil.copy2(child, target)
        print("  ✓ migrated .kb/ → agentic/hermes/.kb/")


def _ensure_templates() -> None:
    """Copy scaffold templates into .kb/templates/ when missing."""
    scaffold = KB_SCAFFOLD / "templates"
    dest = KB_ROOT / "templates"
    if not scaffold.is_dir():
        return
    if dest.is_dir() and any(dest.rglob("*.docx")):
        return
    KB_ROOT.mkdir(parents=True, exist_ok=True)
    shutil.copytree(scaffold, dest, dirs_exist_ok=True)
    print("  ✓ agentic/hermes/.kb/templates/ ← scaffold/templates")


def bootstrap_kb(*, force: bool = False) -> None:
    print("== bootstrap: Career Knowledge Base ==")
    print("  agentic/hermes/.kb/ is gitignored — never commit it.")
    _migrate_legacy_kb()
    for layer in ("public", "private"):
        _copy_kb_scaffold(layer, force=force)
    _ensure_inbox_and_index()
    _ensure_prompts_scaffold()
    _ensure_secrets_scaffold()
    _ensure_templates()


def _ensure_inbox_and_index() -> None:
    KB_ROOT.mkdir(parents=True, exist_ok=True)
    inbox_readme = KB_SCAFFOLD / "inbox" / "README.md"
    if not KB_INBOX.is_dir():
        KB_INBOX.mkdir(parents=True, exist_ok=True)
        if inbox_readme.is_file():
            shutil.copy2(inbox_readme, KB_INBOX / "README.md")
        print("  ✓ .kb/inbox/ (drop zone)")
    elif not any(KB_INBOX.iterdir()):
        if inbox_readme.is_file():
            shutil.copy2(inbox_readme, KB_INBOX / "README.md")
    KB_INDEX.mkdir(parents=True, exist_ok=True)
    (KB_INDEX / "extracted").mkdir(parents=True, exist_ok=True)
    KB_INDEX_DB.mkdir(parents=True, exist_ok=True)
    print("  ✓ agentic/hermes/.kb/_index/ (derived catalog)")
    print("  ✓ agentic/hermes/.kb/index_db/ (ChromaDB RAG)")


def _configure_default_ollama(
    model: str,
    provider: str,
    base_url: str,
    context_length: str,
    *,
    dry_run: bool,
) -> None:
    print("== setup: default profile → Ollama ==")
    for key, value in (
        ("model.default", model),
        ("model.provider", provider),
        ("model.base_url", base_url),
        ("model.context_length", context_length),
    ):
        if dry_run:
            print(f"  would hermes config set {key} {value}")
            continue
        proc = _run_hermes("config", "set", key, value)
        if proc.returncode != 0:
            print(proc.stderr or proc.stdout, file=sys.stderr)
            sys.exit(proc.returncode)
    if not dry_run:
        print(f"  ✓ default → {model} @ {base_url}")


def _profile_model_config(
    profile: str,
    model: str,
    provider: str,
    base_url: str,
    context_length: str,
    *,
    dry_run: bool,
) -> None:
    for key, value in (
        ("model.default", model),
        ("model.provider", provider),
        ("model.base_url", base_url),
        ("model.context_length", context_length),
    ):
        if dry_run:
            print(f"  would hermes -p {profile} config set {key} {value}")
            continue
        proc = _run_hermes("config", "set", key, value, profile=profile)
        if proc.returncode != 0:
            print(proc.stderr or proc.stdout, file=sys.stderr)
            sys.exit(proc.returncode)


def _ensure_profile(
    name: str,
    description: str,
    *,
    dry_run: bool,
    clone_from: str = "default",
) -> None:
    if _profile_dir(name).is_dir():
        if dry_run:
            print(f"  would update {name} description")
            return
        proc = _run_hermes("profile", "describe", name, "--text", description)
        if proc.returncode != 0:
            print(proc.stderr or proc.stdout, file=sys.stderr)
            sys.exit(proc.returncode)
        print(f"  ✓ profile {name} (updated description)")
        return
    if dry_run:
        print(f"  would create profile {name}")
        return
    proc = _run_hermes(
        "profile",
        "create",
        name,
        "--clone-from",
        clone_from,
        "--description",
        description,
    )
    if proc.returncode != 0:
        print(proc.stderr or proc.stdout, file=sys.stderr)
        sys.exit(proc.returncode)
    print(f"  ✓ profile {name} (created)")


def _deploy_soul(name: str, *, dry_run: bool) -> None:
    src = SOULS_DIR / f"{name}.md"
    if not src.is_file():
        return
    dest = _profile_dir(name) / "SOUL.md"
    if dry_run:
        print(f"  would deploy SOUL.md for {name}")
        return
    if not _profile_dir(name).is_dir():
        print(f"  WARN skip SOUL for {name} — profile dir missing")
        return
    shutil.copy2(src, dest)
    print(f"  ✓ SOUL.md → {name}")


def _deploy_repo_onboarding(name: str, *, dry_run: bool) -> None:
    """Copy .agents/onboarding/hermes-and-repo.md into the Hermes profile dir."""
    if not REPO_ONBOARDING_SRC.is_file():
        return
    dest = _profile_dir(name) / "REPO_ONBOARDING.md"
    if dry_run:
        print(f"  would deploy REPO_ONBOARDING.md for {name}")
        return
    if not _profile_dir(name).is_dir():
        return
    shutil.copy2(REPO_ONBOARDING_SRC, dest)
    print(f"  ✓ REPO_ONBOARDING.md → {name}")


def _configure_toolsets(toolsets: list[str], *, dry_run: bool) -> None:
    payload = json.dumps(toolsets)
    if dry_run:
        print(f"  would hermes config set toolsets {payload}")
        return
    proc = _run_hermes("config", "set", "toolsets", payload)
    if proc.returncode != 0:
        print(proc.stderr or proc.stdout, file=sys.stderr)
        sys.exit(proc.returncode)
    print(f"  ✓ default toolsets {payload}")


def _configure_profile_toolsets(profile: str, toolsets: list[str], *, dry_run: bool) -> None:
    payload = json.dumps(toolsets)
    if dry_run:
        print(f"  would hermes -p {profile} config set toolsets {payload}")
        return
    proc = _run_hermes("config", "set", "toolsets", payload, profile=profile)
    if proc.returncode != 0:
        print(proc.stderr or proc.stdout, file=sys.stderr)
        sys.exit(proc.returncode)
    print(f"  ✓ {profile} toolsets {payload}")


def _configure_web(*, dry_run: bool) -> None:
    print("== setup: web search (ddgs) ==")
    if dry_run:
        print("  would hermes config set web.backend ddgs")
        return
    proc = _run_hermes("config", "set", "web.backend", "ddgs")
    if proc.returncode != 0:
        print(proc.stderr or proc.stdout, file=sys.stderr)
        sys.exit(proc.returncode)
    print("  ✓ web.backend ddgs")
    proc = _run_hermes("tools", "post-setup", "ddgs")
    if proc.returncode != 0:
        print(proc.stderr or proc.stdout, file=sys.stderr)
        sys.exit(proc.returncode)
    print("  ✓ ddgs post-setup")


_LEGACY_PROFILES = ("kb_manager", "job_researcher", "application_coach")


def _retire_legacy_profiles(*, dry_run: bool) -> None:
    """Remove pre-Zazu Hermes profile dirs so only zazu_* remain."""
    print("\n== setup: retire legacy profiles (kb_manager, job_researcher, application_coach) ==")
    for name in _LEGACY_PROFILES:
        if not _profile_dir(name).is_dir():
            continue
        if dry_run:
            print(f"  would hermes profile delete {name}")
            continue
        proc = _run_hermes("profile", "delete", name, "-y")
        if proc.returncode != 0:
            print(proc.stderr or proc.stdout, file=sys.stderr)
            print(f"  WARN could not delete legacy profile {name}", file=sys.stderr)
        else:
            print(f"  ✓ deleted legacy profile {name}")


def setup_agents(*, dry_run: bool = False, remote: bool = False) -> int:
    if not _hermes_bin():
        print("hermes not on PATH — install upstream Hermes, then re-run setup.", file=sys.stderr)
        return 1

    spec = _load_roles()
    ollama = _resolve_ollama_config(spec, remote=remote)
    provider = ollama["provider"]
    base_url = ollama["base_url"]
    default_model = ollama["default_model"]
    context_length = ollama["context_length"]
    installed = _ollama_models_at(base_url) or _ollama_models()
    toolsets = spec.get("toolsets") or ["hermes-cli", "kanban"]

    label = "remote 4090" if ollama.get("remote") == "True" else "local"
    print(f"== setup: Career Intelligence profiles ({label}) ==")
    print(f"  Ollama: {default_model} @ {base_url} (ctx {context_length})")
    _configure_default_ollama(default_model, provider, base_url, context_length, dry_run=dry_run)

    toolset_keys = {
        "zazu_knowledge_manager": spec.get("zazu_knowledge_manager_toolsets"),
        "zazu_researcher": spec.get("zazu_researcher_toolsets"),
        "zazu_coach": spec.get("zazu_coach_toolsets"),
    }

    for role in spec.get("roles") or []:
        name = role["name"]
        description = (role.get("description") or "").strip()
        model = _resolve_model(role.get("model") or default_model, default_model, installed)
        print(f"\n== setup: {name} ==")
        _ensure_profile(name, description, dry_run=dry_run)
        _profile_model_config(
            name, model, provider, base_url, context_length, dry_run=dry_run
        )
        _deploy_soul(name, dry_run=dry_run)
        _deploy_repo_onboarding(name, dry_run=dry_run)
        per_role = toolset_keys.get(name)
        if per_role:
            _configure_profile_toolsets(name, per_role, dry_run=dry_run)
        if not dry_run:
            print(f"  ✓ {name} → {model}")

    _configure_toolsets(toolsets, dry_run=dry_run)
    _configure_web(dry_run=dry_run)
    _retire_legacy_profiles(dry_run=dry_run)

    print("\n== setup: done ==")
    print("  Chat:   python agentic/hermes/admin/manage.py hermes dashboard")
    print("  Evaluate a job (zazu_researcher profile):")
    print('    EVALUATE_OPPORTUNITY\\nurl: ...\\ndescription: |\\n  <pasted JD>')
    print("  Docs:   agentic/hermes/working_agreements.md")
    return 0


def cmd_bootstrap(args: argparse.Namespace) -> int:
    print("== Project Career Zazu bootstrap ==")
    _ensure_venv(install_kb_extract=getattr(args, "extract_kb", False))
    _ensure_runtime_dirs()
    _ensure_generated_dirs()
    print(f"  ✓ {RUNTIME.relative_to(REPO)}")
    print(f"  ✓ {GENERATED.relative_to(REPO)}")
    bootstrap_kb(force=args.force_kb)
    if getattr(args, "extract_kb", False):
        rc = cmd_kb_extract(argparse.Namespace(force_organize=True, skip_rag=False))
        if rc != 0:
            return rc
    if args.skip_setup:
        print("Skipping Hermes profile setup (--skip-setup).")
        return 0
    return setup_agents(dry_run=False, remote=args.remote)


def cmd_install_deps(args: argparse.Namespace) -> int:
    """Install pip requirements into .venv (new machine / after git pull)."""
    print("== install-deps ==")
    _ensure_venv(install_kb_extract=args.kb_extract)
    if getattr(args, "email", False) and REQUIREMENTS_EMAIL.is_file():
        pip = VENV / "bin" / "pip"
        subprocess.run([str(pip), "install", "-r", str(REQUIREMENTS_EMAIL)], cwd=REPO, check=True)
        print("  ✓ requirements-email.txt (Gmail + Outlook poll)")
    return 0


def cmd_setup(args: argparse.Namespace) -> int:
    return setup_agents(dry_run=args.dry_run, remote=args.remote)


def cmd_status(_: argparse.Namespace) -> int:
    spec = _load_roles()
    ollama = _resolve_ollama_config(spec)
    print(f"Repo: {REPO}")
    print(f"Hermes pkg: {HERMES_PKG.relative_to(REPO)}")
    env_label = "loaded" if DOTENV_PATH.is_file() else "missing (copy .env.example → .env)"
    print(f"  {'✓' if DOTENV_PATH.is_file() else '·'} .env ({env_label})")
    remote_flag = ollama.get("remote") == "True"
    print(
        f"  Ollama: {ollama['default_model']} @ {ollama['base_url']} "
        f"({'remote' if remote_flag else 'local'})"
    )
    rows = [
        (".venv", VENV.is_dir()),
        ("agentic/hermes/.kb/public", KB_PUBLIC.is_dir()),
        ("agentic/hermes/.kb/private", KB_PRIVATE.is_dir()),
        ("agentic/hermes/.kb/inbox", KB_INBOX.is_dir()),
        ("agentic/hermes/.kb/_index", KB_INDEX.is_dir()),
        ("agentic/hermes/.kb/index_db", KB_INDEX_DB.is_dir()),
        ("agentic/hermes/.generated", GENERATED.is_dir()),
        ("agentic/hermes/.runtime", RUNTIME.is_dir()),
        ("config/hermes_roles.yaml", ROLES_PATH.is_file()),
        ("config/hermes_roles.local.yaml", ROLES_LOCAL_PATH.is_file()),
        ("schemas/opportunity_v1.yaml", (HERMES_PKG / "schemas/opportunity_v1.yaml").is_file()),
        ("schemas/kb_catalog_v1.yaml", (HERMES_PKG / "schemas/kb_catalog_v1.yaml").is_file()),
    ]
    for name, ok in rows:
        print(f"  {'✓' if ok else '·'} {name}")
    hermes = _hermes_bin()
    print(f"  {'✓' if hermes else '·'} hermes CLI ({hermes or 'not on PATH'})")
    if shutil.which("ollama"):
        models = sorted(_ollama_models())
        print(f"  ✓ ollama ({len(models)} models)" if models else "  · ollama (no models)")
    else:
        print("  · ollama (not on PATH)")
    return 0


def _rm(path: Path) -> None:
    if not path.exists():
        return
    print(f"  rm {path.relative_to(REPO)}")
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def cmd_nuke(args: argparse.Namespace) -> int:
    if not args.yes:
        print("Dry run — re-run with --yes to clear agentic/hermes/.runtime", file=sys.stderr)
        return 1
    print("== nuke agentic ephemeral ==")
    manifest = _load_manifest()
    for rel in manifest.get("ephemeral", {}).get("dirs", []):
        _rm(REPO / rel)
    _ensure_runtime_dirs()
    print("Runtime cleared.")
    return 0


def _import_kb_scan():
    if str(HERMES_PKG) not in sys.path:
        sys.path.insert(0, str(HERMES_PKG))
    from lib.kb import scan_kb

    return scan_kb


def _import_extract_kb():
    if str(HERMES_PKG) not in sys.path:
        sys.path.insert(0, str(HERMES_PKG))
    from lib.kb import extract_kb

    return extract_kb


def _import_apply():
    if str(HERMES_PKG) not in sys.path:
        sys.path.insert(0, str(HERMES_PKG))
    from lib.generated.apply import (
        extract_job_id_from_url,
        parse_search_consider,
        parse_search_consider_all,
        planned_filenames,
        write_proposal_triplet,
    )
    from lib.generated.docx_io import coach_sidecar_status, materialize_markdown_sidecars
    from lib.generated.patch_quality import prepare_run_patches

    return {
        "extract_job_id_from_url": extract_job_id_from_url,
        "parse_search_consider": parse_search_consider,
        "parse_search_consider_all": parse_search_consider_all,
        "planned_filenames": planned_filenames,
        "write_proposal_triplet": write_proposal_triplet,
        "materialize_markdown_sidecars": materialize_markdown_sidecars,
        "coach_sidecar_status": coach_sidecar_status,
        "prepare_run_patches": prepare_run_patches,
    }


def _import_registry():
    if str(HERMES_PKG) not in sys.path:
        sys.path.insert(0, str(HERMES_PKG))
    from lib.kb.application_registry import (
        applications_db_path,
        find_company_overlap,
        find_exact,
        format_registry_summary,
        import_vault_folders,
        list_applications,
        record_outcome,
        upsert_application,
    )

    return {
        "applications_db_path": applications_db_path,
        "find_company_overlap": find_company_overlap,
        "find_exact": find_exact,
        "format_registry_summary": format_registry_summary,
        "import_vault_folders": import_vault_folders,
        "list_applications": list_applications,
        "record_outcome": record_outcome,
        "upsert_application": upsert_application,
    }


def cmd_kb_extract(args: argparse.Namespace) -> int:
    """Deep extract vault, build RAG index, organize canonical KB markdown."""
    if not KB_ROOT.is_dir():
        print("Career KB missing — run: python agentic/hermes/admin/manage.py bootstrap", file=sys.stderr)
        return 1
    _ensure_inbox_and_index()

    extract_kb = _import_extract_kb()
    scan_id = datetime.now().strftime("%Y%m%d%H%M%S")
    print("== kb-extract: deep vault ingest + RAG ==")
    print(f"  KB root:   {KB_ROOT.relative_to(REPO)}")
    print(f"  RAG store: {KB_INDEX_DB.relative_to(REPO)}")
    try:
        result = extract_kb(
            REPO,
            scan_id=scan_id,
            force_organize=args.force_organize,
            skip_rag=args.skip_rag,
            skip_registry=getattr(args, "skip_registry", False),
        )
    except (FileNotFoundError, ImportError, RuntimeError) as exc:
        print(exc, file=sys.stderr)
        return 1

    print(f"\n  scanned:        {result.scanned}")
    print(f"  deep extracted: {result.deep_extracted} (unstructured/OCR)")
    print(f"  chunks:         {result.chunk_count} (BM25 + vector corpus)")
    if not args.skip_rag:
        print(f"  embedded:       {result.embedded_count} ({result.embed_model})")
    if not getattr(args, "skip_registry", False):
        print(
            f"  registry:       {result.registry_imported} vault folder(s) → "
            f"{result.applications_db_path.relative_to(REPO)}"
        )
    print(f"  organized:      {len(result.organized_files)} file(s)")
    for rel in result.organized_files:
        print(f"    · {rel}")
    print(f"  ✓ catalog → {result.catalog_path.relative_to(REPO)}")
    print(f"  ✓ chunks  → {result.chunks_path.relative_to(REPO)}")
    if not args.skip_rag:
        print(f"  ✓ ChromaDB → {result.index_db_path.relative_to(REPO)}")
    return 0


def cmd_kb_scan(args: argparse.Namespace) -> int:
    """Scan .kb/, update derived catalog, optionally invoke zazu_knowledge_manager."""
    if not KB_ROOT.is_dir():
        print("Career KB missing — run: python agentic/hermes/admin/manage.py bootstrap", file=sys.stderr)
        return 1
    _ensure_inbox_and_index()

    scan_kb = _import_kb_scan()
    scan_id = datetime.now().strftime("%Y%m%d%H%M%S")
    print("== kb-scan: index Career KB ==")
    print(f"  KB root: {KB_ROOT.relative_to(REPO)}")
    try:
        result = scan_kb(REPO, scan_id=scan_id, force_extract=args.force_extract)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1

    print(f"  scanned:   {result.scanned}")
    print(f"  added:     {result.added}")
    print(f"  updated:   {result.updated}")
    print(f"  unchanged: {result.unchanged}")
    print(f"  removed:   {result.removed}")
    print(f"  pending relocation proposals: {result.proposals}")
    print(f"  ✓ catalog → {result.catalog_path.relative_to(REPO)}")
    if result.proposals:
        print(f"  · proposals → {result.relocation_path.relative_to(REPO)}")

    if args.agent:
        return _kb_scan_agent_review(result, scan_id=scan_id)
    return 0


def _kb_scan_agent_review(result, *, scan_id: str) -> int:
    hermes = _hermes_bin()
    if not hermes:
        print("hermes not on PATH — skipping --agent review.", file=sys.stderr)
        return 1

    proposals_path = result.relocation_path.relative_to(REPO)
    catalog_path = result.catalog_path.relative_to(REPO)
    prompt = f"""SCAN_KB
scan_id: {scan_id}

Review the derived KB catalog and relocation proposals from the latest scan.

Read:
- {catalog_path}
- {proposals_path}

Tasks:
1. Summarize what changed (new files, reclassifications, extraction gaps).
2. For each pending relocation proposal, confirm or correct the suggested path.
3. Flag any misclassified documents (especially inbox PDFs/images).
4. Do NOT move or delete files without explicit user approval.
5. Write a short report to agentic/hermes/.runtime/kb_scan_latest.md
"""

    print("\n== kb-scan: zazu_knowledge_manager review ==")
    print("$ hermes -p zazu_knowledge_manager chat -q ...")
    proc = subprocess.run(
        [hermes, "-p", "zazu_knowledge_manager", "chat", "-q", prompt],
        cwd=REPO,
        text=True,
    )
    report = RUNTIME / "kb_scan_latest.md"
    if report.is_file():
        print(f"\n  ✓ report → {report.relative_to(REPO)}")
    return proc.returncode


def cmd_apply(args: argparse.Namespace) -> int:
    """Write Application Coach DOCX triplet to .generated/proposals/<run>/."""
    if not KB_ROOT.is_dir():
        print("Career KB missing — run: python agentic/hermes/admin/manage.py bootstrap", file=sys.stderr)
        return 1

    if getattr(args, "all_from_search", False):
        apply_mod = _import_apply()
        search_path = GENERATED_RESEARCHED / "search_latest.md"
        picks = apply_mod["parse_search_consider_all"](search_path)
        if not picks:
            print(
                f"No APPLY/CONSIDER roles in {search_path.relative_to(REPO)} — run search first.",
                file=sys.stderr,
            )
            return 1
        print(f"== apply: {len(picks)} role(s) from search ==")
        exit_code = 0
        for index, picked in enumerate(picks, start=1):
            print(f"\n--- apply {index}/{len(picks)}: {picked['company']} / {picked['title']} ---")
            sub = argparse.Namespace(**vars(args))
            sub.all_from_search = False
            sub.from_search = False
            sub.company = picked["company"]
            sub.title = picked["title"]
            sub.url = picked.get("url", "")
            sub.job_id = picked.get("job_id", "")
            sub.run_prefix = None
            sub.force = True
            result = cmd_apply(sub)
            if result != 0:
                exit_code = result
        return exit_code

    apply_mod = _import_apply()
    parse_search_consider = apply_mod["parse_search_consider"]
    extract_job_id_from_url = apply_mod["extract_job_id_from_url"]
    planned_filenames = apply_mod["planned_filenames"]
    write_proposal_triplet = apply_mod["write_proposal_triplet"]

    url = (args.url or "").strip()
    if args.from_search:
        search_path = GENERATED_RESEARCHED / "search_latest.md"
        picked = parse_search_consider(search_path)
        if not picked:
            print(
                f"No APPLY/CONSIDER role in {search_path.relative_to(REPO)} — run search first.",
                file=sys.stderr,
            )
            return 1
        company = picked["company"]
        job_title = picked["title"]
        url = url or picked.get("url", "")
        job_id = args.job_id or picked.get("job_id") or extract_job_id_from_url(url)
    else:
        company = (args.company or "").strip()
        job_title = (args.title or "").strip()
        if not company or not job_title:
            print("Provide --company and --title, or use --from-search.", file=sys.stderr)
            return 1
        job_id = args.job_id or extract_job_id_from_url(url)

    company = re.sub(r"\s*\([^)]*\)", "", company).strip()
    job_date = (args.job_date or "").strip() or datetime.now().strftime("%Y%m%d")
    job_id = job_id or "na"

    GENERATED.mkdir(parents=True, exist_ok=True)
    GENERATED_PROPOSALS.mkdir(parents=True, exist_ok=True)

    names = planned_filenames(
        company=company,
        job_title=job_title,
        job_id=job_id,
        job_date=job_date,
    )

    reg = _import_registry()
    db_path = reg["applications_db_path"](KB_INDEX)
    prior = reg["find_company_overlap"](db_path, company)
    if prior and not getattr(args, "force", False):
        print("\n  ⚠ Application registry — prior record(s) at this company:", file=sys.stderr)
        for rec in prior:
            print(
                f"    · {rec.job_date or '?'} | {rec.job_title} | status={rec.status} | {rec.vault_path or rec.proposal_run or rec.opportunity_id}",
                file=sys.stderr,
            )
        print("  Use --force to apply anyway (different requisition).", file=sys.stderr)
        return 1

    exact = reg["find_exact"](db_path, company=company, job_title=job_title, job_id=job_id)
    if exact and exact.status == "applied" and not getattr(args, "force", False):
        print(f"\n  ⚠ Already recorded: {exact.opportunity_id} status={exact.status}", file=sys.stderr)
        print("  Use --force to write a new proposal run.", file=sys.stderr)
        return 1

    print(f"== apply: Application Coach DOCX — {company} / {job_title} ==")
    print(f"  naming: {names['resume']}")

    try:
        run_dir, paths = write_proposal_triplet(
            kb_root=KB_ROOT,
            repo=REPO,
            proposals_root=GENERATED_PROPOSALS,
            company=company,
            job_title=job_title,
            job_id=job_id,
            job_date=job_date,
            run_prefix=args.run_prefix,
            url=url,
        )
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        print(
            "Ensure pm-resume.docx and cover.docx exist under .kb/private/originals/resume-repo/",
            file=sys.stderr,
        )
        return 1
    except ImportError as exc:
        print(str(exc), file=sys.stderr)
        print("Run: python agentic/hermes/admin/manage.py install-deps", file=sys.stderr)
        return 1

    for path in paths:
        print(f"  ✓ {path.relative_to(REPO)}")
    print(f"  run dir → {run_dir.relative_to(REPO)}")

    resume_rel = cover_rel = brief_rel = None
    for path in paths:
        rel = path.relative_to(REPO).as_posix()
        if rel.endswith("_resume.docx"):
            resume_rel = rel
        elif rel.endswith("_cover.docx"):
            cover_rel = rel
        elif rel.endswith("_brief.docx"):
            brief_rel = rel

    rec = reg["upsert_application"](
        db_path,
        company=company,
        job_title=job_title,
        job_id=job_id,
        apply_url=url or None,
        status="applied",
        job_date=job_date,
        proposal_run=run_dir.name,
        resume_path=resume_rel,
        cover_path=cover_rel,
        brief_path=brief_rel,
        notes=f"apply run {run_dir.name}",
    )
    print(f"  ✓ registry → {db_path.relative_to(REPO)} ({rec.opportunity_id})")

    if args.coach:
        hermes = _hermes_bin()
        if not hermes:
            print("hermes not on PATH — DOCX written; --coach skipped.", file=sys.stderr)
            return 0
        file_list = "\n".join(f"- {run_dir / name}" for name in names.values())
        md_list = "\n".join(
            f"- {run_dir / name.replace('.docx', '_patch.md')}" for name in names.values()
        )
        kb_root = KB_ROOT.resolve()
        search_latest = (GENERATED / "researched" / "search_latest.md").resolve()
        prompt = f"""APPLY_OPPORTUNITY
company: {company}
title: {job_title}
job_id: {job_id}
job_date: {job_date}
url: {url or "na"}

Career KB (read these paths — they exist on disk):
  root: {kb_root}/
  job_fitness: {kb_root / "private/prompts/job_fitness.md"}
  manifest: {kb_root / "templates/manifest.yaml"}
  master_resume: {kb_root / "public/master_resume.md"}
  skills: {kb_root / "public/skills.md"}
  search_latest: {search_latest}

Templates (DO NOT edit binary .docx):
  resume → {kb_root / "templates/resume/pm-resume.docx"}
  cover  → {kb_root / "templates/cover/cover.docx"}
  brief  → {kb_root / "templates/brief/application-brief.docx"}

Write **three required section-patch files** (pipeline merges into DOCX locally):
{md_list}

Patch format: markdown with level-2 headings matching manifest section ids exactly.
Example:
## SUMMARY
(one tailored paragraph)

## EXPERIENCES
Senior Software Engineering Manager, Adobe, [05/2024 - Present]
Lead two teams...

Resume sections (required): SUMMARY, AREAS_OF_EXPERTISE, EXPERIENCES, EDUCATION.
Resume optional (omit heading block to drop): SELECTED_TECHNICAL, CERTIFICATIONS, SELECTED_THEMES, TECH_STACK.

Cover sections (required): COVER_P1 … COVER_P5 (narrative paragraphs; use employer name and role title).

Brief sections (ALL required — do not skip):
OPPORTUNITY_INTELLIGENCE, FLAG_ANALYSIS, LEVEL_MAPPING, EMPLOYER_SUMMARY,
TOP_MATCHING_EXPERIENCE, JD_ALIGNMENT, GAPS_MITIGATIONS, STAR_STORIES,
INTERVIEW_INTELLIGENCE, COMPENSATION_NEXT_STEPS, RECOMMENDATION.

RECOMMENDATION must state APPLY / CONSIDER / SKIP with top 3 KB-backed reasons.
Do not invent experience — trace every claim to the KB or search report.
Do not attempt to edit binary .docx directly.

Writing quality: zero tolerance for spelling/grammar errors, invented words, or
unexpanded abbreviations. Proofread every patch section before saving.

**Required deliverable this session:** write all three *_patch.md files listed above before you stop.
Use search_latest + master_resume as primary sources; keep web research brief (one pass max).
Do not end the session until all three patch files exist on disk.
"""
        print("\n== apply: zazu_coach customization ==")
        print("$ hermes -p zazu_coach chat -q ...")
        proc = subprocess.run(
            [hermes, "-p", "zazu_coach", "chat", "-q", prompt],
            cwd=REPO,
            text=True,
        )
        prepare_patches = apply_mod["prepare_run_patches"]
        patch_report = prepare_patches(run_dir)
        patch_errors = [
            f"{name}: {msg}"
            for name, notes in patch_report.items()
            for msg in notes
            if msg.startswith("error:")
        ]
        if patch_report:
            print("\n== apply: patch quality ==")
            for name, notes in sorted(patch_report.items()):
                for note in notes:
                    prefix = "  ⚠" if note.startswith("error:") else "  ·"
                    print(f"{prefix} {name}: {note}")
        materialize = apply_mod["materialize_markdown_sidecars"]
        merged = materialize(
            run_dir,
            company=company,
            job_title=job_title,
            job_id=job_id,
            job_date=job_date,
            url=url or "",
        )
        sidecars = apply_mod["coach_sidecar_status"](run_dir)
        if merged:
            print("\n== apply: merged coach markdown → DOCX ==")
            for path in merged:
                print(f"  ✓ {path.relative_to(REPO)}")
        missing = [kind for kind, ok in sidecars.items() if not ok]
        if missing:
            print(
                f"\n  ⚠ Coach missing sidecar(s): {', '.join(missing)} — "
                "DOCX may still use template/KB fill for those files.",
                file=sys.stderr,
            )
        elif not merged:
            print(
                "\n  ⚠ Coach did not write *_resume_patch.md / *_cover_patch.md / *_brief_patch.md — "
                "DOCX still has template/KB fill only.",
                file=sys.stderr,
            )
        if patch_errors:
            print(
                f"\n  ⚠ Patch validation reported {len(patch_errors)} issue(s) — review before submitting.",
                file=sys.stderr,
            )
        return proc.returncode

    return 0


def cmd_applications(args: argparse.Namespace) -> int:
    """Application registry (SQLite) — list, import vault, record outcomes."""
    if not KB_ROOT.is_dir():
        print("Career KB missing — run bootstrap first.", file=sys.stderr)
        return 1

    reg = _import_registry()
    db_path = reg["applications_db_path"](KB_INDEX)

    if args.applications_cmd == "list":
        rows = reg["list_applications"](db_path, limit=args.limit)
        if not rows:
            print("(no applications recorded)")
            return 0
        print(f"== applications ({db_path.relative_to(REPO)}) ==")
        for rec in rows:
            extra = rec.vault_path or rec.proposal_run or ""
            print(
                f"  {rec.status:12} | {rec.job_date or '????????'} | {rec.company} | {rec.job_title} | {rec.job_id or 'na'} | {extra}"
            )
        return 0

    if args.applications_cmd == "import-vault":
        imported = reg["import_vault_folders"](KB_ROOT, db_path)
        print(f"== import-vault: {len(imported)} folder(s) → {db_path.relative_to(REPO)} ==")
        for rec in imported[:20]:
            print(f"  ✓ {rec.company} | {rec.job_title} | {rec.job_date} | {rec.vault_path}")
        if len(imported) > 20:
            print(f"  … and {len(imported) - 20} more")
        return 0

    if args.applications_cmd == "register":
        notes = (args.notes or "").strip()
        if args.ats:
            prefix = f"ATS {args.ats}"
            notes = f"{prefix} | {notes}" if notes else prefix
        rec = reg["upsert_application"](
            db_path,
            company=args.company,
            job_title=args.title,
            job_id=args.job_id or None,
            apply_url=args.url or None,
            status=args.status,
            job_date=args.job_date or None,
            notes=notes or None,
        )
        print(f"  ✓ {rec.opportunity_id} | {rec.company} | {rec.job_title} | status={rec.status}")

        if str(HERMES_PKG) not in sys.path:
            sys.path.insert(0, str(HERMES_PKG))
        from lib.kb.learning_registry import (
            normalize_topic,
            record_learning_event,
            set_application_topics,
        )

        topics_raw = getattr(args, "topics", "") or ""
        if topics_raw.strip():
            topic_list = [normalize_topic(t) for t in topics_raw.split(",")]
            topic_list = [t for t in topic_list if t != "na"]
            if topic_list:
                set_application_topics(db_path, rec.opportunity_id, topic_list, source="user")
                print(f"  · topics: {', '.join(topic_list)}")

        if notes or args.status in ("rejected", "withdrawn", "skipped", "offered", "interviewing"):
            explanation = notes or f"Status recorded as {args.status}."
            source_type = "user_rejection" if args.status == "rejected" else "user_outcome"
            event = record_learning_event(
                db_path,
                source_type=source_type,
                source_ref=rec.opportunity_id,
                target=f"status:{args.status}",
                action="auto_applied",
                explanation=explanation,
            )
            print(f"  · learning_event: {event.event_id}")
        return 0

    if args.applications_cmd == "record-outcome":
        rec = reg["record_outcome"](
            db_path,
            opportunity_id=args.opportunity_id,
            company=args.company,
            status=args.status,
            notes=args.notes,
        )
        if rec is None:
            print("No matching application — use --opportunity-id or --company.", file=sys.stderr)
            return 1
        print(f"  ✓ {rec.opportunity_id} → status={rec.status}")

        if str(HERMES_PKG) not in sys.path:
            sys.path.insert(0, str(HERMES_PKG))
        from lib.kb.learning_registry import (
            normalize_topic,
            record_learning_event,
            set_application_topics,
        )

        topics_raw = getattr(args, "topics", "") or ""
        if topics_raw.strip():
            topic_list = [normalize_topic(t) for t in topics_raw.split(",")]
            topic_list = [t for t in topic_list if t != "na"]
            if topic_list:
                set_application_topics(db_path, rec.opportunity_id, topic_list, source="user")
                print(f"  · topics: {', '.join(topic_list)}")

        notes = (args.notes or "").strip()
        if notes or args.status in ("rejected", "withdrawn", "skipped", "offered", "interviewing"):
            explanation = notes or f"Status recorded as {args.status}."
            source_type = "user_rejection" if args.status == "rejected" else "user_outcome"
            event = record_learning_event(
                db_path,
                source_type=source_type,
                source_ref=rec.opportunity_id,
                target=f"status:{args.status}",
                action="auto_applied",
                explanation=explanation,
            )
            print(f"  · learning_event: {event.event_id}")
        return 0

    return 1


def cmd_career(args: argparse.Namespace) -> int:
    """Career orchestration STATUS / ANALYZE — CKM front desk tools."""
    if str(HERMES_PKG) not in sys.path:
        sys.path.insert(0, str(HERMES_PKG))

    import json

    from lib.career.orchestration import career_status
    from lib.kb.application_registry import applications_db_path
    from lib.kb.learning_registry import list_learning_events, topic_response_rates

    db_path = applications_db_path(KB_INDEX)
    cmd = args.career_cmd

    if cmd == "status":
        payload = career_status(
            repo=REPO,
            kb_index=KB_INDEX,
            generated_researched=GENERATED_RESEARCHED,
            generated_proposals=GENERATED_PROPOSALS,
            generated_intake=GENERATED_INTAKE,
        )
        if getattr(args, "json", False):
            print(json.dumps(payload, indent=2))
            return 0
        print("== career status (Career Zazu) ==")
        co = payload.get("coexistence", {})
        print(f"  product: {payload.get('product')}")
        print(f"  kanban: {co.get('career_task_count', 0)} career / {co.get('digest_task_count', 0)} digest tasks (shared board)")
        art = payload.get("artifacts", {})
        sl = art.get("search_latest", {})
        print(f"  search_latest: {sl.get('path') or '(none)'} {sl.get('mtime') or ''}")
        sj = art.get("search_jobspy", {})
        print(f"  search_jobspy: {sj.get('path') or '(none)'} {sj.get('mtime') or ''}")
        ep = art.get("email_poll_latest", {})
        print(f"  email_poll_latest: {ep.get('path') or '(none)'} {ep.get('mtime') or ''}")
        print(f"  latest_proposal_run: {art.get('latest_proposal_run') or '(none)'}")
        reg = payload.get("registry", {})
        if reg.get("status_counts"):
            print(f"  registry: {reg.get('status_counts')}")
        return 0

    if cmd == "topics":
        stats = topic_response_rates(db_path)
        if getattr(args, "json", False):
            print(json.dumps([s.__dict__ for s in stats], indent=2))
            return 0
        print(f"== career topics ({db_path.relative_to(REPO)}) ==")
        if not stats:
            print("  (no tagged applications — use record-outcome --topics mcp,...)")
            return 0
        for s in stats:
            rate = f"{s.response_rate:.0%}" if s.response_rate is not None else "n/a"
            print(
                f"  {s.topic:20} total={s.total} applied={s.applied} "
                f"interviewing={s.interviewing} offered={s.offered} "
                f"rejected={s.rejected} response_rate={rate}"
            )
        return 0

    if cmd == "learning":
        events = list_learning_events(db_path, limit=args.limit)
        if getattr(args, "json", False):
            print(json.dumps([e.__dict__ for e in events], indent=2))
            return 0
        print(f"== learning events ({db_path.relative_to(REPO)}) ==")
        if not events:
            print("  (none)")
            return 0
        for e in events:
            print(f"  {e.event_id} | {e.action} | {e.source_type} | {e.target}")
            print(f"    ref={e.source_ref or '-'} | {e.explanation}")
        return 0

    return 1


def _import_secrets_vault():
    if str(HERMES_PKG) not in sys.path:
        sys.path.insert(0, str(HERMES_PKG))
    from lib.kb import secrets_vault

    return secrets_vault


def cmd_secrets(args: argparse.Namespace) -> int:
    """Encrypted vault under .kb/private/secrets/ — never KB-scanned."""
    if not KB_ROOT.is_dir():
        print("Career KB missing — run: python agentic/hermes/admin/manage.py bootstrap", file=sys.stderr)
        return 1

    sv = _import_secrets_vault()
    path = sv.vault_path(KB_ROOT)
    cmd = args.secrets_cmd

    if cmd == "list":
        rows = sv.list_entries(path)
        if getattr(args, "json", False):
            print(json.dumps(rows, indent=2))
            return 0
        print(f"== secrets ({path.relative_to(REPO)}) ==")
        if not rows:
            print("  (empty — use: secrets set <key> --type … --from-json …)")
            return 0
        for row in rows:
            print(f"  {row['key']:20} type={row['type']:20} updated={row['updated_at']}")
        return 0

    if cmd == "unlock":
        if not path.is_file():
            print("  · vault not created yet — nothing to unlock")
            return 0
        phrase = (os.environ.get("CAREER_VAULT_PASSPHRASE") or "").strip()
        if not phrase:
            phrase = __import__("getpass").getpass("Vault passphrase: ")
        try:
            result = sv.unlock_vault(path, phrase)
        except Exception as exc:  # noqa: BLE001 — user-facing unlock failure
            print(f"  ✗ unlock failed: {exc}", file=sys.stderr)
            return 1
        print(f"  ✓ {result['message']} ({result['entries']} entries)")
        return 0

    phrase = (os.environ.get("CAREER_VAULT_PASSPHRASE") or "").strip()
    if not phrase:
        phrase = __import__("getpass").getpass("Vault passphrase: ")

    if cmd == "set":
        from_json = Path(args.from_json)
        if not from_json.is_file():
            print(f"missing --from-json file: {from_json}", file=sys.stderr)
            return 1
        try:
            payload = json.loads(from_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"invalid JSON: {exc}", file=sys.stderr)
            return 1
        if not isinstance(payload, dict):
            print("--from-json must contain a JSON object", file=sys.stderr)
            return 1
        try:
            sv.set_entry(
                path,
                entry_key=args.key,
                entry_type=args.type,
                payload=payload,
                passphrase=phrase,
            )
        except (ValueError, RuntimeError) as exc:
            print(exc, file=sys.stderr)
            return 1
        print(f"  ✓ stored {args.key} ({args.type}) → {path.relative_to(REPO)}")
        return 0

    if cmd == "delete":
        try:
            removed = sv.delete_entry(path, entry_key=args.key, passphrase=phrase)
        except Exception as exc:  # noqa: BLE001 — wrong passphrase or corrupt vault
            print(f"  ✗ delete failed: {exc}", file=sys.stderr)
            return 1
        if not removed:
            print(f"  · no such entry: {args.key}", file=sys.stderr)
            return 1
        print(f"  ✓ deleted {args.key}")
        return 0

    return 1


def cmd_email(args: argparse.Namespace) -> int:
    """Poll recruiter email via vault-stored connector credentials."""
    if not KB_ROOT.is_dir():
        print("Career KB missing — run bootstrap first.", file=sys.stderr)
        return 1

    if str(HERMES_PKG) not in sys.path:
        sys.path.insert(0, str(HERMES_PKG))

    from lib.career.email_intake import load_email_connector
    from lib.career.email_poll import run_email_poll

    vault_key = (args.vault_key or "").strip()
    if not vault_key:
        print("--vault-key required (e.g. gmail_oauth, yahoo_imap)", file=sys.stderr)
        return 1

    phrase = (os.environ.get("CAREER_VAULT_PASSPHRASE") or "").strip()
    if not phrase:
        phrase = __import__("getpass").getpass("Vault passphrase: ")

    try:
        connector = load_email_connector(KB_ROOT, vault_key=vault_key, passphrase=phrase)
    except Exception as exc:  # noqa: BLE001 — vault/connector setup errors
        print(f"  ✗ connector: {exc}", file=sys.stderr)
        return 1

    print(f"== email poll: {vault_key} ({connector.provider}) ==")
    try:
        result = run_email_poll(
            connector=connector,
            vault_key=vault_key,
            runtime_dir=RUNTIME,
            intake_dir=GENERATED_INTAKE,
            limit=int(args.limit),
            job_filter=bool(getattr(args, "job_filter", False)),
        )
    except Exception as exc:  # noqa: BLE001 — provider/network errors surfaced to user
        print(f"  ✗ poll failed: {exc}", file=sys.stderr)
        return 1

    rel = Path(result["artifact"]).relative_to(REPO)
    print(f"  ✓ {result['count']} new opportunity(ies) → {rel}")
    print(f"  · fetched={result['fetched_total']} skipped_seen={result['skipped_seen']}")
    print(f"  · latest → {GENERATED_INTAKE.relative_to(REPO)}/email_poll_latest.json")
    return 0


def _import_search_preflight():
    if str(HERMES_PKG) not in sys.path:
        sys.path.insert(0, str(HERMES_PKG))
    from lib.kb.search_preflight import build_search_preflight

    return build_search_preflight


def _import_jobspy_source():
    if str(HERMES_PKG) not in sys.path:
        sys.path.insert(0, str(HERMES_PKG))
    from lib.career.jobspy_source import (
        build_jobspy_envelope,
        fetch_jobspy_opportunities,
        format_jobspy_prompt_block,
        parse_site_list,
        write_jobspy_artifact,
    )

    return {
        "build_jobspy_envelope": build_jobspy_envelope,
        "fetch_jobspy_opportunities": fetch_jobspy_opportunities,
        "format_jobspy_prompt_block": format_jobspy_prompt_block,
        "parse_site_list": parse_site_list,
        "write_jobspy_artifact": write_jobspy_artifact,
    }


def cmd_search(args: argparse.Namespace) -> int:
    """Hello-world: zazu_researcher SEARCH_OPPORTUNITIES via Hermes chat -q."""
    hermes = _hermes_bin()
    if not hermes:
        print("hermes not on PATH.", file=sys.stderr)
        return 1
    if not KB_PUBLIC.is_dir() or not KB_PRIVATE.is_dir():
        print("Career KB missing — run: python agentic/hermes/admin/manage.py bootstrap", file=sys.stderr)
        return 1

    query = (args.query or "").strip()
    if not query:
        print("Provide a search query, e.g. --query 'Software Engineering Manager'", file=sys.stderr)
        return 1

    posted_days = int(getattr(args, "posted_within_days", DEFAULT_SEARCH_POSTED_DAYS))
    if posted_days < 1:
        print("--posted-within-days must be at least 1.", file=sys.stderr)
        return 1

    jobspy_block = ""
    jobspy_path = GENERATED_RESEARCHED / "search_jobspy.json"
    if not getattr(args, "no_jobspy", False):
        jobspy_mod = _import_jobspy_source()
        try:
            sites = jobspy_mod["parse_site_list"](getattr(args, "jobspy_sites", ""))
        except ValueError as exc:
            print(exc, file=sys.stderr)
            return 1
        location = (getattr(args, "location", "") or "").strip() or None
        results_wanted = int(getattr(args, "jobspy_limit", 25))
        print(f"== search jobspy: {', '.join(sites)} ==")
        opportunities, jobspy_errors = jobspy_mod["fetch_jobspy_opportunities"](
            query=query,
            sites=sites,
            location=location,
            posted_within_days=posted_days,
            results_wanted=results_wanted,
            linkedin_fetch_description=getattr(args, "jobspy_descriptions", False),
        )
        envelope = jobspy_mod["build_jobspy_envelope"](
            query=query,
            sites=sites,
            location=location,
            posted_within_days=posted_days,
            opportunities=opportunities,
            errors=jobspy_errors,
        )
        jobspy_mod["write_jobspy_artifact"](jobspy_path, envelope)
        jobspy_block = jobspy_mod["format_jobspy_prompt_block"](envelope)
        print(f"  ✓ {len(opportunities)} opportunity(ies) → {jobspy_path.relative_to(REPO)}")
        for err in jobspy_errors:
            print(f"  · {err}")

    build_search_preflight = _import_search_preflight()
    preflight = build_search_preflight(REPO, query, n_hybrid=8)
    kb_context = preflight.as_prompt_sections()

    print("== search preflight: registry + hybrid RAG + path hits ==")
    print(preflight.path_block[:200] + ("…" if len(preflight.path_block) > 200 else ""))

    jobspy_section = f"\n\n{jobspy_block}\n" if jobspy_block else ""

    prompt = f"""SEARCH_OPPORTUNITIES
criteria: {query}

{kb_context}
{jobspy_section}
**Rules:**
- If registry or path hits show a prior application at a company, do NOT recommend APPLY without a yellow flag citing date, title, and status.
- A different job_id at the same company is still a duplicate employer — flag yellow, not greenfield CONSIDER.
- Cross-check excerpts above and agentic/hermes/.kb/private/application_history/.
- When JobSpy seeds are present, read agentic/hermes/.generated/researched/search_jobspy.json — verify each hit, then supplement with ATS boards (Greenhouse, Lever) via web_search.

Read Career KB:
- agentic/hermes/.kb/_index/catalog.json
- agentic/hermes/.kb/private/prompts/job_fitness.md
- agentic/hermes/.kb/public/master_resume.md, skills.md
- agentic/hermes/.kb/private/career_goals.md, location_preferences.md

Use web_search (and browser when needed) to find job postings matching the criteria that were **posted or reposted within the last {posted_days} days**. Do not cap by hit count — include every qualifying posting you can verify. Skip or flag listings with no visible post date or older than {posted_days} days. Record the posted/reposted date for each hit.
Apply red/yellow flag guardrails from job_fitness.md.
For each hit: title, company, location, posted date, URL, fit note, prior-application check (registry + paths + excerpts).
Save a summary to agentic/hermes/.generated/researched/search_latest.md
"""

    out_path = GENERATED_RESEARCHED / "search_latest.md"
    GENERATED.mkdir(parents=True, exist_ok=True)
    GENERATED_RESEARCHED.mkdir(parents=True, exist_ok=True)

    print(f"== search: zazu_researcher — {query!r} ==")
    print(f"  posted within: {posted_days} day(s)")
    print(f"  KB: {KB_ROOT.relative_to(REPO)}")
    print(f"  Output target: {out_path.relative_to(REPO)}")
    print("$ hermes -p zazu_researcher chat -q ...")

    proc = subprocess.run(
        [hermes, "-p", "zazu_researcher", "chat", "-q", prompt],
        cwd=REPO,
        text=True,
    )
    if proc.returncode != 0:
        return proc.returncode
    if out_path.is_file():
        print(f"\n  ✓ wrote {out_path.relative_to(REPO)}")
    else:
        print("\n  · run finished — check hermes output (agent may not have written file yet)")
    return 0


def cmd_hermes(args: argparse.Namespace) -> int:
    argv = list(args.hermes_args or ["profile", "list"])
    if argv and argv[0] == "--":
        argv = argv[1:]
    if not argv:
        argv = ["profile", "list"]
    hermes = _hermes_bin()
    if not hermes:
        print("hermes not on PATH.", file=sys.stderr)
        return 1
    print(f"$ hermes {' '.join(argv)}")
    return subprocess.run([hermes, *argv], cwd=REPO).returncode


def main(argv: list[str] | None = None) -> int:
    _load_dotenv()
    parser = argparse.ArgumentParser(description="Project Career Zazu — Hermes admin")
    sub = parser.add_subparsers(dest="command")

    p_boot = sub.add_parser("bootstrap", help="venv + KB + .runtime + Hermes setup")
    p_boot.add_argument("--skip-setup", action="store_true")
    p_boot.add_argument(
        "--force-kb",
        action="store_true",
        help="overwrite .kb/public and .kb/private from scaffold (destructive)",
    )
    p_boot.add_argument(
        "--extract-kb",
        action="store_true",
        help="after bootstrap: deep extract vault, ChromaDB RAG at .kb/index_db, organize markdown",
    )
    p_boot.add_argument(
        "--remote",
        action="store_true",
        help="Ollama on remote LAN host (ignored if .env sets OLLAMA_BASE_URL)",
    )
    p_boot.set_defaults(func=cmd_bootstrap, remote=False)

    p_deps = sub.add_parser("install-deps", help="pip install requirements into .venv")
    p_deps.add_argument(
        "--kb-extract",
        action="store_true",
        help="also install requirements-kb-extract.txt (unstructured + OCR)",
    )
    p_deps.add_argument(
        "--email",
        action="store_true",
        help="also install requirements-email.txt (Gmail/Outlook email poll)",
    )
    p_deps.set_defaults(func=cmd_install_deps, kb_extract=False, email=False)

    p_setup = sub.add_parser("setup", help="Ollama + three role profiles")
    p_setup.add_argument("--dry-run", action="store_true")
    p_setup.add_argument(
        "--remote",
        action="store_true",
        help="Ollama on remote LAN host (ignored if .env sets OLLAMA_BASE_URL)",
    )
    p_setup.set_defaults(func=cmd_setup, remote=False)

    p_search = sub.add_parser("search", help="hello-world job search via zazu_researcher")
    p_search.add_argument(
        "--query",
        "-q",
        required=True,
        help='e.g. "Software Engineering Manager"',
    )
    p_search.add_argument(
        "--posted-within-days",
        type=int,
        default=DEFAULT_SEARCH_POSTED_DAYS,
        metavar="N",
        help=f"only include postings/reposts from the last N days (default: {DEFAULT_SEARCH_POSTED_DAYS})",
    )
    p_search.add_argument(
        "--location",
        default="",
        help="location filter for JobSpy aggregator (e.g. 'Seattle, WA')",
    )
    p_search.add_argument(
        "--jobspy-sites",
        default="linkedin,indeed,google",
        help="comma-separated JobSpy boards (default: linkedin,indeed,google)",
    )
    p_search.add_argument(
        "--jobspy-limit",
        type=int,
        default=25,
        help="max JobSpy results per site (default: 25)",
    )
    p_search.add_argument(
        "--jobspy-descriptions",
        action="store_true",
        help="fetch full LinkedIn descriptions via JobSpy (slower, more requests)",
    )
    p_search.add_argument(
        "--no-jobspy",
        action="store_true",
        help="skip JobSpy pre-fetch; researcher uses web_search only",
    )
    p_search.set_defaults(func=cmd_search, no_jobspy=False, jobspy_descriptions=False)

    p_apply = sub.add_parser(
        "apply",
        help="write Application Coach DOCX triplet to .generated/proposals/<run>/",
    )
    p_apply.add_argument("--from-search", action="store_true", help="use first CONSIDER role from search_latest.md")
    p_apply.add_argument(
        "--all-from-search",
        action="store_true",
        help="apply to every APPLY/CONSIDER role in search_latest.md (implies --force per role)",
    )
    p_apply.add_argument("--company", help="employer name")
    p_apply.add_argument("--title", help="job title")
    p_apply.add_argument("--job-id", help="ATS requisition id (default: parsed from --url)")
    p_apply.add_argument("--url", help="job posting URL")
    p_apply.add_argument("--job-date", help="YYYYMMDD posting/evaluation date (default: today)")
    p_apply.add_argument("--run-prefix", help="proposals subdir YYYYMMDDHHmmss (default: now)")
    p_apply.add_argument(
        "--coach",
        action="store_true",
        help="after writing DOCX, invoke zazu_coach to customize content",
    )
    p_apply.add_argument(
        "--force",
        action="store_true",
        help="apply even when registry shows prior application at this company",
    )
    p_apply.set_defaults(func=cmd_apply, from_search=False, coach=False, force=False)

    p_apps = sub.add_parser("applications", help="SQLite application registry (applied roles & outcomes)")
    apps_sub = p_apps.add_subparsers(dest="applications_cmd", required=True)

    p_apps_list = apps_sub.add_parser("list", help="list recorded applications")
    p_apps_list.add_argument("--limit", type=int, default=100)
    p_apps_list.set_defaults(func=cmd_applications, applications_cmd="list")

    p_apps_import = apps_sub.add_parser(
        "import-vault",
        help="import company folders from .kb/private/application_history/",
    )
    p_apps_import.set_defaults(func=cmd_applications, applications_cmd="import-vault")

    p_apps_reg = apps_sub.add_parser(
        "register",
        help="record external ATS application (e.g. iCIMS, Eightfold, Greenhouse)",
    )
    p_apps_reg.add_argument("--company", required=True)
    p_apps_reg.add_argument("--title", required=True, help="job title")
    p_apps_reg.add_argument("--job-id", default="", help="employer requisition / job number")
    p_apps_reg.add_argument("--url", default="", help="posting or dashboard URL")
    p_apps_reg.add_argument("--ats", default="", help="ATS label for notes (e.g. icims, eightfold)")
    p_apps_reg.add_argument(
        "--status",
        default="applied",
        choices=["considered", "applied", "interviewing", "offered", "rejected", "withdrawn", "skipped"],
    )
    p_apps_reg.add_argument("--job-date", default="", help="YYYYMMDD posting or apply date")
    p_apps_reg.add_argument("--notes", default="")
    p_apps_reg.add_argument("--topics", default="", help="comma-separated tags for ANALYZE")
    p_apps_reg.set_defaults(func=cmd_applications, applications_cmd="register")

    p_apps_out = apps_sub.add_parser("record-outcome", help="update status / outcome")
    p_apps_out.add_argument("--opportunity-id", help="opp:… id")
    p_apps_out.add_argument("--company", help="match latest row for company")
    p_apps_out.add_argument(
        "--status",
        required=True,
        choices=["considered", "applied", "interviewing", "offered", "rejected", "withdrawn", "skipped"],
    )
    p_apps_out.add_argument("--notes", default="")
    p_apps_out.add_argument(
        "--topics",
        default="",
        help="comma-separated topic tags (e.g. mcp,ai_platform) for ANALYZE",
    )
    p_apps_out.set_defaults(func=cmd_applications, applications_cmd="record-outcome")

    p_career = sub.add_parser("career", help="Career Zazu orchestration (CKM front desk)")
    career_sub = p_career.add_subparsers(dest="career_cmd", required=True)

    p_career_status = career_sub.add_parser("status", help="board + artifacts + registry snapshot")
    p_career_status.add_argument("--json", action="store_true", help="machine-readable output")
    p_career_status.set_defaults(func=cmd_career, career_cmd="status")

    p_career_topics = career_sub.add_parser("topics", help="per-topic application response rates")
    p_career_topics.add_argument("--json", action="store_true")
    p_career_topics.set_defaults(func=cmd_career, career_cmd="topics")

    p_career_learn = career_sub.add_parser("learning", help="recent learning events with trace refs")
    p_career_learn.add_argument("--limit", type=int, default=20)
    p_career_learn.add_argument("--json", action="store_true")
    p_career_learn.set_defaults(func=cmd_career, career_cmd="learning")

    p_secrets = sub.add_parser("secrets", help="encrypted credential vault (.kb/private/secrets/)")
    secrets_sub = p_secrets.add_subparsers(dest="secrets_cmd", required=True)

    p_sec_unlock = secrets_sub.add_parser("unlock", help="verify passphrase (no values printed)")
    p_sec_unlock.set_defaults(func=cmd_secrets, secrets_cmd="unlock")

    p_sec_list = secrets_sub.add_parser("list", help="list entry keys and types only")
    p_sec_list.add_argument("--json", action="store_true")
    p_sec_list.set_defaults(func=cmd_secrets, secrets_cmd="list")

    p_sec_set = secrets_sub.add_parser("set", help="store encrypted entry from JSON file")
    p_sec_set.add_argument("key", help="entry key, e.g. gmail_oauth")
    p_sec_set.add_argument("--type", required=True, dest="type", help="oauth_gmail | oauth_outlook | …")
    p_sec_set.add_argument("--from-json", required=True, help="path to JSON object with secret fields")
    p_sec_set.set_defaults(func=cmd_secrets, secrets_cmd="set")

    p_sec_del = secrets_sub.add_parser("delete", help="remove an entry")
    p_sec_del.add_argument("key", help="entry key to delete")
    p_sec_del.set_defaults(func=cmd_secrets, secrets_cmd="delete")

    p_email = sub.add_parser("email", help="recruiter email intake (vault credentials)")
    email_sub = p_email.add_subparsers(dest="email_cmd", required=True)

    p_email_poll = email_sub.add_parser("poll", help="fetch unread mail → intake opportunities")
    p_email_poll.add_argument(
        "--vault-key",
        required=True,
        help="secrets vault entry (e.g. gmail_oauth, outlook_oauth, yahoo_imap)",
    )
    p_email_poll.add_argument("--limit", type=int, default=20, help="max unread messages to fetch")
    p_email_poll.add_argument(
        "--job-filter",
        action="store_true",
        help="keep only messages with job-board URLs or recruiter-like subjects",
    )
    p_email_poll.set_defaults(func=cmd_email, email_cmd="poll")

    p_kb_scan = sub.add_parser("kb-scan", help="scan .kb/ → catalog + classification")
    p_kb_scan.add_argument(
        "--agent",
        action="store_true",
        help="invoke zazu_knowledge_manager to review scan results and write kb_scan_latest.md",
    )
    p_kb_scan.add_argument(
        "--force-extract",
        action="store_true",
        help="re-run text extraction even when file hash unchanged",
    )
    p_kb_scan.set_defaults(func=cmd_kb_scan)

    p_kb_extract = sub.add_parser(
        "kb-extract",
        help="deep extract .kb/, ChromaDB RAG at index_db/, organize canonical markdown",
    )
    p_kb_extract.add_argument(
        "--force-organize",
        action="store_true",
        help="overwrite public/*.md and private flags even if already populated",
    )
    p_kb_extract.add_argument(
        "--skip-rag",
        action="store_true",
        help="skip Ollama embeddings + ChromaDB (chunk + BM25 corpus only)",
    )
    p_kb_extract.add_argument(
        "--skip-registry",
        action="store_true",
        help="skip SQLite import from application_history/ folders",
    )
    p_kb_extract.set_defaults(func=cmd_kb_extract, force_organize=False, skip_rag=False, skip_registry=False)

    p_status = sub.add_parser("status", help="show bootstrap state")
    p_status.set_defaults(func=cmd_status)

    p_nuke = sub.add_parser("nuke", help="clear agentic/hermes/.runtime")
    p_nuke.add_argument("--yes", action="store_true")
    p_nuke.set_defaults(func=cmd_nuke)

    p_hermes = sub.add_parser("hermes", help="passthrough to upstream hermes CLI")
    p_hermes.add_argument("hermes_args", nargs=argparse.REMAINDER)
    p_hermes.set_defaults(func=cmd_hermes)

    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
