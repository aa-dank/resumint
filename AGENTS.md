# AGENTS.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Project Overview

resumint is a CLI tool that generates tailored, ATS-compatible resume PDFs from a job description and portfolio documents using a single OpenAI LLM agent. The agent runs two sequential loops autonomously: content generation with truthfulness validation, then LaTeX design and compilation.

## Build & Run Commands

```bash
# Install dependencies
uv sync

# Run the CLI
uv run resumint --job path/to/job.pdf --portfolio path/to/resume.pdf

# Run with multiple portfolio docs
uv run resumint --job job.pdf --portfolio resume.pdf --portfolio projects.md

# Resume an interrupted run
uv run resumint --job job.pdf --portfolio resume.pdf --resume-from output_files/Company/JobTitle_20260319/

# Verbose / interactive mode
uv run resumint --job job.pdf --portfolio resume.pdf --verbose --interactive --log-level DEBUG
```

There are no tests, linting, or type-checking configured in this project.

## System Requirement

`pdflatex` must be installed (via TeX Live or MacTeX). The compile toolchain auto-detects `xelatex` vs `pdflatex` based on whether `\usepackage{fontspec}` appears in the `.tex` file.

## Architecture

The project uses the **OpenAI Agents SDK** (`openai-agents`) — not LangChain, not raw OpenAI API calls. The single agent (`ResumeBuilder`) is configured with a system prompt and a set of tools, then run via `Runner.run_streamed()`.

### Two-Phase Agent Loop

**Phase 1 — Content Loop** (`agent.py` + `prompts/prompts.py`):
The agent reads raw job/portfolio text (no structured extraction step), generates resume JSON content, validates every bullet against the portfolio for truthfulness, and saves `resume_content.json` via the `save_resume_content` tool. A `validation_report.txt` is written for any gaps.

**Phase 2 — LaTeX Loop** (`agent.py` + `latex_toolbox.py`):
The agent designs and generates `.cls` + `.tex` files **from scratch** (no Jinja2 templates), compiles via `pdflatex`, and iteratively fixes compile errors (up to 5 attempts). Example `.tex`/`.cls` pairs in `templates/examples/` are injected into the prompt as design references, not rigid templates.

### Tool Factory Pattern

All agent tools are defined as closures inside `build_tools(output_dir)` in `agent.py`. This binds the output directory to every tool without global state. Tools are decorated with `@function_tool` from the Agents SDK — their **docstrings are the tool descriptions shown to the model**, so they must be precise and instructive.

### Key Module Responsibilities

- `main.py` — Typer CLI entry point. Parses documents via `markitdown`, assembles the `InitialMessage`, builds and runs the agent, handles interactive review gate.
- `agent.py` — Agent construction (`build_agent`), tool factory (`build_tools`), streaming runner (`run_agent`), and `PHASE_SIGNALS` display mapping.
- `config.py` — `pydantic-settings` `Settings` class reading from `.env`. Singleton `settings` object used throughout.
- `prompts/prompts.py` — `Prompt` base class with `render()`, the static `SYSTEM_PROMPT_TEXT` (defines both phases, the resume JSON schema, and all agent behavioral rules), and `InitialMessage` which assembles per-run context (job text, portfolio, run config, LaTeX examples).
- `latex_toolbox.py` — `compile_resume_latex_to_pdf()` (runs compiler twice, parses `l.<N>` error lines), `escape_for_latex()`, `cleanup_latex_files()`.
- `parsers.py` — `load_doc_text()` handles JSON/MD/TXT directly and routes PDF/DOCX through `MarkItDown`.
- `utils.py` — `build_application_destination()` creates the output folder path, `setup_run_logger()` configures file+stream logging, `build_final_summary()` assembles the end-of-run status.

### Output Folder Structure

Each run produces artifacts in `output_files/{Company}/{JobTitle15}_{timestamp}/`:
- `resume_content.json` — validated content from Phase 1
- `resume.cls` + `resume.tex` + `resume.pdf` — LaTeX artifacts from Phase 2
- `build_state.json` — phase checkpoint enabling `--resume-from`
- `validation_report.txt` — content gaps (if any)
- `compile_errors.txt` — unresolved errors (if max attempts reached)
- `run.log` — full run log

### Design Specs

Detailed design documents live in `dev/specs/` (PROJECT_SPEC.md, AGENT_DESIGN.md, PROMPTS_DESIGN.md). Reference implementations from a prior project are in `dev/reference/` — these are read-only context, not active code.

## Key Design Decisions

- **No Jinja2 template filling.** The agent generates `.tex`/`.cls` from scratch for full design freedom. The compile loop must handle agent-generated LaTeX errors.
- **No structured extraction pass.** The agent reasons over raw document text directly — no intermediate JSON extraction step.
- **Prompt-driven behavior.** The system prompt in `prompts/prompts.py` defines both phases, all rules, the JSON schema, and common LaTeX error fixes. Changes to agent behavior primarily happen there.
- **Resumability via `build_state.json`.** The agent writes phase checkpoints; `--resume-from` skips completed phases.
- **ATS compatibility.** The system prompt forbids `tabular` for body content, `multicol` for sections, `tcolorbox`, `fontspec`, and `colorbox` on text. No hidden keyword injection.
