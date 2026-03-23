"""Pre-flight structured extraction of job metadata from a raw job posting."""

from __future__ import annotations

import logging

from openai import OpenAI
from pydantic import BaseModel, Field

logger = logging.getLogger("resumint.extractors")

_EXTRACTION_PROMPT = """\
Extract the following metadata from the job posting below.
Return only the fields requested. If a value is genuinely not present, return
an empty string — do not guess or invent values.
"""


class JobMetadata(BaseModel):
    """
    Structured metadata extracted from a job posting.

    Designed to be extended: add new fields here as needed. Each field added
    here will automatically be requested from the model (via structured output)
    and written to job_metadata.json in the output folder.

    Future candidates: required_skills (list[str]), seniority_level (str),
    location (str), remote_policy (str), employment_type (str),
    salary_range (str).
    """

    company_name: str = Field(default="", description="The hiring company's name.")
    job_title: str = Field(default="", description="The advertised job title.")


def extract_job_metadata(
    job_text: str,
    model: str,
    api_key: str,
    max_chars: int = 6000,
) -> JobMetadata:
    """
    Run a lightweight structured-output call to extract job metadata.

    Uses the OpenAI client directly (not the Agents SDK) — this is intentional:
    it's a simple one-shot parse with a known schema, not an agentic loop.

    Falls back to empty-string defaults on any exception so it never blocks
    the main run.

    Args:
        job_text: Raw text of the job posting.
        model: Model to use. Should be a fast, cheap model — gpt-4o-mini is
               the recommended default (see config.extraction_model).
        api_key: OpenAI API key.
        max_chars: Truncation limit. Company name and job title are almost
                   always in the first portion of the posting; 6 000 chars
                   is generous and keeps token cost negligible.

    Returns:
        JobMetadata instance. Fields may be empty strings on partial failure.
    """
    client = OpenAI(api_key=api_key)
    try:
        response = client.beta.chat.completions.parse(
            model=model,
            messages=[
                {"role": "system", "content": _EXTRACTION_PROMPT},
                {"role": "user", "content": job_text[:max_chars]},
            ],
            response_format=JobMetadata,
        )
        result = response.choices[0].message.parsed
        if result is None:
            raise ValueError("Parsed result was None")
        logger.debug(
            "Extracted metadata: company=%r title=%r",
            result.company_name,
            result.job_title,
        )
        return result
    except Exception as exc:
        logger.warning("Job metadata extraction failed (%s) — using fallbacks.", exc)
        return JobMetadata()
