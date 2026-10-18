"""Resume upload -> extract -> parse service (Phase 7B, backend-side).

In-memory only: uploaded bytes are validated, text-extracted, optionally
sent to Gemini for structuring, then discarded — nothing is written to disk,
no resume table exists, and the profile is never touched here. Approval
happens later through the existing profile CRUD endpoints.

Privacy: logs carry extension/size/counts only — never filenames, text,
prompts, responses, or keys. Errors carry kinds, never content.
"""

import io
import json
import logging
import re
import zipfile
import xml.etree.ElementTree as ET

from app.schemas.resume import ResumeExtraction, ResumeParseError, ResumeSkill

logger = logging.getLogger("ai-jobhunter.resume")

#: Hard upload cap (consistent with the 5 MB response caps elsewhere).
MAX_RESUME_BYTES = 5 * 1024 * 1024
#: Bound PDF page walks (pathological files stay cheap).
MAX_PDF_PAGES = 20
#: Prompt-bound resume text (documented truncation, counted in meta).
MAX_PROMPT_CHARS = 12000
#: Output list caps (bounded payloads, bounded UI).
MAX_SKILLS = 80
MAX_ROLES = 20
MAX_TEXT_ITEMS = 40

_ALLOWED_EXTENSIONS = {
    ".pdf": ("application/pdf",),
    ".docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document",),
    ".txt": ("text/plain",),
}
_OCTET_STREAM = "application/octet-stream"

_WS = re.compile(r"\s+")


class ResumeError(Exception):
    """User-safe upload/extraction failure (kind + clean message only)."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


def validate_upload(filename: object, content_type: object, size: int) -> str:
    """Check extension/MIME/size/emptiness. Returns the extension (raises ResumeError)."""
    name = filename if isinstance(filename, str) else ""
    lowered = name.lower()
    extension = next((ext for ext in _ALLOWED_EXTENSIONS if lowered.endswith(ext)), "")
    if not extension:
        raise ResumeError(422, "Unsupported file type. Upload a PDF, DOCX, or TXT resume.")
    mime = (content_type or "").strip().lower().split(";")[0]
    allowed_mimes = _ALLOWED_EXTENSIONS[extension]
    if mime and mime not in allowed_mimes and mime != _OCTET_STREAM:
        raise ResumeError(422, "File content does not match its type. Upload a PDF, DOCX, or TXT resume.")
    if size <= 0:
        raise ResumeError(422, "Empty file. Upload a resume with readable content.")
    if size > MAX_RESUME_BYTES:
        raise ResumeError(413, "File too large. Resumes must be 5 MB or smaller.")
    return extension


def _clean_text(text: object) -> str:
    """Normalize line endings/whitespace, keep section boundaries."""
    if not isinstance(text, str):
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [_WS.sub(" ", line).strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line)


def _require_readable(text: str) -> str:
    """Reject empty/scanned-style output without echoing content."""
    if not text or not re.search(r"[A-Za-z0-9]{3,}", text):
        raise ResumeError(422, "Could not extract readable text from this resume.")
    return text


def extract_txt(data: bytes) -> str:
    """Decode plain text (UTF-8-SIG, latin-1 fallback for odd encodings)."""
    try:
        text = data.decode("utf-8-sig")
    except (UnicodeDecodeError, ValueError):
        text = data.decode("latin-1")
    return _require_readable(_clean_text(text))


def extract_docx(data: bytes) -> str:
    """Paragraph text from OOXML (stdlib zip+xml — no new dependency)."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            try:
                document = archive.read("word/document.xml")
            except KeyError:
                raise ResumeError(422, "Malformed resume file. Upload a valid DOCX resume.")
    except zipfile.BadZipFile:
        raise ResumeError(422, "Malformed resume file. Upload a valid DOCX resume.")
    try:
        namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        root = ET.fromstring(document)
    except ET.ParseError:
        raise ResumeError(422, "Malformed resume file. Upload a valid DOCX resume.")
    parts = []
    for paragraph in root.iterfind(".//w:p", namespace):
        runs = [node.text or "" for node in paragraph.iterfind(".//w:t", namespace)]
        line = _WS.sub(" ", "".join(runs)).strip()
        if line:
            parts.append(line)
    return _require_readable(_clean_text("\n".join(parts)))


def extract_pdf(data: bytes) -> str:
    """Text-layer text from a PDF (scanned/image-only PDFs yield no text)."""
    try:
        import fitz  # local import: PyMuPDF is an extraction-only dependency
    except ImportError:
        raise ResumeError(503, "PDF extraction is temporarily unavailable.")
    try:
        with fitz.open(stream=data, filetype="pdf") as document:
            if document.page_count > MAX_PDF_PAGES:
                raise ResumeError(422, "Resume has too many pages. Upload a concise resume.")
            parts = [page.get_text() or "" for page in document]
    except ResumeError:
        raise
    except Exception:
        raise ResumeError(422, "Malformed resume file. Upload a valid PDF resume.")
    return _require_readable(_clean_text("\n".join(parts)))


def extract_text(data: bytes, extension: str) -> str:
    """Dispatch bytes -> text by validated extension."""
    if extension == ".pdf":
        return extract_pdf(data)
    if extension == ".docx":
        return extract_docx(data)
    return extract_txt(data)


def _dedupe_names(values: object, limit: int) -> list:
    """Strip/collapse whitespace, drop empties, case-insensitive dedupe.

    First-seen display form wins; distinct technologies never merged
    ("Java" vs "JavaScript" stay separate — only exact matches collapse).
    """
    seen = set()
    cleaned = []
    items = values if isinstance(values, list) else []
    for value in items:
        name = value.get("name") if isinstance(value, dict) else value
        if not isinstance(name, str):
            continue
        collapsed = _WS.sub(" ", name).strip()
        if not collapsed or len(collapsed) > 120:
            continue
        key = collapsed.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(collapsed)
        if len(cleaned) >= limit:
            break
    return cleaned


def normalize_extraction(raw: dict) -> ResumeExtraction:
    """Validate AI output and normalize skill/role lists (raises on invalid)."""
    try:
        parsed = ResumeExtraction.model_validate(raw if isinstance(raw, dict) else {})
    except Exception as exc:
        raise ResumeError(422, f"Resume analysis returned an unusable result ({type(exc).__name__}).")
    skills = _dedupe_names([s.model_dump() for s in parsed.skills], MAX_SKILLS)
    parsed.skills = [ResumeSkill(name=name) for name in skills]
    parsed.target_roles = _dedupe_names(parsed.target_roles, MAX_ROLES)[:MAX_ROLES]
    parsed.education = _dedupe_names(parsed.education, MAX_TEXT_ITEMS)
    parsed.projects = _dedupe_names(parsed.projects, MAX_TEXT_ITEMS)
    parsed.certifications = _dedupe_names(parsed.certifications, MAX_TEXT_ITEMS)
    return parsed


def parse_resume_text(text: str):
    """Structure resume text via the existing Gemini abstraction (lazy import).

    Returns (ResumeExtraction | None, ResumeParseError | None). The ai package
    is imported here — never at module top — so non-AI paths never load it.
    """
    from ai.prompts.resume_intelligence import build_resume_prompt
    from ai.providers.base import AIRequest
    from ai.providers.gemini import GeminiError, GeminiProvider

    provider = GeminiProvider()
    if not provider.is_configured():
        return None, ResumeParseError(
            code="ai_unavailable",
            message="Resume text was extracted, but AI analysis is not configured.",
        )
    try:
        response = provider.generate(AIRequest(prompt=build_resume_prompt(text), schema_name="resume_extraction"))
        payload = json.loads(response.text)
    except GeminiError as exc:
        logger.warning("resume parse: gemini %s", exc.kind)
        return None, ResumeParseError(
            code="ai_unavailable",
            message="Resume text was extracted, but AI analysis is temporarily unavailable.",
        )
    except Exception as exc:
        logger.warning("resume parse: bad model output (%s)", type(exc).__name__)
        return None, ResumeParseError(code="invalid_output", message="Resume analysis returned an unusable result.")
    try:
        return normalize_extraction(payload), None
    except ResumeError:
        logger.warning("resume parse: schema validation failed")
        return None, ResumeParseError(code="invalid_output", message="Resume analysis returned an unusable result.")
