# Job Metadata Extraction

**Project:** resumint
**Spec date:** 2026-03-23
**Status:** Planned
**Related:** `PROJECT_SPEC.md`, `AGENT_DESIGN.md`

---

## 1. Problem

`main.py` currently derives the company name and job title from a heuristic
(`_extract_company_and_title`) that reads the first two non-empty lines of the
job text and splits on common separators (`|`, `—`, `,`, etc.). This fails
reliably: job postings have no consistent structure — the first lines may be an
ATS portal header, a salary band, a requisition ID, or the posting platform's
branding.

The values are used to name the output folder
(`output_files/{Company}/{JobTitle15}_{ts}/`) and are the natural first record
in a planned audit database. They need to be accurate.

---

## 2. Design

### 2.1 Scope of this spec

This spec covers only a **pre-flight extraction step** that runs before the
main agent, replaces the broken heuristic, and produces a small structured
record that can be written to disk and later persisted to a database.

It is explicitly **not** the content-extraction pass described in
`PROJECT_SPEC.md §3.1`. That principle ("no dedicated extraction step for
resume content") still holds. This extraction is about _job metadata for
tooling purposes_ (folder naming, auditing), not about building resume content.

### 2.2 New module: `src/resumint/extractors.py`

One file owns the `JobMetadata` model and the extraction function.

```python
# src/resumint/extractors.py

from __future__ import annotations
import logging
from pydantic import BaseModel, Field
from openai import OpenAI

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
```

### 2.3 Fallback values

When `company_name` or `job_title` come back empty (either from a partial LLM
response or an exception), `build_application_destination` already handles
empty strings by raising a `ValueError`. The caller in `main.py` should
substitute explicit fallbacks before passing to that function:

```python
company = metadata.company_name or "Unknown"
title = metadata.job_title or "Resume"
```

This matches the behaviour of the old heuristic and keeps the folder naming
consistent.

### 2.4 Model and configuration

Add one new field to `config.py`:

```python
class Settings(BaseSettings):
    ...
    extraction_model: str = "gpt-4o-mini"   # model used for pre-flight metadata extraction
```

If `extraction_model` is set to an empty string in `.env`, fall back to
`default_model` at the call site in `main.py`:

```python
extraction_model = settings.extraction_model or settings.default_model
metadata = extract_job_metadata(
    job_text=job_text,
    model=extraction_model,
    api_key=settings.openai_api_key,
)
```

The extraction call is intentionally split from `default_model`. The main agent
run may use `gpt-4o`; the metadata extraction does not need that capability and
`gpt-4o-mini` is faster and cheaper for a one-shot structured parse.

The CLI's existing `--model` flag overrides `default_model` only. It does not
affect `extraction_model`. A separate `--extraction-model` flag is not needed
for v1 — `.env` override is sufficient.

---

## 3. Changes to `main.py`

### 3.1 Replace the heuristic call

Remove `_extract_company_and_title` and its call site. Replace with:

```python
from resumint.extractors import extract_job_metadata

# after job_text is available, before build_application_destination:
metadata = extract_job_metadata(
    job_text=job_text,
    model=settings.extraction_model or settings.default_model,
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
```

### 3.2 Write `job_metadata.json` to the output folder

Immediately after `out_dir` is known (and the logger is re-configured with the
file handler), write the extracted metadata to disk:

```python
import json, os

metadata_path = os.path.join(out_dir, "job_metadata.json")
with open(metadata_path, "w", encoding="utf-8") as f:
    json.dump(metadata.model_dump(), f, indent=2, ensure_ascii=False)
```

This file is:
- Useful immediately for debugging and auditing, even before any database exists
- The natural source record when SQLite persistence is added (see §4)
- Consistent with how other intermediate artifacts are written in this project

### 3.3 Updated flow in `main.py`

The sequence in the non-resume-from path becomes:

```
1. setup_run_logger (console only)
2. Parse documents (job_text, portfolio_docs)
3. extract_job_metadata  ← new, replaces heuristic
4. build_application_destination
5. setup_run_logger (add file handler now that out_dir is known)
6. Write job_metadata.json  ← new
7. Assemble InitialMessage
8. build_agent / run_agent
9. cleanup, interactive gate, final summary
```

---

## 4. Output folder artifacts update

Add `job_metadata.json` to the documented output folder contents
(`PROJECT_SPEC.md §8`):

```
output_files/{Company}/{JobTitle15}_{ts}/
├── job_metadata.json         ← extracted company, title, and future metadata fields
├── build_state.json
├── resume_content.json
...
```

---

## 5. SQLite bridge (future)

When a database is added, the insertion point is immediately after
`job_metadata.json` is written in step 3.2 above. The `job_runs` table
row is created at that moment — before the agent starts — so even interrupted
runs have a record.

Suggested table shape (not final, for planning purposes only):

```
job_runs
  id               INTEGER PRIMARY KEY
  run_at           TEXT          (ISO-8601 timestamp)
  company_name     TEXT
  job_title        TEXT
  output_dir       TEXT          (absolute path to run folder)
  model            TEXT          (settings.default_model for this run)
  status           TEXT          (running | complete | interrupted | failed)
  pdf_path         TEXT          (null until compiled)
  compile_attempts INTEGER       (null until Loop B runs)
```

Additional fields extracted by `JobMetadata` (e.g. `location`, `seniority_level`)
map directly to columns on this table. Adding a new field to `JobMetadata` and
writing it to `job_metadata.json` is the only change needed on the extraction
side; the database migration is a separate concern.

---

## 6. File changes summary

| File | Change |
|---|---|
| `src/resumint/extractors.py` | **New.** `JobMetadata` model + `extract_job_metadata()` |
| `src/resumint/config.py` | Add `extraction_model: str = "gpt-4o-mini"` |
| `src/resumint/main.py` | Replace `_extract_company_and_title` heuristic; write `job_metadata.json` |
| `dev/specs/PROJECT_SPEC.md` | Add `job_metadata.json` to §8 output folder artifact list |
