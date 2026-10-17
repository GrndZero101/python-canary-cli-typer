# Python Canary CLI Typer

Canary consumer of python-template-cli-typer, exercising the template in real use

Generated from [python-template-cli-typer](https://github.com/GrndZero101/python-template-cli-typer)
on [python-template-base](https://github.com/GrndZero101/python-template-base), built
around one idea: every rule in [CLAUDE.md](CLAUDE.md) exists so a human (or an AI agent) can stop
the program and inspect it. Structure, debuggability and portability rules are mechanically enforced
by lint config and a `prek` gate — not just documented and hoped for.

## What's here

- **`src/python_canary_cli_typer/`** — the package. It ships a
  scaffold CLI, `tdf-cli`, on typer, pydantic-settings, rich and loguru, with one
  placeholder command, `about`. Replace it or build beside it; the plumbing around it — settings,
  output, logging, the entry point — is meant to stay. Built beside it: `weather`, which looks up
  current conditions from wttr.in over httpx, offline-tested via `httpx.MockTransport`.
- **`tools/`** — the custom checks no off-the-shelf linter covers: `check_conventions.py` and
  `convention_rules.py` (the CLAUDE.md conventions no linter checks: `def` or `class` inside a
  function, complex comprehensions, `raise ... from None`, computed `getattr`, an unguarded
  `main`), `branch_guard.py` and `gate.py` (the `PreToolUse`/`PostToolUse` hooks that
  block edits to `main` and run the lint gate on save), `stop_gate.py` (the `Stop` hook that
  re-checks every changed file and runs the tests before a turn ends), `gate_log.py` (one line per
  gate run in the gitignored `.gate.log`), `session_doctor.py` (the `SessionStart` hook that
  reports the branch, and any guard switched off by a missing `prek` or git shim),
  `finish_branch.py` (consolidates, gates, tests and merges a finished branch into `main`; see the
  `git-workflow` skill), `hook_payload.py` (shared parsing), and
  `debug_module.py` and `debug_pytest.py` (let the DebugMCP CLI debug a source module and a test
  file; see below).
- **`.claude/skills/`** — the conventions for this stack, loaded by an agent when they apply:
  `python-cli-typer` for commands and settings, and `python-data` and `python-tui` for a
  command that crunches files or draws a full-screen interface.
- **`.debugmcp.json`** — debugger adapters for an agent driving [DebugMCP](https://github.com/microsoft/DebugMCP).
- **`CLAUDE.md`** — the full rule set: structure, debuggability, agent-friendliness, portability,
  branching, and commit conventions, plus a table of exactly what is enforced by what.

## Setup

The template's generation tasks already ran these. Repeat them only on a fresh clone:

```bash
uv sync
prek install -t pre-commit -t commit-msg -t pre-merge-commit
```

All three shims are required — `prek install` alone wires only `pre-commit`, which silently skips
the commit-message check and breaks `--no-ff` merges into `main`.

### Live debugging for an agent (optional, once per machine)

`.debugmcp.json` lets Claude Code set breakpoints, step and inspect values through the standalone
DebugMCP CLI, with no IDE involved. The server is installed per user, so the project itself never
needs Node. It needs Node 20+:

```bash
npm install --global debugmcp
claude mcp add --scope user debugmcp-cli -- debugmcp serve --stdio
```

On native Windows, use `-- cmd /c debugmcp serve --stdio`. The name is `debugmcp-cli` because the
VS Code extension takes `debugmcp`. Prefer this to `debugmcp configure`, which also installs a
skill written for the VS Code extension. The `python-debug` skill covers using it.

## Commands

```bash
prek run --files <path> [<path> ...]    # the whole gate, on the files you touched
prek run ty --all-files                 # one hook by id: ruff-check, ty, rumdl, conventions
prek run --all-files                    # the whole gate, every tracked file
uv run pytest                           # tests, which the gate does not run
```

Run the linters **through prek, never directly.** `ty` is not installed outside the gate, so
`ty check` is "command not found", and a `ruff` on PATH can be older than the hook's, which is
always the latest release, and disagree with it. prek runs what the commit will, so what passes here
passes at commit.

## Using the CLI

```bash
uv run tdf-cli --help
uv run tdf-cli about                  # table on stdout
uv run tdf-cli about --output json    # one JSON object on stdout
uv run tdf-cli --verbose about        # global options go before the command
uv run tdf-cli weather cleve          # current conditions from wttr.in
```

Every setting resolves **flag, then environment variable, then config file, then default**:

| Setting | Flag | Environment variable | Default |
|---|---|---|---|
| Config file to read | `--config PATH` (global) | `TDF_CLI_CONFIG` | see below |
| Debug logging to stderr | `--verbose` / `--no-verbose` (global) | `TDF_CLI_VERBOSE` | off |
| Output format | `--output` / `-o` (per command) | `TDF_CLI_OUTPUT` | `table` |

The config file is YAML, keyed by setting name, and need not exist:

```yaml
output: json
verbose: true
```

It lives at `$XDG_CONFIG_HOME/tdf-cli/config.yaml` when `XDG_CONFIG_HOME` is set, on any
platform; otherwise at `~/.config/tdf-cli/config.yaml` on Linux and macOS, and
`%APPDATA%\tdf-cli\config.yaml` on Windows. `tdf-cli about` shows the path in use.

The docstring of `config.py` says how to add a setting. An invalid value from any source exits 2
with a message naming the flag, the variable and the config file.

Shell completion is emitted rather than installed:

```bash
_TDF_CLI_COMPLETE=source_zsh tdf-cli > "${ZDOTDIR:-$HOME}/completions/_tdf-cli"
```

## Installing it

`uv run tdf-cli` works inside this project. To put `tdf-cli` on your PATH
everywhere, in an isolated environment of its own:

```bash
uv tool install .                         # a snapshot of this checkout
uv tool install --editable .              # while developing: source edits apply at once
uv tool install git+https://github.com/<owner>/<repo>           # for anyone, from git
uv tool install git+https://github.com/<owner>/<repo>@v0.2.0    # a tagged release
uv tool update-shell                      # once, if uv warns its bin directory is not on PATH
```

The command lands in `uv tool dir --bin`. uv manages the tool by its package name,
`python-canary-cli-typer`:

```bash
uv tool upgrade python-canary-cli-typer
uv tool uninstall python-canary-cli-typer
```

An upgrade rebuilds from where the tool was installed — this checkout or the git URL — so after
pulling or editing, it picks up both the new code and the new version.

## Releasing a version

The version lives in `pyproject.toml` alone; `tdf-cli --version` reads it from the
installed package. Bump it on a branch like any other change, finish the branch, then tag `main`:

```bash
git switch -c chore/release
uv version --bump patch                   # or minor / major; updates pyproject.toml and uv.lock
git commit -am "chore(release): bump to $(uv version --short)"
uv run python tools/finish_branch.py "chore(release): bump to $(uv version --short)"
git tag "v$(uv version --short)" && git push origin main --tags
```

An editable install reports the version it was installed at until it is reinstalled with
`uv tool install --editable . --reinstall`; its code, unlike its version, is always current.

## Updating from the template

The project comes from two templates, and each updates separately, touching only its own files:
the CLI layer (`src/`, `tests/`, `pyproject.toml`, this README), recorded in
`.copier-answers.yml`, and the base under it (`CLAUDE.md`, `tools/`, the hooks, the shared
skills), recorded in `.copier-answers.base.yml`. Run both, the base first: the CLI layer is
written against the base, so a CLI change that needs a base change then never lands ahead of it.
Each needs a clean tree, so commit between them:

```bash
git switch -c chore/template-update
copier update --trust -a .copier-answers.base.yml     # the base
# resolve conflicts, if any; then:
uv sync && git add -A && git commit -m "chore(template): update the base"
copier update --trust                                 # the CLI layer
# resolve conflicts, if any; then:
uv sync && git add -A && git commit -m "chore(template): update the cli layer"
uv run python tools/finish_branch.py "chore(template): update from the templates"
```

Do not delete either answers file: `copier update` reads it to know what you answered.
`--trust` is required because the template declares `_tasks`. They run on the first copy only, so
an update runs none of them, but copier asks for the flag anyway and exits 4 without it. An agent
can run the update with `--defaults`, since it cannot answer copier's prompts; a new question then
takes the template's default, so check `git diff` on both answers files. `uv sync` comes before any
check, so a dependency the template dropped is gone from `.venv` too. Conflicts, new questions and
pinning a version:
[Keeping it in sync](https://github.com/GrndZero101/python-template-cli-typer#keeping-it-in-sync-with-the-template).

## License

[MIT](LICENSE)
