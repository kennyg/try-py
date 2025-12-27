# try-py

Ephemeral workspace manager - organize your experimental projects.

Python port of [try](https://github.com/your-repo/try).

## Installation

```bash
uv pip install -e .
```

## Usage

Add to your shell config:

```bash
# bash/zsh
eval "$(try init ~/src/tries)"

# fish
eval (try init ~/src/tries | string collect)
```

Then use `try` to manage your experimental directories:

```bash
try                    # Interactive selector
try project            # Filter with initial query
try clone <git-url>    # Clone repo into dated directory
try worktree <name>    # Create git worktree
```
