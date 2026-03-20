# resumint — Build Kick-off Prompt

You are building **resumint**, a Python CLI tool that generates tailored, ATS-compatible resume PDFs from a job description and a portfolio of documents, using an LLM agent.

## Start here

Read [`dev/README.md`](dev/README.md) first. It maps every file in this repo and tells you what's a spec, what's a reference, and what order to read in.

## Spec files (read in this order)

1. **[`dev/specs/PROJECT_SPEC.md`](dev/specs/PROJECT_SPEC.md)** — what the tool does, the CLI interface, the two-loop agent architecture (Loop A: content; Loop B: LaTeX), the output folder layout, and the suggested project structure. This is your primary reference.

2. **[`dev/specs/AGENT_DESIGN.md`](dev/specs/AGENT_DESIGN.md)** — the OpenAI Agents SDK wiring: `build_agent`, `run_agent` (uses `Runner.run_streamed()`), the tool factory pattern, every tool spec (4.1–4.9), the `Prompt` class, `InitialMessage`, `PHASE_SIGNALS`, and the `main.py` sketch. This is the implementation blueprint.

3. **[`dev/specs/PROMPTS_DESIGN.md`](dev/specs/PROMPTS_DESIGN.md)** — the full system prompt text, the `InitialMessage` structure, LaTeX example guidance, and prompt engineering notes including token budget.

## Reference files (don't implement, just read)

- **[`dev/reference/less_basic_template.tex`](dev/reference/less_basic_template.tex)** and **[`.cls`](dev/reference/less_basic_template.cls)** — background reading on `.tex`/`.cls` structure. The agent generates from scratch; these are not templates.
- **LaTeX example pair for `templates/examples/`** — copy from the prior project (adjust path to your local clone): `<job_hunter_toolbox>/output_files/CaloptimaHealth/DataOperationsE_20260223201653/resume.tex` and `resume.cls`. See `PROMPTS_DESIGN.md` Section 3 for details and known issues.
- **[`dev/reference/latex_toolbox.py`](dev/reference/latex_toolbox.py)**, **[`parsers.py`](dev/reference/parsers.py)**, **[`utils.py`](dev/reference/utils.py)** — reference implementations. Adapt what's useful; don't copy wholesale.
- **[`dev/reference/metrics.py`](dev/reference/metrics.py)** — not used in resumint.

## What's already decided

- Use **`uv`** for project management (`uv init`, `uv add`, `uv run`). See Section 9 of `PROJECT_SPEC.md` for the full `pyproject.toml` scaffold.
- Agent generates `.tex` and `.cls` from scratch — no Jinja2, no template filling. (Examples of good `.tex`/`.cls` structure are provided to the agent)
- `Prompt` class with a `render()` method is the calling convention for all prompts.
- `Runner.run_streamed()` with `stream_events()` is the run loop — not `Runner.run()`.
- No `check_content_grounding` tool. No profiles feature.
- The suggested project structure in Section 5 of `PROJECT_SPEC.md` is a recommendation, not a mandate — use your judgment.

## Go build it

Follow the implementation order in Section 10 of `PROJECT_SPEC.md`. Start with config and parsers, end with `main.py` and packaging. The specs are complete. When something is ambiguous, prefer the simpler interpretation and leave a `# TODO` comment.
