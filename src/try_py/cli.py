"""CLI entry point using Click."""

from __future__ import annotations

import os
import re
import sys
from datetime import datetime

import click

from . import __version__
from .selector import TrySelector
from .shell import (
    emit_script,
    generate_init_script,
    script_cd,
    script_clone,
    script_delete,
    script_mkdir_cd,
    script_worktree,
)
from .ui import UI


def parse_git_uri(uri: str) -> dict | None:
    """Parse git URI into components."""
    uri = re.sub(r"\.git$", "", uri)

    # HTTPS GitHub
    match = re.match(r"^https?://github\.com/([^/]+)/([^/]+)", uri)
    if match:
        return {"user": match.group(1), "repo": match.group(2), "host": "github.com"}

    # SSH GitHub
    match = re.match(r"^git@github\.com:([^/]+)/([^/]+)", uri)
    if match:
        return {"user": match.group(1), "repo": match.group(2), "host": "github.com"}

    # Other HTTPS hosts
    match = re.match(r"^https?://([^/]+)/([^/]+)/([^/]+)", uri)
    if match:
        return {"user": match.group(2), "repo": match.group(3), "host": match.group(1)}

    # Other SSH hosts
    match = re.match(r"^git@([^:]+):([^/]+)/([^/]+)", uri)
    if match:
        return {"user": match.group(2), "repo": match.group(3), "host": match.group(1)}

    return None


def generate_clone_directory_name(git_uri: str, custom_name: str | None = None) -> str | None:
    """Generate dated directory name for clone."""
    if custom_name:
        return custom_name

    parsed = parse_git_uri(git_uri)
    if not parsed:
        return None

    date_prefix = datetime.now().strftime("%Y-%m-%d")
    return f"{date_prefix}-{parsed['user']}-{parsed['repo']}"


def is_git_uri(arg: str | None) -> bool:
    """Check if argument is a git URI."""
    if not arg:
        return False
    return bool(
        re.match(r"^(https?://|git@)", arg)
        or "github.com" in arg
        or "gitlab.com" in arg
        or arg.endswith(".git")
    )


def unique_dir_name(tries_path: str, dir_name: str) -> str:
    """Return unique directory name by appending -2, -3, etc."""
    candidate = dir_name
    i = 2
    while os.path.exists(os.path.join(tries_path, candidate)):
        candidate = f"{dir_name}-{i}"
        i += 1
    return candidate


def resolve_unique_name_with_versioning(tries_path: str, date_prefix: str, base: str) -> str:
    """Resolve unique name with smart versioning."""
    initial = f"{date_prefix}-{base}"
    if not os.path.exists(os.path.join(tries_path, initial)):
        return base

    match = re.match(r"^(.*?)(\d+)$", base)
    if match:
        stem, n = match.group(1), int(match.group(2))
        candidate_num = n + 1
        while True:
            candidate_base = f"{stem}{candidate_num}"
            if not os.path.exists(os.path.join(tries_path, f"{date_prefix}-{candidate_base}")):
                return candidate_base
            candidate_num += 1
    else:
        full = unique_dir_name(tries_path, f"{date_prefix}-{base}")
        return full.replace(f"{date_prefix}-", "", 1)


def parse_test_keys(spec: str | None) -> list[str] | None:
    """Parse test key specification."""
    if not spec:
        return None

    use_token_mode = "," in spec or re.match(r"^[A-Z\-]+$", spec)

    if use_token_mode:
        tokens = re.split(r",\s*", spec)
        keys = []
        for tok in tokens:
            up = tok.upper()
            key_map = {
                "UP": "\033[A",
                "DOWN": "\033[B",
                "LEFT": "\033[D",
                "RIGHT": "\033[C",
                "ENTER": "\r",
                "ESC": "\033",
                "BACKSPACE": "\x7f",
                "CTRL-A": "\x01",
                "CTRLA": "\x01",
                "CTRL-B": "\x02",
                "CTRLB": "\x02",
                "CTRL-D": "\x04",
                "CTRLD": "\x04",
                "CTRL-E": "\x05",
                "CTRLE": "\x05",
                "CTRL-F": "\x06",
                "CTRLF": "\x06",
                "CTRL-H": "\x08",
                "CTRLH": "\x08",
                "CTRL-K": "\x0b",
                "CTRLK": "\x0b",
                "CTRL-N": "\x0e",
                "CTRLN": "\x0e",
                "CTRL-P": "\x10",
                "CTRLP": "\x10",
                "CTRL-W": "\x17",
                "CTRLW": "\x17",
            }
            if up in key_map:
                keys.append(key_map[up])
            elif up.startswith("TYPE="):
                for ch in up[5:]:
                    keys.append(ch)
            elif len(tok) == 1:
                keys.append(tok)
        return keys
    else:
        keys = []
        i = 0
        while i < len(spec):
            if spec[i] == "\033" and i + 2 < len(spec) and spec[i + 1] == "[":
                keys.append(spec[i : i + 3])
                i += 3
            else:
                keys.append(spec[i])
                i += 1
        return keys


def worktree_path(tries_path: str, repo_dir: str, custom_name: str | None) -> str:
    """Generate worktree path."""
    if custom_name and custom_name.strip():
        base = re.sub(r"\s+", "-", custom_name)
    else:
        try:
            base = os.path.basename(os.path.realpath(repo_dir))
        except OSError:
            base = os.path.basename(repo_dir)

    date_prefix = datetime.now().strftime("%Y-%m-%d")
    base = resolve_unique_name_with_versioning(tries_path, date_prefix, base)
    return os.path.join(tries_path, f"{date_prefix}-{base}")


def cmd_clone(args: list[str], tries_path: str) -> list[str]:
    """Handle clone command."""
    if not args:
        click.echo("Error: git URI required for clone command", err=True)
        click.echo("Usage: try clone <git-uri> [name]", err=True)
        sys.exit(1)

    git_uri = args[0]
    custom_name = args[1] if len(args) > 1 else None

    dir_name = generate_clone_directory_name(git_uri, custom_name)
    if not dir_name:
        click.echo(f"Error: Unable to parse git URI: {git_uri}", err=True)
        sys.exit(1)

    return script_clone(os.path.join(tries_path, dir_name), git_uri)


def cmd_cd(
    args: list[str],
    tries_path: str,
    and_type: str | None,
    and_exit: bool,
    and_keys: list[str] | None,
    and_confirm: str | None,
) -> list[str] | None:
    """Handle cd command (main selector)."""
    if args and args[0] == "clone":
        return cmd_clone(args[1:], tries_path)

    # Handle try . [name] and try ./path [name]
    if args and args[0].startswith("."):
        path_arg = args[0]
        custom = " ".join(args[1:]) if len(args) > 1 else ""
        repo_dir = os.path.abspath(path_arg)

        if path_arg == "." and not custom.strip():
            click.echo("Error: 'try .' requires a name argument", err=True)
            click.echo("Usage: try . <name>", err=True)
            sys.exit(1)

        base = re.sub(r"\s+", "-", custom) if custom.strip() else os.path.basename(repo_dir)
        date_prefix = datetime.now().strftime("%Y-%m-%d")
        base = resolve_unique_name_with_versioning(tries_path, date_prefix, base)
        full_path = os.path.join(tries_path, f"{date_prefix}-{base}")

        if os.path.isdir(os.path.join(repo_dir, ".git")):
            return script_worktree(full_path, repo_dir)
        else:
            return script_mkdir_cd(full_path)

    search_term = " ".join(args)

    # Git URL shorthand
    first = search_term.split()[0] if search_term.split() else ""
    if is_git_uri(first):
        parts = search_term.split(None, 1)
        git_uri = parts[0]
        custom_name = parts[1] if len(parts) > 1 else None

        dir_name = generate_clone_directory_name(git_uri, custom_name)
        if not dir_name:
            click.echo(f"Error: Unable to parse git URI: {git_uri}", err=True)
            sys.exit(1)

        return script_clone(os.path.join(tries_path, dir_name), git_uri)

    # Interactive selector
    selector = TrySelector(
        search_term,
        base_path=tries_path,
        initial_input=and_type,
        test_render_once=and_exit,
        test_no_cls=and_exit or (and_keys is not None and len(and_keys) > 0),
        test_keys=and_keys,
        test_confirm=and_confirm,
    )

    result = selector.run()
    if not result:
        return None

    if result.get("type") == "delete":
        return script_delete(result["paths"], result["base_path"])
    elif result.get("type") == "mkdir":
        return script_mkdir_cd(result["path"])
    else:
        return script_cd(result["path"])


HELP_TEXT = """{h1}try{reset} v%s - ephemeral workspace manager

To use try, add to your shell config:

  {dim}# bash/zsh (~/.bashrc or ~/.zshrc){/fg}
  {b}eval "$(try init ~/src/tries)"{/b}

  {dim}# fish (~/.config/fish/config.fish){/fg}
  {b}eval (try init ~/src/tries | string collect){/b}

{h2}Usage:{reset}
  try [query]           Interactive directory selector
  try clone <url>       Clone repo into dated directory
  try worktree <name>   Create worktree from current git repo
  try --help            Show this help

{h2}Commands:{reset}
  init [path]           Output shell function definition
  clone <url> [name]    Clone git repo into date-prefixed directory
  worktree <name>       Create worktree in dated directory

{h2}Examples:{reset}
  try                   Open interactive selector
  try project           Selector with initial filter
  try clone https://github.com/user/repo
  try worktree feature-branch

{h2}Manual mode (without alias):{reset}
  try exec [query]      Output shell script to eval

{h2}Defaults:{reset}
  Default path: {dim}~/src/tries{/fg}
  Current: {dim}%s{/fg}
""" % (__version__, TrySelector.TRY_PATH)


def print_version(ctx, param, value):
    """Print version in expected format."""
    if not value or ctx.resilient_parsing:
        return
    click.echo(f"try {__version__}")
    ctx.exit()


def print_help_flag(ctx, param, value):
    """Print help for -h flag."""
    if not value or ctx.resilient_parsing:
        return
    out = UI.expand_tokens(HELP_TEXT)
    if sys.stdout.isatty() or "{" in out:
        pass
    else:
        out = re.sub(r"\{.*?\}", "", HELP_TEXT)
    click.echo(out, nl=False)
    ctx.exit(0)


@click.command(context_settings={"ignore_unknown_options": True, "allow_extra_args": True})
@click.option("--path", "tries_path", default=None, help="Override tries directory")
@click.option("--no-colors", is_flag=True, help="Disable ANSI colors")
@click.option("--no-expand-tokens", is_flag=True, hidden=True)
@click.option("--and-type", default=None, hidden=True)
@click.option("--and-exit", is_flag=True, hidden=True)
@click.option("--and-keys", default=None, hidden=True)
@click.option("--and-confirm", default=None, hidden=True)
@click.option("-v", "--version", is_flag=True, callback=print_version, expose_value=False, is_eager=True)
@click.option("-h", "--help", "show_help", is_flag=True, callback=print_help_flag, expose_value=False, is_eager=True)
@click.pass_context
def main(
    ctx: click.Context,
    tries_path: str | None,
    no_colors: bool,
    no_expand_tokens: bool,
    and_type: str | None,
    and_exit: bool,
    and_keys: str | None,
    and_confirm: str | None,
):
    """try - ephemeral workspace manager"""
    # Handle color settings
    if no_expand_tokens:
        UI.disable_token_expansion()

    if no_colors or os.environ.get("NO_COLOR"):
        UI.disable_colors()

    # Enable colors in test mode
    if and_exit or and_keys:
        UI.force_colors()

    # Resolve tries path
    path = os.path.expanduser(tries_path or TrySelector.TRY_PATH)

    # Parse test keys
    parsed_keys = parse_test_keys(and_keys)

    # Get remaining args
    args = list(ctx.args)

    # No command = launch selector (matches help text: "try [query]")
    if not args:
        script = cmd_cd([], path, and_type, and_exit, parsed_keys, and_confirm)
        if script:
            emit_script(script)
            sys.exit(0)
        else:
            print("Cancelled.")
            sys.exit(1)

    command = args[0]

    if command == "clone":
        script = cmd_clone(args[1:], path)
        emit_script(script)
        sys.exit(0)

    elif command == "init":
        init_path = args[1] if len(args) > 1 and args[1].startswith("/") else path
        init_path = os.path.expanduser(init_path)
        script_path = os.path.abspath(sys.argv[0])
        print(generate_init_script(script_path, init_path))
        sys.exit(0)

    elif command == "exec":
        sub = args[1] if len(args) > 1 else None

        if sub == "clone":
            script = cmd_clone(args[2:], path)
            emit_script(script)

        elif sub == "worktree":
            repo = args[2] if len(args) > 2 else None
            repo_dir = os.path.abspath(repo) if repo and repo != "dir" else os.getcwd()
            custom = " ".join(args[3:]) if len(args) > 3 else None
            full_path = worktree_path(path, repo_dir, custom)
            script = script_worktree(full_path, None if repo_dir == os.getcwd() else repo_dir)
            emit_script(script)

        elif sub == "cd":
            script = cmd_cd(args[2:], path, and_type, and_exit, parsed_keys, and_confirm)
            if script:
                emit_script(script)
                sys.exit(0)
            else:
                print("Cancelled.")
                sys.exit(1)

        else:
            script = cmd_cd(args[1:], path, and_type, and_exit, parsed_keys, and_confirm)
            if script:
                emit_script(script)
                sys.exit(0)
            else:
                print("Cancelled.")
                sys.exit(1)

    elif command == "worktree":
        repo = args[1] if len(args) > 1 else None
        repo_dir = os.path.abspath(repo) if repo and repo != "dir" else os.getcwd()
        custom = " ".join(args[2:]) if len(args) > 2 else None
        full_path = worktree_path(path, repo_dir, custom)
        script = script_worktree(full_path, None if repo_dir == os.getcwd() else repo_dir)
        emit_script(script)
        sys.exit(0)

    else:
        # Default: try [query]
        script = cmd_cd(args, path, and_type, and_exit, parsed_keys, and_confirm)
        if script:
            emit_script(script)
            sys.exit(0)
        else:
            print("Cancelled.")
            sys.exit(1)


if __name__ == "__main__":
    main()
