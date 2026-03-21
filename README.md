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
| `--interactive` | ❌ | False | Pause for human review after compile |
| `--verbose` | ❌ | False | Show agent reasoning text |
| `--log-level` | ❌ | INFO | Logging verbosity |
| `--resume-from` | ❌ | — | Resume from an existing output folder |
| `--output-dir` | ❌ | `output_files` | Root output directory |
