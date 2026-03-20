# resumint — Project Specification

**Project:** resumint  
**Spec date:** 2026-03-15  
**Status:** Pre-build planning

---

## 1. What is resumint?

`resumint` is a command-line tool that generates a tailored, compiled resume PDF from a job description and a portfolio of user documents. It is fully agentic: a single LLM agent reads all inputs as raw text, generates targeted resume content, validates that content against the portfolio, renders it as LaTeX, and loops until the PDF compiles cleanly — with no required human intervention unless explicitly requested.

The name: **resum**e + m**int** (to mint/produce).

---

## 2. Prior Art

`resumint` draws on lessons from a prior project (`job_hunter_toolbox`) that solved the same problem using a sequential, manually-driven pipeline. Key takeaways from that prior implementation:

| What worked | What didn't |
|---|---|
| LaTeX + Jinja2 templates produce high-quality PDF output | Manual pause between generation and compilation broke automation |
| `output_files/{Company}/{JobTitle}_{ts}/` folder convention keeps runs organized | ~9 separate LLM calls (one per section) was expensive and brittle |
| `MarkItDown`-based document parsing handles PDF/DOCX/MD/TXT uniformly | A dedicated structured-extraction step added latency and an extra failure point |
| Running pdflatex twice resolves cross-references reliably | Sentence-transformer scoring was a manual relevance signal the LLM can do natively |
| Jinja2 custom LaTeX delimiters (`\BLOCK{}`, `\VAR{}`) avoid delimiter conflicts | Static ATS keyword injection (hidden white text) is a hack with no real value |

**Intentional departure from prior art:** `resumint` does not use Jinja2 template filling for LaTeX rendering. The agent generates `.tex` and `.cls` source from scratch, guided by example file pairs in `templates/examples/` that are loaded verbatim into the initial message. This unlocks full design freedom at the cost of requiring the compile loop to be robust against agent-generated LaTeX.

Reference implementations of the LaTeX toolbox and document parser are in `dev/reference/`. The coding agent building `resumint` should read these for context.

---

## 3. Core Design Principles

### 3.1 Raw Text In — No Structured Extraction Pass
The agent receives raw document text directly — job description and all portfolio materials — as its context. There is no dedicated LLM pre-processing step that converts them into intermediate JSON. The agent reasons over unstructured text natively.

**Why:** Modern top models hold large contexts and identify relevant facts on demand. A dedicated extraction step adds a round-trip LLM call, creates a fragile intermediate representation, and introduces a place for information to be dropped.

### 3.2 Two Autonomous Loops Before Any Human Sees It
Two loops run fully automatically before the human review gate:

1. **Content + Truthfulness Loop** — generate, validate against portfolio, revise until content is targeted and grounded
2. **LaTeX Design & Compile Loop** — agent generates `.tex` and `.cls` from scratch guided by example references loaded into the prompt, compiles, reads errors, fixes, repeat until PDF compiles

Only after both loops succeed is the user offered the option to review. At that point, the file is already a valid, compilable `.tex`.

### 3.3 Organized Output Folders
Every run produces artifacts in a dedicated folder:
```
output_files/{Company}/{JobTitle15}_{YYYYMMDDHHmmSS}/
```
All intermediate files, the final `.tex`, the compiled `.pdf`, and the run log live there. This mirrors the convention from the prior project and is worth keeping — it makes outputs easy to navigate, compare, and debug.

The output folder is generated programmatically from the job description metadata (company name + job title + timestamp), ensuring every run gets a unique, human-readable home. See `utils.py` — `build_application_destination()` handles this.

### 3.4 No ATS Keyword Injection
Do not use hidden white-text keyword blocks. Targeting is accomplished entirely through generated content quality.

### 3.5 Resumability
Each major agent action writes its output to the output folder. If a run is interrupted, re-invoking with `--resume-from <output-folder>` picks up from the last successful checkpoint.

---

## 4. Two-Loop Architecture

### Loop A: Content + Truthfulness Loop

**Goal:** Resume content that is maximally job-targeted and 100% grounded in the portfolio.

```
1. Read job description. Identify: role, requirements, preferred qualifications, keywords.
2. Read all portfolio text. Map relevant experiences, projects, skills, education, metrics.
3. Draft resume sections: work_experience, education, projects, skill_section, 
   certifications, achievements.
4. Validate each bullet:
   - Is this traceable to the portfolio? NO → remove or replace with something that is.
   - Is there a stronger portfolio fact that better targets this requirement? YES → revise.
5. Repeat steps 3–4 until content is grounded and optimized (max 3 iterations).
6. Call save_resume_content with final JSON. Write validation_report.txt with any gaps.
```

Loop A terminates when the agent calls `save_resume_content`. This is a deliberate gate — the tool's docstring instructs the agent to call it only when satisfied.

### Loop B: LaTeX Design & Compile Loop

**Goal:** A visually cohesive, ATS-compatible `.tex` + `.cls` document pair that compiles to a valid PDF — designed from scratch by the agent with intentional choices that present this specific candidate compellingly for this specific role.

**Design philosophy:** Loop B is a design step, not just a compile-error fixer. The agent generates the full `.tex` and `.cls` source from scratch, using the example LaTeX pairs in `templates/examples/` (provided verbatim in the initial message) as a reference vocabulary. The agent reads these, draws on them, and adapts or departs from them freely — the examples are inspiration, not constraints. The result should feel like a thoughtful human designer made real choices about layout, section ordering, visual hierarchy, and whitespace. The design should project a **cohesive image of the candidate** consistent with the role and the overall picture their portfolio paints. The agent is expected to infer appropriate visual tone and register directly from the materials.

**ATS compatibility — avoid these patterns:**
- `\begin{tabular}` for body content — parsers may not read table cells linearly
- `\begin{multicol}` for content sections (header or summary use is fine)
- `tcolorbox`, floating frames, or text-box environments around content
- `\usepackage{fontspec}` — stick to pdflatex-compatible fonts
- `\colorbox` fills on text content

Prefer: `\section`, `\subsection`, `itemize`, `geometry` for layout. Horizontal rules, subtle color accents on section headings, and custom spacing are all fine.

```
1. Review the finalized resume content and the target role. Decide:
   - Which section leads (experience, education, or projects — strongest first).
   - Layout: single-column, two-column sidebar, or hybrid with rules.
   - Tone: infer the appropriate visual register from the role, company, and the candidate's materials.

2. Generate the document class: call write_cls_file(<cls_content>)
   - Draw on the .cls examples in the initial message as reference.
   - The \documentclass{} in the .tex MUST be \documentclass{resume} to match.

3. Generate the LaTeX source: call write_tex_file(<full_tex_content>)
   - Content variables come from the resume_content.json saved in Loop A.
   - Apply escape_for_latex logic to all user-supplied text content.

4. Call compile_latex on the resume.tex path:
   - SUCCESS → PDF exists → exit loop.
   - FAILURE → returns stderr, error line numbers.

5. Call read_tex_file (and read_output_file("resume.cls") if the error is in the .cls).
6. Make surgical fixes to the lines mentioned in errors:
   - Unescaped special chars: & % $ # _ { } ~ ^ \
   - Empty environments with no \item lines — remove the block entirely.
   - Malformed \href{}{} or URL encoding issues.
   - .cls definition errors: undefined command, missing brace.
7. Call write_tex_file (or write_cls_file) with corrected content.
8. Repeat from step 4 (max 5 compile attempts).
```

**Important:** Once the `.tex` and `.cls` are written in steps 2–3, do NOT rewrite them from scratch on subsequent attempts. Fix only the specific lines causing errors. Rewriting from scratch resets all accumulated fixes and restarts the error cycle.

### Human Review Gate (`--interactive`)

After both loops succeed, if `--interactive` was passed:
```
Resume compiled successfully → output_files/Acme/SoftwareEngineer_20260315143022/resume.pdf

Open resume.tex to make edits.
Press ENTER to recompile, or SKIP to finish without recompile: _
```
- ENTER → compile once more and finish
- SKIP → finish immediately

Without `--interactive`, the run ends silently after Loop B.

---

## 5. Suggested Project Structure

The structure below is a starting point, not a mandate. The implementation agent should create only the files and folders that make sense given actual project scope. Some modules may be merged, split, or skipped entirely if the code is cleaner without them.

```
resumint/
├── .env                          ← API keys (gitignored)
├── .env.example                  ← template for .env
├── pyproject.toml
├── README.md
├── config.py                     ← pydantic-settings, reads .env
├── agent.py                      ← Agent + Runner setup, tool factory
├── main.py                       ← CLI entry point
├── parsers.py                    ← document loading (PDF/DOCX/MD/TXT via MarkItDown)
├── latex_toolbox.py              ← LaTeX compile, escape, cleanup utilities
├── utils.py                      ← output folder creation, run logger, misc helpers
├── tools/                        ← agent-facing tool functions (may stay in agent.py if small)
│   ├── file_tools.py             ← read/write artifacts in output folder
│   └── latex_tools.py            ← wrappers around latex_toolbox.py
├── prompts/                      ← Prompt class and assembled prompt objects
│   └── prompts.py                ← Prompt class + InitialMessage and system prompt assembly
├── templates/
│   └── examples/                 ← paired .tex/.cls reference files injected into the prompt
│       ├── resume.tex            ← copied from job_hunter_toolbox (see PROMPTS_DESIGN.md §3)
│       └── resume.cls
└── output_files/                 ← generated artifacts (gitignored except .gitkeep)
    └── .gitkeep
```

---

## 6. CLI Design

```bash
# Minimal
resumint --job path/to/job.pdf --portfolio path/to/resume.pdf

# Multiple portfolio documents
resumint --job job.pdf --portfolio resume.pdf projects.md skills.txt

# Full options
resumint --job job.pdf \
         --portfolio resume.pdf \
         --model gpt-4o \              # override model from config
         --interactive \               # pause for human review after compile
         --log-level DEBUG \           # set logging verbosity
         --resume-from output_files/Acme/SoftwareEngineer_20260315143022
```

| Arg | Required | Default | Description |
|---|---|---|---|
| `--job` | ✅ | — | Job description file path |
| `--portfolio` | ✅ | — | Portfolio document path(s), space-separated |
| `--model` | ❌ | from `.env` | LLM model override |
| `--interactive` | ❌ | False | Enable human review gate after compile |
| `--log-level` | ❌ | `INFO` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `--resume-from` | ❌ | — | Path to an existing output folder to resume |
| `--output-dir` | ❌ | `output_files` | Root output directory |

---

## 7. Configuration (`config.py`)

```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    openai_api_key: str
    default_model: str = "gpt-4o"
    output_dir: str = "output_files"
    max_content_loop_iterations: int = 3
    max_compile_loop_iterations: int = 5
    log_level: str = "INFO"               # DEBUG | INFO | WARNING | ERROR

    model_config = SettingsConfigDict(env_file=".env")

settings = Settings()
```

`.env` file holds secrets. `creds.py` pattern from prior project is not used.

---

## 8. Output Folder Artifacts

```
output_files/{Company}/{JobTitle15}_{ts}/
├── build_state.json          ← agent phase checkpoint (resumability)
├── resume_content.json       ← validated content from Loop A
├── validation_report.txt     ← Loop A gaps/warnings (if any)
├── resume.tex                ← LaTeX (may differ from first render due to Loop B edits)
├── resume.pdf                ← compiled output
├── resume.cls                ← generated document class (must match \documentclass{resume})
├── compile_errors.txt        ← Loop B errors if max attempts reached
├── run.log                   ← full agent run log: tool calls, loop iterations, timing
└── {original_job_file}       ← moved here by cleanup
```

---

## 9. Python Dependencies

Use **`uv`** for project management: `uv init`, `uv add <pkg>`, `uv run resumint`. The `pyproject.toml` is the single source of truth for dependencies, entry points, and Python version.

```toml
[project]
name = "resumint"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "openai-agents",          # OpenAI Agents SDK
    "pydantic-settings",      # config / .env management
    "markitdown",             # PDF/DOCX/MD/TXT extraction
    "fpdf2",                  # cover letter PDF (future)
    "typer",                  # CLI
]

[project.scripts]
resumint = "resumint.main:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

No `sentence-transformers` dependency — relevance scoring is handled natively by the LLM.  
No `langchain` dependency — prompt construction is plain Python strings.

---

## 10. Implementation Order

1. `config.py` + `.env.example`
2. `parsers.py` — adapt from reference implementation
3. `latex_toolbox.py` — adapt from reference implementation (remove unused scoring hooks)
4. `utils.py` — `build_application_destination()`, `setup_run_logger()`, and helpers
5. `templates/examples/` — copy the `.tex`/`.cls` pair from `job_hunter_toolbox` (see `PROMPTS_DESIGN.md` Section 3)
6. Tool functions (`tools/` or inline in `agent.py`)
7. `prompts/prompts.py` — `Prompt` class, system prompt, `InitialMessage`
8. `agent.py`
9. `main.py`
10. `pyproject.toml` + `README.md` — `uv init`, add entry point, finalize deps with `uv add`

---

## 11. Open Questions

- **Cover letter:** `--cover-letter` flag that runs a second lightweight agent call after Loop B, using the same context? Likely yes, scope for later.
- **Streaming:** Show agent reasoning in the terminal while it runs? Good UX for a tool with ~30-60s runs.
- **Example template quality:** The compile loop's robustness depends heavily on the `.tex`/`.cls` example pairs being known-good compilable documents. They must be tested thoroughly before first use — a broken example misleads the agent.
- **Token budget for examples:** Each `.tex`/`.cls` pair adds ~800–1,200 tokens to the initial message. v1 ships with one pair (~4,000–6,000 tokens total context). Additional pairs can be added freely within budget (see `PROMPTS_DESIGN.md` Section 4 for full estimates).
