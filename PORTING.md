# Porting Guide: try - Ephemeral Workspace Manager

This document provides comprehensive documentation for porting the `try` workspace manager to new languages. It covers the original Ruby implementation's features, the architecture, and critical behaviors that must be matched exactly.

---

## Table of Contents

1. [Original try Project Features](#original-try-project-features)
2. [Feature Comparison Matrix](#feature-comparison-matrix)
3. [Architecture Overview](#architecture-overview)
4. [Test Compatibility](#test-compatibility)
5. [Porting Checklist](#porting-checklist)

---

## Original try Project Features

### Core Functionality

The `try` tool is an ephemeral workspace manager that organizes project directories with date-prefixed naming (`YYYY-MM-DD-name`). It provides:

1. **Interactive Directory Selector (TUI)**
   - Fuzzy search with real-time filtering
   - Keyboard navigation (arrow keys, Emacs-style bindings)
   - Score-based ranking with recency bonuses
   - Scrolling viewport for large directory lists
   - Double-buffered rendering to prevent flicker

2. **Shell Integration**
   - `init` command outputs shell wrapper functions
   - Supports bash, zsh, and fish shells
   - Wrapper evaluates output to change parent shell's directory

3. **Git Integration**
   - `clone` command clones repos into dated directories
   - `worktree` command creates git worktrees
   - Smart URL parsing for GitHub, GitLab, SSH URLs

4. **Directory Management**
   - Create new directories with date prefix
   - Batch delete with confirmation (type "YES")
   - Touch mtime on selection (for recency sorting)

### CLI Commands

| Command | Description |
|---------|-------------|
| `try` | Show help (no args) |
| `try [query]` | Interactive selector with optional filter |
| `try init [path]` | Output shell wrapper function |
| `try clone <url> [name]` | Clone git repo into dated directory |
| `try worktree <name>` | Create git worktree |
| `try exec [cmd]` | Internal: output script for shell eval |
| `try . <name>` | Create worktree from current repo |

### CLI Options

| Option | Description |
|--------|-------------|
| `--path <dir>` | Override tries directory |
| `--help`, `-h` | Show help text |
| `--version`, `-v` | Show version number |
| `--no-colors` | Disable ANSI colors |
| `NO_COLOR` env | Disable colors (standard) |

### Test-Only Options (Internal)

| Option | Description |
|--------|-------------|
| `--and-exit` | Render TUI once and exit |
| `--and-keys=<seq>` | Inject key sequence |
| `--and-type=<text>` | Set initial input buffer |
| `--and-confirm=<text>` | Auto-confirm for delete |
| `--no-expand-tokens` | Output raw tokens |

### Keyboard Controls

#### Navigation
| Key | Action |
|-----|--------|
| `Up` / `Ctrl-P` | Move selection up |
| `Down` / `Ctrl-N` | Move selection down |
| `Enter` | Select current entry |
| `Esc` / `Ctrl-C` | Cancel/exit |

#### Line Editing
| Key | Action |
|-----|--------|
| `Ctrl-A` | Beginning of line |
| `Ctrl-E` | End of line |
| `Ctrl-B` | Backward one character |
| `Ctrl-F` | Forward one character |
| `Backspace` / `Ctrl-H` | Delete char before cursor |
| `Ctrl-K` | Kill to end of line |
| `Ctrl-W` | Delete word backward |

#### Delete Mode
| Key | Action |
|-----|--------|
| `Ctrl-D` | Toggle mark for deletion |
| `Enter` (in delete mode) | Show confirmation |
| `Esc` (in delete mode) | Exit delete mode |

---

## Feature Comparison Matrix

### Ruby vs Python Implementation Status

| Feature | Ruby | Python | Notes |
|---------|:----:|:------:|-------|
| **CLI** | | | |
| `--help` / `-h` | Yes | Yes | |
| `--version` / `-v` | Yes | Yes | Format: `try X.Y.Z` |
| `--path <dir>` | Yes | Yes | Override tries directory |
| `--no-colors` | Yes | Yes | |
| `NO_COLOR` env | Yes | Yes | |
| `init` command | Yes | Yes | |
| `clone` command | Yes | Yes | |
| `worktree` command | Yes | Yes | |
| `exec` subcommand | Yes | Yes | |
| `try .` shorthand | Yes | Yes | |
| **TUI** | | | |
| Double buffering | Yes | Yes | |
| Token system | Yes | Yes | |
| Fuzzy matching | Yes | Yes | |
| Score-based ranking | Yes | Yes | |
| Recency bonus | Yes | Yes | |
| Date prefix bonus | Yes | Yes | |
| Navigation (arrows) | Yes | Yes | |
| Navigation (Ctrl-P/N) | Yes | Yes | |
| Line editing | Yes | Yes | |
| Scroll viewport | Yes | Yes | |
| Create new entry | Yes | Yes | |
| Delete mode | Yes | Yes | |
| Batch delete | Yes | Yes | |
| SIGWINCH handling | Yes | Yes | Terminal resize |
| **Shell Integration** | | | |
| Bash/Zsh wrapper | Yes | Yes | |
| Fish wrapper | Yes | Yes | |
| Script emission | Yes | Yes | |
| Quote escaping | Yes | Yes | |
| **Testing** | | | |
| `--and-exit` | Yes | Yes | |
| `--and-keys` | Yes | Yes | |
| `--and-type` | Yes | Yes | |
| `--and-confirm` | Yes | Yes | |
| `TRY_WIDTH` env | Yes | Yes | |
| `TRY_HEIGHT` env | Yes | Yes | |

### Implementation Differences

| Aspect | Ruby | Python |
|--------|------|--------|
| Dependencies | None (stdlib only) | click, rich (optional) |
| Terminal handling | `IO.console`, `STDERR.raw` | `termios`, `tty` module |
| Key reading | `STDIN.getc`, `read_nonblock` | `select`, raw mode read |
| Size detection | `tput` command | `shutil.get_terminal_size` |
| Class structure | Module + Class | Classes with `@classmethod` |

---

## Architecture Overview

### Module Structure

```
try/
  try.rb          # Single-file Ruby implementation

try-py/
  src/try_py/
    __init__.py   # Package version
    cli.py        # CLI routing (Click-based)
    ui.py         # Token system, double buffering
    fuzzy.py      # Scoring algorithm
    selector.py   # TUI state machine
    shell.py      # Script generation
```

### UI Module

The UI module provides a declarative token-based formatting system with double buffering for flicker-free rendering.

#### Token System

Tokens are placeholders wrapped in curly braces that expand to ANSI escape sequences:

```
TOKEN_MAP = {
    # Text formatting
    "{b}":        "\033[1;33m",      # Bold + Yellow
    "{/b}":       "\033[22m\033[39m", # Reset bold + foreground
    "{dim}":      "\033[90m",         # Gray (bright black)
    "{text}":     "\033[0m\033[39m",  # Full reset
    "{reset}":    "\033[0m\033[39m\033[49m",  # Complete reset
    "{/fg}":      "\033[39m",         # Reset foreground only

    # Headings
    "{h1}":       "\033[1;38;5;208m", # Bold + Orange (256-color)
    "{h2}":       "\033[1;34m",       # Bold + Blue

    # Selection
    "{section}":  "\033[1m",          # Bold
    "{/section}": "\033[0m",          # Full reset

    # Deletion
    "{strike}":   "\033[48;5;52m",    # Dark red background
    "{/strike}":  "\033[49m",         # Reset background

    # Screen control
    "{clear_screen}": "\033[2J",
    "{clear_line}":   "\033[2K",
    "{home}":         "\033[H",
    "{clear_below}":  "\033[0J",
    "{hide_cursor}":  "\033[?25l",
    "{show_cursor}":  "\033[?25h",
}
```

#### Double Buffering

The double buffer compares current frame to previous frame and only updates changed lines:

```python
class UI:
    _buffer = []       # Current frame being built
    _last_buffer = []  # Previous rendered frame
    _current_line = "" # Line being constructed

    def print(text):   # Append to current line
    def puts(text):    # Finalize line, add to buffer
    def flush(io):     # Diff and render changed lines
    def cls():         # Clear screen and reset buffers
```

**Flush Algorithm:**
1. Finalize current line into buffer
2. If not TTY and not force_colors: strip tokens, output plain text
3. If TTY: position cursor at home
4. For each line index:
   - If line differs from last_buffer: move cursor, clear line, output
5. Store current buffer as last_buffer
6. Clear buffer for next frame

### Fuzzy Matching Algorithm

The scoring formula combines character matching with contextual bonuses.

#### Score Calculation

```python
def calculate_score(try_dir, query_down, query_chars, ctime, mtime):
    score = 0.0

    # 1. Date prefix bonus
    if text.match(/^\d{4}-\d{2}-\d{2}-/):
        score += 2.0

    # 2. Fuzzy character matching (if query exists)
    if query:
        last_pos = -1
        query_idx = 0

        for i, char in enumerate(text_lower):
            if query_idx >= len(query_chars):
                break

            if char == query_chars[query_idx]:
                # Base point
                score += 1.0

                # Word boundary bonus (at start or after non-alnum)
                if i == 0 or not text_lower[i-1].isalnum():
                    score += 1.0

                # Proximity bonus
                if last_pos >= 0:
                    gap = i - last_pos - 1
                    score += 2.0 / sqrt(gap + 1)

                last_pos = i
                query_idx += 1

        # All query chars must match
        if query_idx < len(query_chars):
            return 0.0

        # Density multiplier (concentrated matches score higher)
        score *= query_len / (last_pos + 1)

        # Length penalty (shorter names preferred)
        score *= 10.0 / (text_len + 10.0)

    # 3. Recency bonus (always applied)
    if mtime:
        hours_since = (now - mtime).total_hours()
        score += 3.0 / sqrt(hours_since + 1)

    return score
```

#### Formula Summary

| Component | Formula | Notes |
|-----------|---------|-------|
| Date prefix bonus | `+2.0` | For `YYYY-MM-DD-` prefix |
| Character match | `+1.0` per char | Sequential matching |
| Word boundary | `+1.0` | At index 0 or after non-alnum |
| Proximity | `+2.0 / sqrt(gap + 1)` | Consecutive = +2.0 |
| Density | `* query_len / (last_pos + 1)` | Concentrated matches |
| Length penalty | `* 10.0 / (text_len + 10.0)` | Shorter names preferred |
| Recency | `+3.0 / sqrt(hours + 1)` | Based on mtime |

### TrySelector (TUI State Machine)

The selector manages the interactive loop with keyboard input and rendering.

#### State Variables

```python
class TrySelector:
    # Navigation state
    cursor_pos = 0           # Current selection index
    scroll_offset = 0        # First visible item index

    # Input state
    input_buffer = ""        # Search query text
    input_cursor_pos = 0     # Cursor position in query

    # Delete mode state
    delete_mode = False      # In delete mode?
    marked_for_deletion = [] # Paths marked for delete
    delete_status = None     # Status message to show

    # Result
    selected = None          # SelectionResult on completion

    # Cached data
    _all_tries = None        # Memoized directory list
```

#### Main Loop Structure

```python
def main_loop():
    while True:
        # 1. Load and filter directories
        tries = get_tries()

        # 2. Calculate total items (includes "Create new" if query)
        show_create_new = bool(input_buffer)
        total_items = len(tries) + (1 if show_create_new else 0)

        # 3. Clamp cursor to valid range
        cursor_pos = clamp(cursor_pos, 0, total_items - 1)

        # 4. Render frame
        render(tries)

        # 5. Read key input
        key = read_key()

        # 6. Handle key (updates state or breaks loop)
        handle_key(key)
```

#### Key Handling Logic

```python
match key:
    case "\r":  # Enter
        if delete_mode and marked_for_deletion:
            confirm_batch_delete()
        elif cursor_pos < len(tries):
            selected = {type: "cd", path: tries[cursor_pos].path}
            break
        elif show_create_new:
            selected = {type: "mkdir", path: new_path}
            break

    case "\033[A" | "\x10":  # Up / Ctrl-P
        cursor_pos = max(0, cursor_pos - 1)

    case "\033[B" | "\x0e":  # Down / Ctrl-N
        cursor_pos = min(total_items - 1, cursor_pos + 1)

    case "\x7f" | "\b":  # Backspace
        delete_char_before_cursor()
        cursor_pos = 0  # Reset to top on query change

    case "\x04":  # Ctrl-D
        toggle_delete_mark()

    case "\x03" | "\033":  # Ctrl-C / ESC
        if delete_mode:
            exit_delete_mode()
        else:
            selected = None
            break

    case printable_char:
        insert_char_at_cursor()
        cursor_pos = 0  # Reset to top on query change
```

### Shell Emission

The shell module generates scripts that the shell wrapper evaluates.

#### Quote Escaping

Single quotes with proper escaping for shell safety:

```python
def q(s: str) -> str:
    """Shell-quote a string."""
    return "'" + s.replace("'", "'\"'\"'") + "'"

# Example: "it's a test" -> "'it'\"'\"'s a test'"
```

#### Script Format

Commands are chained with `&& \` for readability:

```bash
# if you can read this, you didn't launch try from an alias. run try --help.
mkdir -p '/path/to/dir' && \
  touch '/path/to/dir' && \
  cd '/path/to/dir'
```

#### Script Generators

| Function | Commands Generated |
|----------|-------------------|
| `script_cd(path)` | `touch`, `cd` |
| `script_mkdir_cd(path)` | `mkdir -p`, `touch`, `cd` |
| `script_clone(path, uri)` | `mkdir -p`, `echo`, `git clone`, `touch`, `cd` |
| `script_worktree(path, repo)` | `mkdir -p`, `echo`, worktree cmd, `touch`, `cd` |
| `script_delete(paths, base)` | `cd base`, `[[ -d ]] && rm -rf` per path, restore pwd |

### CLI Routing

The CLI parses commands and routes to appropriate handlers.

#### Command Priority

1. `--help` / `-h` (handled first, exits)
2. `--version` / `-v` (handled first, exits)
3. Named commands: `init`, `clone`, `worktree`, `exec`
4. Default: treat args as search query, launch selector

#### Exit Codes

| Code | Meaning | Wrapper Action |
|------|---------|----------------|
| 0 | Success | Eval output (execute cd) |
| 1 | Cancelled/Error | Print output |
| 2 | No args (help shown) | Print help |

---

## Test Compatibility

### Test Framework Overview

Tests live in `spec/tests/` and validate behavior against markdown specifications in `spec/`.

#### Test Runner

```bash
./spec/tests/runner.sh /path/to/try-binary
./spec/tests/runner.sh "valgrind ./try"  # With memory checker
```

The runner:
1. Creates test environment with sample directories
2. Sources each `test_*.sh` file
3. Provides helper functions: `pass`, `fail`, `section`, `try_run`
4. Reports results and exit code

#### Test Environment

```
$TEST_TRIES/
  2025-11-01-alpha            (oldest mtime)
  2025-11-15-beta
  2025-11-20-gamma
  2025-11-25-project-with-long-name
  no-date-prefix              (most recent mtime)
```

### Critical Test Requirements

#### 1. Tests Must Terminate

The TUI blocks waiting for input. Every test MUST use:
- `--and-exit` to render once and exit, OR
- `--and-keys=<sequence>` ending with Enter/Escape

```bash
# WRONG: will hang forever
output=$(try_run exec)

# RIGHT: render once
output=$(try_run --and-exit exec 2>&1)

# RIGHT: inject keys ending with Enter
output=$(try_run --and-keys="beta"$'\r' exec)
```

#### 2. Output Capture

- TUI renders to stderr
- Script output goes to stdout
- Use `2>&1` to capture TUI for display tests
- Use `2>/dev/null` to discard TUI for script tests

#### 3. Environment Variables

| Variable | Purpose |
|----------|---------|
| `TRY_WIDTH` | Override terminal width |
| `TRY_HEIGHT` | Override terminal height |
| `TEST_TRIES` | Path to test directories |

### Test Patterns

```bash
# Pattern 1: Check TUI renders correctly
output=$(try_run --path="$TEST_TRIES" --and-exit exec 2>&1)
if echo "$output" | grep -q "expected text"; then
    pass
else
    fail "description" "expected" "$output" "spec.md#section"
fi

# Pattern 2: Check selection produces correct script
output=$(try_run --path="$TEST_TRIES" --and-keys="beta"$'\r' exec 2>/dev/null)
if echo "$output" | grep -q "cd '"; then
    pass
fi

# Pattern 3: Check exit code
try_run --and-keys=$'\x1b' exec >/dev/null 2>&1
if [ $? -eq 1 ]; then
    pass
fi
```

### Spec Files

| File | Coverage |
|------|----------|
| `command_line.md` | CLI options, commands, exit codes |
| `init_spec.md` | Shell wrapper generation |
| `tui_spec.md` | Display, layout, keyboard handling |
| `fuzzy_matching.md` | Scoring algorithm |
| `delete_spec.md` | Delete workflow, script format |
| `token_system.md` | ANSI token definitions |
| `test_spec.md` | Test framework requirements |
| `performance.md` | Performance targets |

---

## Porting Checklist

### Pre-Implementation

- [ ] Read all spec files in `spec/` directory
- [ ] Study the Ruby implementation thoroughly
- [ ] Understand the test framework requirements
- [ ] Choose appropriate libraries for:
  - [ ] Terminal raw mode / key reading
  - [ ] CLI argument parsing
  - [ ] Terminal size detection

### Critical Behaviors to Match Exactly

#### 1. Version Output Format

```
try X.Y.Z
```

Must match regex: `^try [0-9]+\.[0-9]+`

#### 2. Help Text Content

Must contain: `"ephemeral workspace manager"`

#### 3. Script Output Format

```bash
# if you can read this, you didn't launch try from an alias. run try --help.
command1 && \
  command2 && \
  command3
```

- Warning comment on first line
- Commands chained with ` && \`
- 2-space indent on continuation lines
- No trailing continuation on last command

#### 4. Quote Escaping

Single quotes with embedded single quote escaping:

```
input:  it's
output: 'it'"'"'s'
```

#### 5. Exit Codes

| Situation | Exit Code |
|-----------|-----------|
| Success (selection made) | 0 |
| Cancelled (Esc/Ctrl-C) | 1 |
| Error | 1 |
| No args (help shown) | 2 |

### ANSI Token Mappings

All tokens must map to these exact sequences:

| Token | ANSI Sequence | Description |
|-------|---------------|-------------|
| `{b}` | `\033[1;33m` | Bold + Yellow |
| `{/b}` | `\033[22m\033[39m` | Reset bold + fg |
| `{dim}` | `\033[90m` | Bright black |
| `{text}` | `\033[0m\033[39m` | Reset |
| `{reset}` | `\033[0m\033[39m\033[49m` | Full reset |
| `{/fg}` | `\033[39m` | Reset fg only |
| `{h1}` | `\033[1;38;5;208m` | Bold + 256-color orange |
| `{h2}` | `\033[1;34m` | Bold + Blue |
| `{section}` | `\033[1m` | Bold |
| `{/section}` | `\033[0m` | Reset |
| `{strike}` | `\033[48;5;52m` | Dark red background |
| `{/strike}` | `\033[49m` | Reset background |
| `{hide_cursor}` | `\033[?25l` | |
| `{show_cursor}` | `\033[?25h` | |
| `{home}` | `\033[H` | |
| `{clear_screen}` | `\033[2J` | |
| `{clear_line}` | `\033[2K` | |
| `{clear_below}` | `\033[0J` | |

### Keyboard Handling

#### Escape Sequences

| Key | Sequence | Hex |
|-----|----------|-----|
| Up | `\033[A` | `1B 5B 41` |
| Down | `\033[B` | `1B 5B 42` |
| Right | `\033[C` | `1B 5B 43` |
| Left | `\033[D` | `1B 5B 44` |
| Enter | `\r` | `0D` |
| Escape | `\033` | `1B` |
| Backspace | `\x7F` | `7F` |

#### Control Characters

| Key | Hex | Name |
|-----|-----|------|
| Ctrl-A | `\x01` | Start of heading |
| Ctrl-B | `\x02` | |
| Ctrl-C | `\x03` | End of text |
| Ctrl-D | `\x04` | End of transmission |
| Ctrl-E | `\x05` | |
| Ctrl-F | `\x06` | |
| Ctrl-H | `\x08` | Backspace |
| Ctrl-K | `\x0B` | |
| Ctrl-N | `\x0E` | |
| Ctrl-P | `\x10` | |
| Ctrl-W | `\x17` | |

### Score Calculation Formula

```python
# 1. Date prefix bonus (if matches ^\d{4}-\d{2}-\d{2}-)
score += 2.0

# 2. For each matched character:
score += 1.0  # base
if word_boundary:
    score += 1.0
if previous_match_exists:
    gap = current_pos - previous_pos - 1
    score += 2.0 / sqrt(gap + 1)

# 3. After all matches (if all query chars matched):
score *= query_length / (last_match_pos + 1)  # density
score *= 10.0 / (text_length + 10.0)          # length penalty

# 4. Recency bonus (always applied):
hours = (now - mtime).total_hours()
score += 3.0 / sqrt(hours + 1)
```

### Shell Script Output Format

#### CD Command
```bash
touch '/path/to/dir' && \
  cd '/path/to/dir'
```

#### MKDIR Command
```bash
mkdir -p '/path/to/dir' && \
  touch '/path/to/dir' && \
  cd '/path/to/dir'
```

#### Clone Command
```bash
mkdir -p '/path/to/dir' && \
  echo 'Using git clone to create this trial from URL.' && \
  git clone 'URL' '/path/to/dir' && \
  touch '/path/to/dir' && \
  cd '/path/to/dir'
```

#### Delete Command
```bash
cd '/tries/base' && \
  [[ -d 'dir-name-1' ]] && rm -rf 'dir-name-1' && \
  [[ -d 'dir-name-2' ]] && rm -rf 'dir-name-2' && \
  ( cd '/original/pwd' 2>/dev/null || cd "$HOME" )
```

### Init Script Format

#### Bash/Zsh
```bash
try() {
  local out
  out=$('/path/to/try' exec --path '/tries/path' "$@" 2>/dev/tty)
  if [ $? -eq 0 ]; then
    eval "$out"
  else
    echo "$out"
  fi
}
```

#### Fish
```fish
function try
  set -l out ('/path/to/try' exec --path '/tries/path' $argv 2>/dev/tty | string collect)
  if test $status -eq 0
    eval $out
  else
    echo $out
  end
end
```

### Implementation Verification

After implementing, verify with the test suite:

```bash
# Run all tests
./spec/tests/runner.sh /path/to/your/implementation

# Run with memory checker (if applicable)
./spec/tests/runner.sh "valgrind -q /path/to/your/implementation"
```

All tests must pass before the port is considered complete.

### Common Pitfalls

1. **Forgetting to terminate test sequences** - Always end `--and-keys` with Enter or Escape
2. **Wrong escape sequence handling** - Arrow keys are 3-byte sequences
3. **Score calculation precision** - Use floating point, not integers
4. **Quote escaping in scripts** - Test with names containing single quotes
5. **TTY detection** - Handle non-TTY gracefully for piped output
6. **Terminal size fallback** - Default to 80x24 if detection fails
7. **Delete safety check** - Verify realpath is inside tries directory
8. **PWD restoration** - Handle case where original pwd was deleted

---

## References

- Ruby implementation: `<path-to-try>/try.rb`
- AGENTS.md: `<path-to-try>/AGENTS.md`
- Spec files: `<path-to-try>/spec/`
- Test suite: `<path-to-try>/spec/tests/`
