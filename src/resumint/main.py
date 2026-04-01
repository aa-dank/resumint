"""CLI entry point for resumint."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from markitdown import MarkItDown

from resumint.agent import build_agent, run_agent
from resumint.config import settings
from resumint.extractors import extract_job_metadata
from resumint.latex_toolbox import cleanup_latex_files
from resumint.parsers import load_doc_text
from resumint.prompts.prompts import InitialMessage
from resumint.utils import build_application_destination, build_final_summary, setup_run_logger

app = typer.Typer(
    name="resumint",
    help="Generate tailored, ATS-compatible resume PDFs from a job description and portfolio documents.",
    add_completion=False,
)


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
        help="Pause for human review after successful compile.",
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

    # --- Interactive review gate ---
    if interactive and os.path.exists(os.path.join(out_dir, "resume.pdf")):
        typer.echo(f"\nResume compiled → {os.path.join(out_dir, 'resume.pdf')}")
        typer.echo("Open resume.tex to make edits.")
        try:
            input("Press ENTER to recompile, or Ctrl+C to skip: ")
            # Re-compile once more
            from resumint.latex_toolbox import compile_resume_latex_to_pdf

            tex_path = os.path.join(out_dir, "resume.tex")
            result_dict = compile_resume_latex_to_pdf(tex_path)
            if result_dict["success"]:
                typer.echo("✔ Recompile succeeded.")
            else:
                typer.echo(f"✘ Recompile failed: {result_dict['errors'][:200]}")
        except KeyboardInterrupt:
            typer.echo("\nSkipping recompile.")

    # --- Final summary ---
    typer.echo(f"\n{build_final_summary(out_dir)}")


if __name__ == "__main__":
    app()


