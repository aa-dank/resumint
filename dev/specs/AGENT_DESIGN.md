# Agent Design & Tool Specifications

**Project:** resumint  
**Related:** `PROJECT_SPEC.md`, `PROMPTS_DESIGN.md`  
**Framework:** OpenAI Agents SDK (`openai-agents`)

---

## 1. OpenAI Agents SDK — How It Works

`resumint` uses the OpenAI Agents SDK as its agent framework. Install: `pip install openai-agents`.

Core pattern:

```python
from agents import Agent, Runner, function_tool

@function_tool
def compile_latex(tex_path: str) -> dict:
    """Compile a .tex file and return success status and any errors."""
    ...

agent = Agent(
    name="ResumeBuilder",
    model="gpt-4o",
    instructions=SYSTEM_PROMPT,
    tools=[compile_latex, render_template, save_content, ...],
    max_turns=40,
)

result = await Runner.run(agent, input=initial_message)
```

**Key SDK behaviors to design around:**
- The agent runs until it stops calling tools naturally — this is the primary stopping mechanism
- `Runner.run()` returns the final text output plus the full tool call trace
- Tool docstrings become the tool description shown to the model — write them carefully
- The agent may call multiple tools in parallel when it determines order doesn't matter — tools must be safe for concurrent execution
- `max_turns` caps total tool calls to prevent runaway loops (40 is a safe ceiling for a full run)

---

## 2. Agent Configuration

```python
# agent.py

from agents import Agent, Runner
from prompts.prompts import system_prompt
from config import settings

def build_agent(output_dir: str) -> Agent:
    """Build the ResumeBuilder agent with tools pre-bound to this run's output directory."""
    tools = build_tools(output_dir)
    return Agent(
        name="ResumeBuilder",
        model=settings.default_model,
        instructions=system_prompt.render(),
        tools=tools,
        max_turns=40,
    )

async def run_agent(agent: Agent, initial_message: str) -> str:
    """Run the agent with live terminal streaming of tool calls and phase transitions."""
    result = Runner.run_streamed(agent, input=initial_message)
    async for event in result.stream_events():
        if event.type == "tool_call_start":
            label = PHASE_SIGNALS.get(event.tool_name, f"  → {event.tool_name}")
            print(label)
        elif event.type == "tool_call_output":
            print(f"    ✓ {str(event.output)[:120]}")
    return result.final_output
```

---

## 3. Tool Factory Pattern

Tools are pure functions but all implicitly share the `output_dir` for the current run. Use a factory (closure) to inject it:

```python
# agent.py

def build_tools(output_dir: str) -> list:
    """Return all agent tools pre-bound to this run's output directory."""

    @function_tool
    def write_output_file(filename: str, content: str) -> str:
        """Write a file to the current build's output folder..."""
        path = os.path.join(output_dir, filename)
        os.makedirs(output_dir, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    # ... same pattern for all tools
    return [write_output_file, read_output_file, save_resume_content, ...]
```

This avoids global state while giving every tool implicit access to the current run's folder.

### Logging Wrapper

All tool functions returned by `build_tools()` are wrapped in a logging decorator before being passed to `Agent`. The wrapper is applied inside `build_tools()` before the return statement.

```python
import logging, time, functools

def log_tool_call(fn):
    """Wrap a tool function with structured per-call logging."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        logger = logging.getLogger("resumint.tools")
        logger.debug("CALL  %s | args=%s kwargs=%s", fn.__name__, args, kwargs)
        t0 = time.perf_counter()
        try:
            result = fn(*args, **kwargs)
            logger.debug("RETURN %s | %.2fs | %s", fn.__name__, time.perf_counter() - t0, str(result)[:200])
            return result
        except Exception as exc:
            logger.error("ERROR  %s | %s", fn.__name__, exc)
            raise
    return wrapper
```

`setup_run_logger(log_path, level)` in `utils.py` attaches a `FileHandler` writing to `run.log` in the output folder and a `StreamHandler` for the terminal. Both use the log level from `Settings.log_level`, overridable via `--log-level` on the CLI.

---

## 4. Tool Specifications

### 4.1 `write_output_file`

```python
@function_tool
def write_output_file(filename: str, content: str) -> str:
    """
    Write a file to the current build's output folder.
    Use for intermediate artifacts: resume_content.json, validation_report.txt,
    compile_errors.txt, build_state.json.
    Returns the full absolute path of the written file.
    """
```

**Implementation:** `os.path.join(output_dir, filename)`, `open(..., "w")`.  
**Returns:** Absolute path string.

---

### 4.2 `read_output_file`

```python
@function_tool
def read_output_file(filename: str) -> str:
    """
    Read a file from the current build's output folder.
    Returns the file content as text, or the string NOT_FOUND if the file doesn't exist.
    """
```

---

### 4.3 `save_resume_content`

```python
@function_tool
def save_resume_content(resume_json: str) -> str:
    """
    Save the final validated resume content as JSON to resume_content.json in the output folder.
    This signals the end of the content generation and validation loop — only call this
    when you are satisfied that all content is grounded in the portfolio and well-targeted.
    The JSON must be valid and match the template variable schema.
    Returns the path of the saved file, or an error string if the JSON is invalid.
    """
```

**Implementation:** `json.loads(resume_json)` to validate, then write to `resume_content.json`.  
**Returns:** Path string, or `"ERROR: invalid JSON — <parse error message>"`.  
**Design note:** This is a semantic gate, not just a file write. Keeping it distinct from `write_output_file` signals to the agent (via the docstring) that this tool call has meaning in the workflow. The system prompt reinforces this.

---

### 4.4 `write_cls_file`

```python
@function_tool
def write_cls_file(content: str) -> str:
    """
    Write a custom LaTeX document class file as resume.cls to the output folder.
    Call this at the start of the LaTeX design phase, before write_tex_file.
    The \\documentclass{} declaration in resume.tex MUST be \\documentclass{resume} to match.
    Draw on the example .cls files provided in the initial message as reference.
    Returns the full path of the written file.
    """
```

**Implementation:** `os.path.join(output_dir, "resume.cls")`, `open(..., "w")`.  
**Returns:** Absolute path string.  
**Design note:** Paired with `write_tex_file`. The agent generates both files from scratch rather than filling a Jinja2 template, which allows unconstrained layout design at the cost of requiring the compile loop to handle agent-generated LaTeX.

---

### 4.5 `compile_latex`

```python
@function_tool
def compile_latex(tex_file_path: str) -> dict:
    """
    Compile a .tex file to PDF using pdflatex or xelatex (auto-detected from file content).
    Runs the compiler twice to resolve cross-references.
    Returns a dict:
      {
        "success": bool,
        "pdf_path": str | null,
        "errors": str,           # stderr output, truncated to 3000 chars if long
        "error_lines": [int],    # line numbers mentioned in error output (e.g. "l.42")
      }
    """
```

**Implementation:** Wraps `latex_toolbox.compile_resume_latex_to_pdf()`.  
Auto-detects `xelatex` vs `pdflatex` by checking `\usepackage{fontspec}` in the `.tex` file.  
Runs compiler twice. Parses `l.<N>` patterns from stderr to extract `error_lines`.  
**Returns:** Dict as documented.

---

### 4.6 `read_tex_file`

```python
@function_tool
def read_tex_file() -> str:
    """
    Read the current contents of resume.tex from the output folder.
    Call this before making edits during the compile loop so you can see
    the full current content and identify exactly which lines to fix.
    Returns the full .tex content, or NOT_FOUND.
    """
```

---

### 4.7 `write_tex_file`

```python
@function_tool
def write_tex_file(content: str) -> str:
    """
    Write the full LaTeX source as resume.tex to the output folder.
    Call this at the start of the LaTeX design phase (after write_cls_file) with the
    complete generated .tex content, and again during the compile loop to apply fixes.
    When fixing errors, replace the entire file content with the corrected version.
    Do not re-generate from scratch after the first write — make surgical edits only.
    Returns the path of the written file.
    """
```

---

### 4.8 `save_build_state`

```python
@function_tool
def save_build_state(state: dict) -> str:
    """
    Save a JSON snapshot of the current build state to build_state.json.
    Call this after completing each major phase to enable resumability.
    Recommended state structure:
      {"phase": "content_complete" | "compile_complete", "pdf_path": str | null}
    Returns the path of the saved file.
    """
```

---

### 4.9 `load_build_state`

```python
@function_tool
def load_build_state() -> str:
    """
    Load the existing build state from build_state.json in the output folder.
    Returns the state as a JSON string, or NOT_FOUND if no state exists.
    Call this at the start of a resumed run to determine what has already been completed.
    """
```

---

## 5. Prompt Assembly — `Prompt` Class

All prompt construction uses a `Prompt` class. A `Prompt` instance holds the template text and any named slot values, and exposes a `render()` method that returns the final string. This keeps every component of a prompt — template, slots, formatting logic — in one place rather than scattered across `main.py`.

```python
class Prompt:
    """
    A prompt template paired with the values needed to render it.
    Subclass or compose to build more complex prompt objects.
    """
    def __init__(self, template: str, **values):
        self.template = template
        self.values = values

    def render(self) -> str:
        return self.template.format_map(self.values)
```

**Both the system prompt and the initial agent message are `Prompt` instances.** The system prompt is a `Prompt` with no dynamic slots (pure static text for now, but the class makes it trivial to add context-sensitive slots later). The agent is configured as:

```python
Agent(
    name="ResumeBuilder",
    instructions=system_prompt.render(),
    ...
)
```

This is intentionally identical in behavior to passing a bare string today — the value is in consistency and extensibility, not in any current runtime difference.

### `SystemPrompt`

The system prompt lives in `prompts/prompts.py` as a module-level singleton:

```python
# prompts/prompts.py

system_prompt = Prompt(template=SYSTEM_PROMPT_TEXT)
```

The raw `SYSTEM_PROMPT_TEXT` string can live in the same file or be imported from a constants block. `system_prompt.render()` is what gets passed to `Agent`.

### `InitialMessage`

`InitialMessage` is a `Prompt` subclass (or composed instance) that assembles the per-run context the agent needs. Whatever form it takes, its `render()` MUST assemble all four of the following sections into a single string in order:

| Section | Content |
|---|---|
| Job description | Full raw text extracted from the job file |
| Portfolio documents | Each document labeled with its filename, full text appended |
| Run configuration | Output folder path, timestamp, optional resuming flag |
| LaTeX reference examples | Each `.tex` and `.cls` file from `templates/examples/`, labeled by filename, content verbatim |

How examples are loaded (eager at startup, lazy from disk, cached) is an implementation detail. What matters is that they appear in the rendered string.

**Conceptual sketch** (not prescriptive — exact class design is an implementation decision):

```python
class InitialMessage(Prompt):
    def __init__(
        self,
        job_text: str,
        portfolio_docs: list[tuple[str, str]],  # [(filename, text), ...]
        output_dir: str,
        examples: list[tuple[str, str]],        # [(filename, content), ...]
        timestamp: str,
        resuming: bool = False,
    ):
        ...

    def render(self) -> str:
        ...
```
```

---

## 6. Loop Control Strategy

Loops are emergent from the agent's tool-calling sequence — the SDK has no explicit loop primitive. The system prompt defines the phases and the tools serve as transition signals:

| Tool call | Meaning |
|---|---|
| Agent calls `save_resume_content` | Loop A complete → proceed to Loop B |
| `compile_latex` returns `success: true` | Loop B complete → proceed to review gate or finish |
| Agent calls `save_build_state({"phase": "compile_complete", ...})` | Run is fully done |

The system prompt instructs the agent to follow this sequence strictly and not skip phases.

---

## 7. Error Handling & Guardrails

| Scenario | Handling |
|---|---|
| Max content loop iterations (3) reached | Write `validation_report.txt` with remaining issues, call `save_resume_content` anyway |
| Max compile iterations (5) reached | Write `compile_errors.txt`, report in final message, halt |
| Portfolio text empty or unreadable | Agent reports in final message, does not generate a resume |
| `write_tex_file` or `write_cls_file` writes invalid LaTeX | Caught by `compile_latex` on next call — compile loop handles it |
| `save_resume_content` receives invalid JSON | Returns `"ERROR: ..."` → agent fixes and retries |
| Resume interrupted mid-run | `--resume-from` + `load_build_state` skips completed phases |

---

## 8. `main.py` Orchestration Sketch

```python
# main.py
import asyncio, os
import typer
from pathlib import Path
from markitdown import MarkItDown
from parsers import load_doc_text
from utils import build_application_destination, setup_run_logger
from prompts.prompts import InitialMessage
from agent import build_agent, run_agent

app = typer.Typer()

@app.command()
def main(
    job: Path = typer.Option(...),
    portfolio: list[Path] = typer.Option(...),
    model: str = typer.Option(None),
    interactive: bool = typer.Option(False),
    log_level: str = typer.Option("INFO"),
    resume_from: Path = typer.Option(None),
    output_dir: str = typer.Option("output_files"),
):
    setup_run_logger(log_path=None, level=log_level)
    md = MarkItDown()
    job_text = load_doc_text(str(job), md)
    portfolio_docs = [(p.name, load_doc_text(str(p), md)) for p in portfolio]

    if resume_from:
        out_dir = str(resume_from)
        resuming = True
    else:
        out_dir = build_application_destination(...)
        resuming = False

    setup_run_logger(log_path=os.path.join(out_dir, "run.log"), level=log_level)

    prompt = InitialMessage(
        job_text=job_text,
        portfolio_docs=portfolio_docs,
        output_dir=out_dir,
        timestamp=timestamp,
        resuming=resuming,
    )

    agent = build_agent(out_dir, model_override=model)
    try:
        result = asyncio.run(run_agent(agent, prompt.render()))
    except KeyboardInterrupt:
        print("\nInterrupted. Run state saved — resume with --resume-from", out_dir)
        raise SystemExit(1)
    print(result)

    if interactive:
        input("\nOpen resume.tex to edit. Press ENTER to recompile, or Ctrl+C to skip: ")
        # trigger one more compile
```
---

## 9. Terminal Display & Streaming

`resumint` streams agent output to the terminal in real time using `Runner.run_streamed()`. The experience is modelled on CLI coding agents (codex, claude code): each tool call is shown as it fires, phase transitions are announced, and a structured summary is printed at the end. A 30–60s run should feel responsive, not frozen.

### `run_agent` uses `run_streamed`

`run_agent` (Section 2) iterates over `result.stream_events()` and maps tool names to display labels via `PHASE_SIGNALS`. This mapping lives in `agent.py` (or a small `display.py` module if it grows):

```python
PHASE_SIGNALS = {
    "save_resume_content": "✔ Phase 1 complete — content validated",
    "write_cls_file":       "◆ Phase 2 — generating document class",
    "write_tex_file":       "◆ Phase 2 — generating LaTeX source",
    "compile_latex":        "  → compiling...",
    "save_build_state":     "✔ Build state saved",
}
```

Tool calls not in the map fall through to a generic `→ <tool_name>` line. Tool call output is truncated to 120 chars to avoid flooding the terminal with large `.tex` content.

### Ctrl+C interrupt

The `main()` function wraps `asyncio.run(run_agent(...))` in a `KeyboardInterrupt` handler. On interrupt, `build_state.json` will have been written by the most recent `save_build_state` call (the agent is instructed to call it after each phase). The handler prints the `--resume-from` path and exits cleanly.

### Final summary

After the agent's final output is printed, `main.py` prints a structured summary derived from the output folder contents:

```
✔ resumint complete
  PDF:      output_files/Acme/DataEngineer_20260319141022/resume.pdf
  Compiled: 2 attempts
  Gaps:     1 (see validation_report.txt)
  Log:      output_files/Acme/DataEngineer_20260319141022/run.log
```

This is assembled by reading `build_state.json` and checking for the presence of `validation_report.txt` and `compile_errors.txt` — no parsing of the agent's natural language output.

### `--verbose` flag

By default, intermediate agent reasoning text is suppressed — only tool calls are shown. Adding `--verbose` passes agent text messages through as well. This maps to watching for `event.type == "agent_message"` in the stream loop.