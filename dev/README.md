# resumint — Developer Notes

## For the coding agent building this project

**Start here:** Read the files in `specs/` in this order:

1. [`specs/PROJECT_SPEC.md`](specs/PROJECT_SPEC.md) — What the project is, architecture, CLI, output structure, implementation order
2. [`specs/AGENT_DESIGN.md`](specs/AGENT_DESIGN.md) — How the OpenAI Agents SDK is used, every tool's full spec, the tool factory pattern
3. [`specs/PROMPTS_DESIGN.md`](specs/PROMPTS_DESIGN.md) — The full system prompt (a `Prompt` instance), initial message structure, LaTeX example reference conventions
4. [`specs/JOB_METADATA_EXTRACTION.md`](specs/JOB_METADATA_EXTRACTION.md) — Pre-flight structured LLM extraction of company name and job title; `JobMetadata` model; SQLite bridge notes

**Then read `reference/`** for working implementations you can adapt directly:

| File | What to use it for |
|---|---|
| `reference/less_basic_template.tex` | Reference only — the agent generates `.tex` from scratch; read this to understand the prior content schema and what produced good output |
| `reference/less_basic_template.cls` | Starting point for the example `.cls` files in `templates/examples/` — adapt the layout definitions, strip the ATS keyword block |
| `reference/latex_toolbox.py` | Adapt as `latex_toolbox.py` — the `compile_resume_latex_to_pdf`, `escape_for_latex`, and `cleanup_latex_files` functions are production-tested |
| `reference/parsers.py` | Adapt as `parsers.py` — `load_doc_text` handles PDF/DOCX/MD/TXT via MarkItDown |
| `reference/utils.py` | Pull `build_application_destination` for the output folder naming convention |
| `reference/metrics.py` | Not used in resumint — retain as reference only |

## Directory layout

```
dev/
├── README.md          ← you are here
├── specs/
│   ├── PROJECT_SPEC.md
│   ├── AGENT_DESIGN.md
│   ├── PROMPTS_DESIGN.md
│   └── JOB_METADATA_EXTRACTION.md
└── reference/         ← prior art from job_hunter_toolbox (read-only, do not edit)
    ├── less_basic_template.tex
    ├── less_basic_template.cls
    ├── latex_toolbox.py
    ├── parsers.py
    ├── utils.py
    └── metrics.py
```
