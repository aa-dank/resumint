# Build Journal

## Entry 1 — Initial Build (2026-03-19)

### How the project was built

The project was spec-driven. Three design documents were written first and committed as the sole initial commit (`2e34672`):

- `dev/specs/PROJECT_SPEC.md` — architecture, CLI, two-loop design, output folder convention
- `dev/specs/AGENT_DESIGN.md` — OpenAI Agents SDK wiring, all 9 tool specs, Prompt class, streaming runner
- `dev/specs/PROMPTS_DESIGN.md` — full system prompt text, InitialMessage format, token budget

A `dev/BUILD_PROMPT.md` kick-off prompt was included to hand the specs to a coding agent for implementation. Reference implementations from the predecessor project (`job_hunter_toolbox`) were placed in `dev/reference/` as read-only context.

The implementation was then generated from these specs. All source code (`src/`, `pyproject.toml`, `README.md`, `.env.example`, `.python-version`) is currently untracked — only the specs and templates were committed.

### Prior art and what carried over

resumint descends from `job_hunter_toolbox`, which used a sequential pipeline of ~9 separate LLM calls with Jinja2 template filling. Key things that were **kept**:

- `output_files/{Company}/{JobTitle15}_{timestamp}/` folder convention (`build_application_destination()` in `utils.py` — adapted nearly verbatim from reference)
- `parsers.py` / `load_doc_text()` — adapted almost 1:1 from reference; dropped the `read_job_text` / `read_resume_text` convenience wrappers
- `escape_for_latex()` character map — identical to reference
- `compile_resume_latex_to_pdf()` — simplified from reference: removed cls-copying logic (agent writes cls directly to output dir), removed font-checking, kept the two-pass compile + `l.<N>` error extraction
- `MarkItDown` for PDF/DOCX parsing
- `pdflatex` two-pass compilation strategy

Key things that were **intentionally dropped**:

- Jinja2 template filling — the agent generates `.tex`/`.cls` from scratch for full design freedom
- Structured extraction pass — no intermediate JSON extraction step; agent reasons over raw text
- `sentence-transformers` relevance scoring — LLM handles relevance natively
- Hidden ATS keyword injection (white text block) — replaced by prompt-driven content targeting
- `matplotlib` font manager dependency (`check_fonts_installed`, `extract_tex_font_dependencies`) — not needed without `fontspec`/xelatex
- `text_to_pdf()` utility (fpdf2-based) — `fpdf2` is still a dependency but this function was dropped; fpdf2 may be intended for future cover letter generation

### Architecture decisions worth remembering

**Tool factory pattern**: All 9 agent tools are closures inside `build_tools(output_dir)` in `agent.py`. This binds the output directory without global state. The `@function_tool` decorator comes from the Agents SDK — tool docstrings are literally the descriptions the model sees, so they double as prompt engineering.

**`save_resume_content` as a semantic gate**: This is deliberately a separate tool from `write_output_file` even though it just writes JSON. The distinct name + docstring ("only call when satisfied") creates prompt pressure that prevents the agent from saving a first draft prematurely. Same principle as "submit" vs "save draft" buttons.

**Surgical compile fixes**: The system prompt instructs the agent to never rewrite `.tex`/`.cls` from scratch after the first write — only fix the specific lines the compiler complains about. Rewriting from scratch resets all accumulated fixes and restarts the error cycle.

**No `max_turns` on the agent**: The SDK supports it but it wasn't set. The agent relies on natural termination via the system prompt's phase discipline. A `# TODO` comment notes this in `agent.py`.

**`Prompt` class wrapping static text**: The system prompt has no dynamic slots in v1. The `Prompt` wrapper with `render()` exists for consistency with `InitialMessage` and to make future dynamic slots (date, run config) non-breaking.

### LaTeX example seeding

The `templates/examples/` directory contains one `.tex`/`.cls` pair copied from a `job_hunter_toolbox` output run (CaloptimaHealth/DataOperationsE). These are loaded verbatim into the initial message as design references. The skills section in that example uses `\begin{tabular}` which is an ATS risk — this is explicitly called out in the `InitialMessage` render output so the agent avoids reproducing it.

Adding more example pairs to `templates/examples/` automatically expands the agent's design vocabulary with no code changes — `InitialMessage._load_examples()` loads all `.tex`/`.cls` from that directory.

### Token budget (estimated)

Per PROMPTS_DESIGN.md §4:
- System prompt: ~1,200 tokens
- Job description: ~500 tokens
- Portfolio (1 resume): ~1,500–2,500 tokens
- LaTeX examples (1 pair): ~800–1,200 tokens
- **Total input: ~4,000–6,000 tokens**
- Agent output per run: ~2,000–3,000 tokens
- Estimated cost per run (gpt-4o): ~$0.10–0.25

### Open items from specs

- Cover letter generation (`--cover-letter` flag) — scoped for later; `fpdf2` dependency is already present
- No tests, linting, or type-checking configured
- `max_turns` on the agent is not set (see TODO in `agent.py`)
