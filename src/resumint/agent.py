"""Agent configuration, tool factory, and streaming runner."""

from __future__ import annotations

import functools
import json
import logging
import os
import time

from agents import Agent, MaxTurnsExceeded, Runner, function_tool

from resumint.config import settings
from resumint.latex_toolbox import compile_resume_latex_to_pdf
from resumint.prompts.prompts import system_prompt

logger = logging.getLogger("resumint.agent")

# ---------------------------------------------------------------------------
# Phase display signals for the streaming loop
# ---------------------------------------------------------------------------

PHASE_SIGNALS: dict[str, str] = {
    "save_resume_content": "✔ Phase 1 complete — content validated",
    "write_cls_file": "◆ Phase 2 — generating document class",
    "write_tex_file": "◆ Phase 2 — generating LaTeX source",
    "compile_latex": "  → compiling...",
    "save_build_state": "✔ Build state saved",
}

# ---------------------------------------------------------------------------
# Logging wrapper for tool calls
# ---------------------------------------------------------------------------


def _log_tool_call(fn):
    """Wrap a tool function with structured per-call logging."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        tool_logger = logging.getLogger("resumint.tools")
        tool_logger.debug("CALL  %s | args=%s kwargs=%s", fn.__name__, args, kwargs)
        t0 = time.perf_counter()
        try:
            result = fn(*args, **kwargs)
            tool_logger.debug(
                "RETURN %s | %.2fs | %s",
                fn.__name__,
                time.perf_counter() - t0,
                str(result)[:200],
            )
            return result
        except Exception as exc:
            tool_logger.error("ERROR  %s | %s", fn.__name__, exc)
            raise

    return wrapper


# ---------------------------------------------------------------------------
# Tool factory — all tools pre-bound to the current run's output directory
# ---------------------------------------------------------------------------


def build_tools(output_dir: str) -> list:
    """Return all agent tools pre-bound to this run's output directory."""

    @function_tool
    def write_output_file(filename: str, content: str) -> str:
        """
        Write a file to the current build's output folder.
        Use for intermediate artifacts: resume_content.json, validation_report.txt,
        compile_errors.txt, build_state.json.
        Returns the full absolute path of the written file.
        """
        path = os.path.join(output_dir, filename)
        os.makedirs(output_dir, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    @function_tool
    def read_output_file(filename: str) -> str:
        """
        Read a file from the current build's output folder.
        Returns the file content as text, or the string NOT_FOUND if the file doesn't exist.
        """
        path = os.path.join(output_dir, filename)
        if not os.path.exists(path):
            return "NOT_FOUND"
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    @function_tool
    def save_resume_content(resume_json: str) -> str:
        """
        Save the final validated resume content as JSON to resume_content.json in the output folder.
        This signals the end of the content generation and validation loop — only call this
        when you are satisfied that all content is grounded in the portfolio and well-targeted.
        The JSON must be valid and match the template variable schema.
        Returns the path of the saved file, or an error string if the JSON is invalid.
        """
        try:
            data = json.loads(resume_json)
        except json.JSONDecodeError as e:
            return f"ERROR: invalid JSON — {e}"
        path = os.path.join(output_dir, "resume_content.json")
        os.makedirs(output_dir, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return path

    @function_tool
    def write_cls_file(content: str) -> str:
        """
        Write a custom LaTeX document class file as resume.cls to the output folder.
        Call this at the start of the LaTeX design phase, before write_tex_file.
        The \\documentclass{} declaration in resume.tex MUST be \\documentclass{resume} to match.
        Draw on the example .cls files provided in the initial message as reference.
        Returns the full path of the written file.
        """
        path = os.path.join(output_dir, "resume.cls")
        os.makedirs(output_dir, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

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
        path = os.path.join(output_dir, "resume.tex")
        os.makedirs(output_dir, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    @function_tool
    def read_tex_file() -> str:
        """
        Read the current contents of resume.tex from the output folder.
        Call this before making edits during the compile loop so you can see
        the full current content and identify exactly which lines to fix.
        Returns the full .tex content, or NOT_FOUND.
        """
        path = os.path.join(output_dir, "resume.tex")
        if not os.path.exists(path):
            return "NOT_FOUND"
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    @function_tool
    def compile_latex(tex_file_path: str) -> dict:
        """
        Compile a .tex file to PDF using pdflatex or xelatex (auto-detected from file content).
        Runs the compiler twice to resolve cross-references.
        Returns a dict:
          {
            "success": bool,
            "pdf_path": str | null,
            "errors": str,
            "error_lines": [int],
          }
        """
        return compile_resume_latex_to_pdf(tex_file_path)

    @function_tool
    def save_build_state(state_json: str) -> str:
        """
        Save a JSON snapshot of the current build state to build_state.json.
        Call this after completing each major phase to enable resumability.
        Recommended state structure:
          {"phase": "content_complete" | "compile_complete", "pdf_path": str | null}
        Returns the path of the saved file.
        """
        try:
            data = json.loads(state_json)
        except json.JSONDecodeError as e:
            return f"ERROR: invalid JSON — {e}"
        path = os.path.join(output_dir, "build_state.json")
        os.makedirs(output_dir, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return path

    @function_tool
    def load_build_state() -> str:
        """
        Load the existing build state from build_state.json in the output folder.
        Returns the state as a JSON string, or NOT_FOUND if no state exists.
        Call this at the start of a resumed run to determine what has already been completed.
        """
        path = os.path.join(output_dir, "build_state.json")
        if not os.path.exists(path):
            return "NOT_FOUND"
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    # Apply logging wrapper and return all tools
    tools = [
        write_output_file,
        read_output_file,
        save_resume_content,
        write_cls_file,
        write_tex_file,
        read_tex_file,
        compile_latex,
        save_build_state,
        load_build_state,
    ]
    return tools


# ---------------------------------------------------------------------------
# Agent builder
# ---------------------------------------------------------------------------


def build_agent(output_dir: str, model_override: str | None = None) -> Agent:
    """Build the ResumeBuilder agent with tools pre-bound to this run's output directory."""
    tools = build_tools(output_dir)
    model = model_override or settings.default_model
    return Agent(
        name="ResumeBuilder",
        model=model,
        instructions=system_prompt.render(),
        tools=tools,
        # TODO: max_turns is not yet a supported param in all SDK versions;
        # leave it out and rely on natural termination + system prompt discipline.
    )


# ---------------------------------------------------------------------------
# Streaming runner
# ---------------------------------------------------------------------------


async def run_agent(
    agent: Agent,
    initial_message: str,
    verbose: bool = False,
) -> str:
    """
    Run the agent with live terminal streaming of tool calls and phase transitions.

    Args:
        agent: Configured Agent instance.
        initial_message: The rendered InitialMessage string.
        verbose: If True, also print agent reasoning text.

    Returns:
        The agent's final output text.
    """
    logger.info("Agent run started")
    result = Runner.run_streamed(agent, input=initial_message, max_turns=50)
    try:
        async for event in result.stream_events():
            if event.type == "raw_response_event":
                # Skip raw SSE chunks
                continue
            elif event.type == "run_item_stream_event":
                item = event.item
                # Tool call start
                if item.type == "tool_call_item" and hasattr(item, "raw_item"):
                    tool_name = getattr(item.raw_item, "name", None)
                    if tool_name:
                        logger.info("Tool call: %s", tool_name)
                        label = PHASE_SIGNALS.get(tool_name, f"  → {tool_name}")
                        print(label)
                # Tool output
                elif item.type == "tool_call_output_item":
                    output_str = str(getattr(item, "output", ""))[:120]
                    logger.debug("Tool output: %s", output_str)
                    print(f"    ✓ {output_str}")
                # Agent message (verbose only)
                elif verbose and item.type == "message_output_item":
                    text = getattr(item, "text", "")
                    if text:
                        print(f"  [agent] {text[:200]}")
    except MaxTurnsExceeded as exc:
        logger.error("MaxTurnsExceeded: %s", exc)
        return "Run stopped: agent exceeded maximum turns. Partial output may exist in the output directory."

    logger.info("Agent run complete")
    return result.final_output
