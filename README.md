# resumint

CLI tool that generates tailored, ATS-compatible resume PDFs from a job description and a portfolio of documents, using an LLM agent.

## Setup

```bash
# Clone and install
uv sync

# Configure
cp .env.example .env
# Edit .env with your OpenAI API key
```

Requires `pdflatex` installed on the system (e.g. via TeX Live or MacTeX).

## Usage

```bash
# Minimal
uv run resumint --job path/to/job.pdf --portfolio path/to/resume.pdf

# Multiple portfolio documents
uv run resumint --job job.pdf --portfolio resume.pdf --portfolio projects.md

# Full options
uv run resumint --job job.pdf \
    --portfolio resume.pdf \
    --instructions "Emphasize data platform and ML systems work; keep the tone conservative." \
    --model gpt-4o \
    --interactive \
    --log-level DEBUG \
    --resume-from output_files/Acme/SoftwareEngineer_20260315143022
```

## How it works

1. **Phase 1 — Content Loop**: The agent reads the job description and portfolio, generates targeted resume content, validates truthfulness against the portfolio, and saves `resume_content.json`.

2. **Phase 2 — LaTeX Loop**: The agent designs and generates `.tex` + `.cls` files from scratch, compiles to PDF via pdflatex, and iteratively fixes any compile errors.

Outputs land in `output_files/{Company}/{JobTitle}_{timestamp}/`.

## CLI Options

| Option | Required | Default | Description |
|---|---|---|---|
| `--job` | ✅ | — | Job description file path |
| `--portfolio` | ✅ | — | Portfolio document path(s) |
| `--model` | ❌ | from `.env` | LLM model override |
| `--instructions` | ❌ | — | Inline extra guidance for emphasis, tone, or omissions |
| `--instructions-file` | ❌ | — | File containing extra guidance for emphasis, tone, or omissions |
| `--interactive` | ❌ | False | Enter an iterative review loop after LaTeX generation |
| `--verbose` | ❌ | False | Show agent reasoning text |
| `--log-level` | ❌ | INFO | Logging verbosity |
| `--resume-from` | ❌ | — | Resume from an existing output folder |
| `--output-dir` | ❌ | `output_files` | Root output directory |

If you use `--interactive` and do not pass `--instructions` or `--instructions-file`, the CLI prompts once before Phase 1 for any optional additional guidance. Press ENTER on the first line to skip, or type `END` on its own line to finish the note.

In `--interactive` mode, the CLI keeps the original build context available and lets you:
- enter a natural-language revision request for the model
- type `manual` to edit `resume.tex` / `resume.cls` yourself and then ask the model to compile and repair
- type `done` to run one final compile and finish
