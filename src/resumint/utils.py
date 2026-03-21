"""Utility functions: output folder creation, run logger setup."""

import json
import logging
import os
import re
from datetime import datetime


def build_application_destination(
    company_name: str,
    job_title: str,
    output_destination: str = "output_files",
    timestamp: str | None = None,
) -> str:
    """
    Create the standard output directory: <output>/<Company>/<JobTitle15>_<timestamp>.

    Args:
        company_name: Company name from the job description.
        job_title: Job title from the job description.
        output_destination: Root output directory.
        timestamp: Optional override; defaults to now in YYYYMMDDHHmmSS format.

    Returns:
        Absolute path to the created directory.
    """

    def _clean(value: str) -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9]+", "", value.title().replace(" ", "").strip())
        if not cleaned:
            raise ValueError(
                "Value must contain at least one alphanumeric character after cleaning."
            )
        return cleaned

    if not company_name or not job_title:
        raise ValueError(
            "company_name and job_title are required to build an application destination."
        )

    normalized_company = _clean(company_name)
    normalized_job = _clean(job_title)[:15]
    run_timestamp = timestamp or datetime.now().strftime(r"%Y%m%d%H%M%S")

    destination_dir = os.path.join(
        output_destination,
        normalized_company,
        f"{normalized_job}_{run_timestamp}",
    )
    os.makedirs(destination_dir, exist_ok=True)
    return destination_dir


def setup_run_logger(
    log_path: str | None = None,
    level: str = "INFO",
) -> None:
    """
    Configure the 'resumint' logger hierarchy.

    Attaches a StreamHandler (always) and a FileHandler (if log_path is given)
    at the specified level.
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    root_logger = logging.getLogger("resumint")
    root_logger.setLevel(numeric_level)

    # Avoid duplicate handlers on repeated calls
    root_logger.handlers.clear()

    fmt = logging.Formatter(
        "%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(numeric_level)
    stream_handler.setFormatter(fmt)
    root_logger.addHandler(stream_handler)

    if log_path:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(fmt)
        root_logger.addHandler(file_handler)


def build_final_summary(output_dir: str) -> str:
    """
    Assemble the final summary printed after the agent run completes.

    Reads build_state.json and checks for validation_report.txt / compile_errors.txt.
    """
    lines = ["✔ resumint complete"]

    # Check for PDF
    pdf_path = os.path.join(output_dir, "resume.pdf")
    if os.path.exists(pdf_path):
        lines.append(f"  PDF:      {pdf_path}")
    else:
        lines.append("  PDF:      (not found — compilation may have failed)")

    # Read build state for compile attempts
    state_path = os.path.join(output_dir, "build_state.json")
    if os.path.exists(state_path):
        try:
            with open(state_path, "r") as f:
                state = json.load(f)
            if "compile_attempts" in state:
                lines.append(f"  Compiled: {state['compile_attempts']} attempts")
        except (json.JSONDecodeError, OSError):
            pass

    # Validation gaps
    report_path = os.path.join(output_dir, "validation_report.txt")
    if os.path.exists(report_path):
        lines.append(f"  Gaps:     see {report_path}")

    # Compile errors
    errors_path = os.path.join(output_dir, "compile_errors.txt")
    if os.path.exists(errors_path):
        lines.append(f"  Errors:   see {errors_path}")

    # Run log
    log_path = os.path.join(output_dir, "run.log")
    if os.path.exists(log_path):
        lines.append(f"  Log:      {log_path}")

    return "\n".join(lines)
