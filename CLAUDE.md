# try-py Project Context

## What This Is
Python port of the Ruby `try` tool (ephemeral workspace manager).

## Current Status
- **Tests**: 308/329 passing (93.6%) - exceeds Ruby original (307/329)
- **Commit**: Ready to push, all changes committed
- **Shell integration**: Working - uses venv Python directly

## Project Structure
```
src/try_py/
  cli.py      - Click-based CLI entry point
  ui.py       - Token system, double buffering
  fuzzy.py    - Scoring algorithm
  selector.py - TUI state machine
  shell.py    - Script generation for shell eval
```

## Key Files
- `PORTING.md` - Comprehensive guide for future language ports
- `.mise.toml` - Python 3.12 + uv
- `pyproject.toml` - click, rich dependencies

## Running Tests
```bash
cd <path-to-ruby-try> && bash spec/tests/runner.sh <path-to-try-py>/.venv/bin/try
```

## Shell Setup
```bash
eval "$(<path-to-try-py>/.venv/bin/try init <tries-directory>)"
```

## Known Failing Tests (21)
Most are ANSI control sequence tests that also fail on Ruby:
- Cursor hide/show sequences
- Home positioning
- Clear screen sequences
These are skipped in test mode (`--and-exit`) by design.

## TODO / Future Work
- User was about to test a few things before pushing
- Consider publishing to PyPI
- Could add more Rich integration for prettier output
