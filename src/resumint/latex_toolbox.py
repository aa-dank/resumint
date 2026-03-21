"""LaTeX compilation, escaping, and cleanup utilities."""

import logging
import os
import re
import subprocess
from typing import Any, Dict, List, Union

logger = logging.getLogger(__name__)

# Type alias for recursive latex data structures
LatexData = Union[str, List["LatexData"], Dict[Any, "LatexData"]]

# Characters that must be escaped in LaTeX text content
_LATEX_SPECIAL_CHARS = {
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\^{}",
    "\\": r"\textbackslash{}",
    "\n": "\\newline%\n",
    "-": r"{-}",
    "\xa0": "~",  # Non-breaking space
    "[": r"{[}",
    "]": r"{]}",
}


def escape_for_latex(data: LatexData) -> LatexData:
    """
    Recursively escape special characters in data for LaTeX compatibility.

    Handles dicts (escapes values), lists (escapes each item), and strings.
    """
    if isinstance(data, dict):
        return {key: escape_for_latex(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [escape_for_latex(item) for item in data]
    elif isinstance(data, str):
        return "".join(_LATEX_SPECIAL_CHARS.get(c, c) for c in data)
    return data


def compile_resume_latex_to_pdf(
    tex_filepath: str,
    latex_engine: str | None = None,
) -> dict:
    """
    Compile a .tex file to PDF. Runs the compiler twice for cross-references.

    The .cls file must already be in the same directory as the .tex file.

    Args:
        tex_filepath: Absolute path to the .tex file.
        latex_engine: 'pdflatex' or 'xelatex'. Auto-detected if None.

    Returns:
        dict with keys: success (bool), pdf_path (str|None),
        errors (str), error_lines (list[int]).
    """
    output_dir = os.path.dirname(os.path.abspath(tex_filepath))
    tex_filename = os.path.basename(tex_filepath)
    base_name = os.path.splitext(tex_filename)[0]
    pdf_path = os.path.join(output_dir, f"{base_name}.pdf")

    # Auto-detect engine
    if not latex_engine:
        with open(tex_filepath, "r", encoding="utf-8") as f:
            content = f.read()
        latex_engine = "xelatex" if "\\usepackage{fontspec}" in content else "pdflatex"

    cmd = [latex_engine, "-interaction=nonstopmode", tex_filename]
    logger.info("Compiling with: %s", " ".join(cmd))

    combined_output = ""
    for pass_num in range(1, 3):
        result = subprocess.run(
            cmd,
            cwd=output_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout = result.stdout.decode(errors="replace")
        stderr = result.stderr.decode(errors="replace")
        combined_output = stdout + "\n" + stderr

        if result.returncode != 0:
            logger.error("Compilation failed on pass %d", pass_num)
            error_lines = _extract_error_lines(combined_output)
            errors = combined_output[-3000:] if len(combined_output) > 3000 else combined_output
            return {
                "success": False,
                "pdf_path": None,
                "errors": errors,
                "error_lines": error_lines,
            }
        logger.info("Pass %d succeeded", pass_num)

    return {
        "success": True,
        "pdf_path": pdf_path if os.path.exists(pdf_path) else None,
        "errors": "",
        "error_lines": [],
    }


def _extract_error_lines(output: str) -> list[int]:
    """Extract line numbers from LaTeX error output (patterns like 'l.42')."""
    return [int(m) for m in re.findall(r"l\.(\d+)", output)]


def cleanup_latex_files(output_dir: str, base_name: str = "resume") -> None:
    """Remove auxiliary files generated during LaTeX compilation."""
    extensions = [".aux", ".log", ".out", ".toc", ".synctex.gz", ".fls", ".fdb_latexmk"]
    for ext in extensions:
        aux_file = os.path.join(output_dir, base_name + ext)
        try:
            if os.path.exists(aux_file):
                os.remove(aux_file)
        except OSError as e:
            logger.warning("Could not remove %s: %s", aux_file, e)
