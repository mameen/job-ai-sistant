"""Generated artifact layout for Career Intelligence."""

from .docx_io import (
    COVER_TEMPLATE_REL,
    RESUME_TEMPLATE_REL,
    clone_and_fill_body,
    render_from_template,
    write_application_triplet,
    write_plain_docx,
)
from .naming import (
    ARTIFACT_KINDS,
    artifact_filename,
    hermes_paths,
    proposal_run_dir,
)

__all__ = [
    "ARTIFACT_KINDS",
    "COVER_TEMPLATE_REL",
    "RESUME_TEMPLATE_REL",
    "artifact_filename",
    "clone_and_fill_body",
    "hermes_paths",
    "proposal_run_dir",
    "render_from_template",
    "write_application_triplet",
    "write_plain_docx",
]
