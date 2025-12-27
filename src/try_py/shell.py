"""Shell script emission for parent shell integration."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from .ui import UI

SCRIPT_WARNING = "# if you can read this, you didn't launch try from an alias. run try --help."


def q(s: str) -> str:
    """Shell-quote a string."""
    return "'" + s.replace("'", "'\"'\"'") + "'"


def emit_script(cmds: list[str]) -> None:
    """Format and print commands for shell eval."""
    print(SCRIPT_WARNING)
    for i, cmd in enumerate(cmds):
        if i == 0:
            sys.stdout.write(cmd)
        else:
            sys.stdout.write(f"  {cmd}")

        if i < len(cmds) - 1:
            print(" && \\")
        else:
            print()


def script_cd(path: str) -> list[str]:
    """Generate commands to touch and cd to a path."""
    return [f"touch {q(path)}", f"cd {q(path)}"]


def script_mkdir_cd(path: str) -> list[str]:
    """Generate commands to mkdir and cd."""
    return [f"mkdir -p {q(path)}", *script_cd(path)]


def script_clone(path: str, uri: str) -> list[str]:
    """Generate commands to clone a git repo."""
    msg = UI.expand_tokens(f"Using {{b}}git clone{{/b}} to create this trial from {uri}.")
    return [
        f"mkdir -p {q(path)}",
        f"echo {q(msg)}",
        f"git clone '{uri}' {q(path)}",
        *script_cd(path),
    ]


def script_worktree(path: str, repo: str | None = None) -> list[str]:
    """Generate commands to create a git worktree."""
    if repo:
        r = q(repo)
        worktree_cmd = (
            f"/usr/bin/env sh -c 'if git -C {r} rev-parse --is-inside-work-tree >/dev/null 2>&1; "
            f"then repo=$(git -C {r} rev-parse --show-toplevel); "
            f'git -C "$repo" worktree add --detach {q(path)} >/dev/null 2>&1 || true; fi; exit 0\''
        )
        src = repo
    else:
        worktree_cmd = (
            "/usr/bin/env sh -c 'if git rev-parse --is-inside-work-tree >/dev/null 2>&1; "
            f"then repo=$(git rev-parse --show-toplevel); "
            f'git -C "$repo" worktree add --detach {q(path)} >/dev/null 2>&1 || true; fi; exit 0\''
        )
        src = str(Path.cwd())

    msg = UI.expand_tokens(f"Using {{b}}git worktree{{/b}} to create this trial from {src}.")
    return [f"mkdir -p {q(path)}", f"echo {q(msg)}", worktree_cmd, *script_cd(path)]


def script_delete(paths: list[dict], base_path: str) -> list[str]:
    """Generate commands to delete directories."""
    cmds = [f"cd {q(base_path)}"]
    for item in paths:
        basename = item["basename"]
        cmds.append(f"[[ -d {q(basename)} ]] && rm -rf {q(basename)}")
    cmds.append(f'( cd {q(str(Path.cwd()))} 2>/dev/null || cd "$HOME" )')
    return cmds


def is_fish() -> bool:
    """Check if current shell is fish."""
    shell = os.environ.get("SHELL", "")
    return "fish" in shell


def generate_init_script(script_path: str, tries_path: str) -> str:
    """Generate shell initialization script."""
    path_arg = f" --path '{tries_path}'" if tries_path else ""

    # Get the directory containing the script (the venv bin dir)
    script_dir = Path(script_path).parent
    # Use uv run from the project directory, or fall back to direct venv python
    venv_python = script_dir / "python"

    if is_fish():
        return f"""function try
  set -l out ('{venv_python}' '{script_path}' exec{path_arg} $argv 2>/dev/tty | string collect)
  if test $status -eq 0
    eval $out
  else
    echo $out
  end
end
"""
    else:
        return f"""try() {{
  local out
  out=$('{venv_python}' '{script_path}' exec{path_arg} "$@" 2>/dev/tty)
  if [ $? -eq 0 ]; then
    eval "$out"
  else
    echo "$out"
  fi
}}
"""
