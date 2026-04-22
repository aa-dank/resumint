"""CLI entry point for resumint."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from markitdown import MarkItDown

from resumint.agent import build_agent, run_agent
from resumint.config import settings
from resumint.extractors import extract_job_metadata
from resumint.latex_toolbox import cleanup_latex_files, compile_resume_latex_to_pdf
from resumint.parsers import load_doc_text
from resumint.prompts.prompts import (
    InitialMessage,
    InteractiveRevisionMessage,
    review_system_prompt,
)
from resumint.utils import build_application_destination, build_final_summary, setup_run_logger

app = typer.Typer(
    name="resumint",
    help="Generate tailored, ATS-compatible resume PDFs from a job description and portfolio documents.",
    add_completion=False,
)


def _looks_like_terminal_bootstrap_input(text: str) -> bool:
    """Best-effort filter for terminal bootstrap text accidentally consumed by input()."""
    stripped = text.strip()
    if not stripped:
        return False
    lowered = stripped.lower()
    return (
        lowered.startswith("source ")
        or lowered.startswith("export ")
        or lowered.startswith("conda activate")
        or ".venv/bin/activate" in lowered
    )


def _is_content_revision_request(text: str) -> bool:
    """Heuristic for requests that change grounded resume content, not just presentation."""
    lowered = text.lower()
    content_markers = [
        "add project",
        "another project",
        "new project",
        "project",
        "bullet",
        "experience",
        "education",
        "skills",
        "achievement",
        "certification",
        "tailor",
        "taylored",
        "tailored",
        "rewrite",
        "reword",
        "wording",
        "content",
        "summary",
        "headline",
        "quantify",
        "emphasize",
        "emphasise",
        "remove",
        "add",
    ]
    return any(marker in lowered for marker in content_markers)


def _save_compile_complete_state(output_dir: str, pdf_path: str) -> None:
    """Persist compile-complete state after interactive review compiles."""
    state_path = os.path.join(output_dir, "build_state.json")
    state: dict[str, str] = {}
    if os.path.exists(state_path):
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                state = json.load(f)
        except (json.JSONDecodeError, OSError):
            state = {}
    state.update({"phase": "compile_complete", "pdf_path": pdf_path})
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def _run_interactive_review_loop(
    *,
    out_dir: str,
    job_text: str,
    job_filename: str,
    portfolio_docs: list[tuple[str, str]],
    timestamp: str,
    model: Optional[str],
    verbose: bool,
) -> None:
    """Run a conversational revision loop over the generated LaTeX files."""
    tex_path = os.path.join(out_dir, "resume.tex")
    if not os.path.exists(tex_path):
        typer.echo("\nInteractive review skipped: resume.tex was not generated.")
        return

    revision_history: list[str] = []

    typer.echo("\nInteractive review mode")
    typer.echo("Enter a revision request for the model, type `manual` to edit the files yourself, or `done` to finalize.")

    while True:
        try:
            user_input = input("Revision request / manual / done: ").strip()
        except KeyboardInterrupt:
            typer.echo("\nLeaving interactive review mode.")
            return

        if _looks_like_terminal_bootstrap_input(user_input):
            typer.echo("Ignoring terminal bootstrap input. Waiting for your review instruction.")
            continue

        if not user_input:
            typer.echo("Enter a revision request, `manual`, or `done`.")
            continue

        command = user_input.lower()

        if command in {"done", "finish", "finalize", "exit"}:
            typer.echo("Running a final compile check...")
            result = compile_resume_latex_to_pdf(tex_path)
            cleanup_latex_files(out_dir)
            if result["success"] and result["pdf_path"]:
                _save_compile_complete_state(out_dir, result["pdf_path"])
                typer.echo("✔ Final compile succeeded.")
                return
            typer.echo(f"✘ Final compile failed: {result['errors'][:200]}")
            typer.echo("Interactive review is still open so you can request another fix.")
            continue

        revision_request = user_input
        history_label = user_input
        content_revision = _is_content_revision_request(user_input)

        if command == "manual":
            typer.echo(f"Edit {os.path.join(out_dir, 'resume.tex')} and/or {os.path.join(out_dir, 'resume.cls')}, then return here.")
            try:
                ready = input("Press ENTER when ready for compile-and-fix, or type `back` to cancel: ").strip()
            except KeyboardInterrupt:
                typer.echo("\nReturning to the review prompt without compiling.")
                continue
            if ready.lower() == "back":
                continue
            revision_request = (
                "The user manually edited the current LaTeX files. Re-read the live resume.tex and resume.cls, "
                "preserve those user edits, and run the compile-and-fix loop until the PDF compiles cleanly. "
                "Only make targeted fixes needed to keep the user's intent and restore successful compilation."
            )
            history_label = "manual edit + compile/fix"
            content_revision = False

        prompt = InteractiveRevisionMessage(
            job_text=job_text,
            job_filename=job_filename,
            portfolio_docs=portfolio_docs,
            output_dir=out_dir,
            timestamp=timestamp,
            user_request=revision_request,
            revision_history=revision_history,
            content_revision=content_revision,
        )
        agent = build_agent(
            out_dir,
            model_override=model,
            instructions_prompt=review_system_prompt,
        )
        try:
            result = asyncio.run(run_agent(agent, prompt.render(), verbose=verbose))
        except KeyboardInterrupt:
            typer.echo("\nRevision interrupted. Returning to the review prompt.")
            continue

        if result:
            typer.echo(f"\n{result}")

        cleanup_latex_files(out_dir)
        revision_history.append(history_label)

        pdf_path = os.path.join(out_dir, "resume.pdf")
        if os.path.exists(pdf_path):
            typer.echo(f"Current PDF: {pdf_path}")


@app.command()
def main(
    job: Path = typer.Option(
        ...,
        help="Path to the job description file.",
        exists=True,
        readable=True,
    ),
    portfolio: list[Path] = typer.Option(
        ...,
        help="Path(s) to portfolio documents (resume, projects, etc.).",
        exists=True,
        readable=True,
    ),
    model: Optional[str] = typer.Option(
        None,
        help="LLM model override (default from .env).",
    ),
    interactive: bool = typer.Option(
        False,
        help="Enter an iterative review loop after LaTeX generation.",
    ),
    verbose: bool = typer.Option(
        False,
        help="Show agent reasoning text in addition to tool calls.",
    ),
    log_level: str = typer.Option(
        "INFO",
        help="Logging verbosity (DEBUG, INFO, WARNING, ERROR).",
    ),
    resume_from: Optional[Path] = typer.Option(
        None,
        help="Path to an existing output folder to resume from.",
    ),
    output_dir: str = typer.Option(
        "output_files",
        help="Root output directory.",
    ),
) -> None:
    """Generate a tailored resume PDF from a job description and portfolio documents."""

    # --- Early logger (console only) ---
    setup_run_logger(level=log_level)

    # --- Parse documents ---
    md = MarkItDown()
    job_text = load_doc_text(str(job), md)
    portfolio_docs = [(p.name, load_doc_text(str(p), md)) for p in portfolio]

    if not job_text.strip():
        typer.echo("Error: job description file is empty or unreadable.", err=True)
        raise typer.Exit(1)

    # --- Determine output directory ---
    timestamp = datetime.now().strftime(r"%Y%m%d%H%M%S")
    resuming = False

    if resume_from:
        out_dir = str(resume_from)
        resuming = True
    else:
        # Extract company / title via structured LLM call for accurate folder naming.
        extraction_model = settings.extraction_model or settings.default_model
        metadata = extract_job_metadata(
            job_text=job_text,
            model=extraction_model,
            api_key=settings.openai_api_key,
        )
        company = metadata.company_name or "Unknown"
        title = metadata.job_title or "Resume"
        out_dir = build_application_destination(
            company_name=company,
            job_title=title,
            output_destination=output_dir,
            timestamp=timestamp,
        )

    # --- Reconfigure logger with file handler ---
    log_path = os.path.join(out_dir, "run.log")
    setup_run_logger(log_path=log_path, level=log_level)

    # --- Write extracted metadata to disk ---
    if not resuming:
        metadata_path = os.path.join(out_dir, "job_metadata.json")
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata.model_dump(), f, indent=2, ensure_ascii=False)

    typer.echo(f"Output: {out_dir}")

    # --- Assemble initial message ---
    prompt = InitialMessage(
        job_text=job_text,
        job_filename=job.name,
        portfolio_docs=portfolio_docs,
        output_dir=out_dir,
        timestamp=timestamp,
        resuming=resuming,
    )

    # --- Build and run agent ---
    agent = build_agent(out_dir, model_override=model)
    try:
        result = asyncio.run(run_agent(agent, prompt.render(), verbose=verbose))
    except KeyboardInterrupt:
        typer.echo(f"\nInterrupted. Resume with: resumint --resume-from {out_dir}")
        raise typer.Exit(1)

    # Print agent's final message
    if result:
        typer.echo(f"\n{result}")

    # --- Cleanup LaTeX auxiliary files ---
    cleanup_latex_files(out_dir)

    # --- Move job description file into output directory ---
    job_dest = Path(out_dir) / job.name
    if job.resolve() != job_dest.resolve():
        shutil.move(str(job), str(job_dest))

    # --- Interactive review loop ---
    if interactive:
        _run_interactive_review_loop(
            out_dir=out_dir,
            job_text=job_text,
            job_filename=job.name,
            portfolio_docs=portfolio_docs,
            timestamp=timestamp,
            model=model,
            verbose=verbose,
        )

    # --- Final summary ---
    typer.echo(f"\n{build_final_summary(out_dir)}")


if __name__ == "__main__":
    app()
