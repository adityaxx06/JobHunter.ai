"""Phase 7B resume tests. Fully offline — synthetic fixtures, stubbed AI.

The ai package is stubbed via sys.modules (mock.patch.dict, self-reverting)
so no real provider module is ever imported and no quota is spent. Fixtures
use fake names only — never a real personal resume.
"""

import io
import json
import sys
import zipfile
from unittest import mock

PID = "11111111-1111-1111-1111-111111111111"

TXT_RESUME = """Test Candidate
MCA, Fresher

Skills: Java, Python, SQL, java,  Spring Boot

Experience:
AI/ML Intern at Demo Labs (2024)
"""

PDF_TEXT = "Test Candidate\nMCA Fresher\nSkills: Java, Python, SQL"


def _docx_bytes(paragraphs):
    body = "".join(
        f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body></w:document>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", document)
        archive.writestr("[Content_Types].xml", "<Types/>")
    return buffer.getvalue()


def _pdf_bytes(text):
    import fitz

    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    data = document.tobytes()
    document.close()
    return data


class _StubRequest:
    def __init__(self, prompt="", schema_name=""):
        self.prompt = prompt
        self.schema_name = schema_name


class _StubResponse:
    def __init__(self, text=""):
        self.text = text


class _StubGeminiError(Exception):
    def __init__(self, kind="server", detail=""):
        super().__init__(f"gemini {kind}")
        self.kind = kind


class _FakeGemini:
    """Scripted stand-in: configured flag + canned payloads/failures."""

    def __init__(self, script, configured=True):
        self.script = list(script)
        self.configured = configured
        self.calls = 0

    def is_configured(self):
        return self.configured

    def generate(self, request):
        self.calls += 1
        assert isinstance(request.prompt, str) and "RESUME TEXT" in request.prompt
        action = self.script.pop(0) if self.script else {}
        if isinstance(action, Exception):
            raise action
        return _StubResponse(action if isinstance(action, str) else json.dumps(action))


def _stub_ai(monkeypatch, fake):
    """Install stub ai modules (reverted after the test — zero residue)."""
    import types

    prompts = types.ModuleType("ai.prompts.resume_intelligence")
    prompts.build_resume_prompt = lambda text: f"SYSTEM\n\nRESUME TEXT (untrusted data):\n{text[:50]}"
    base = types.ModuleType("ai.providers.base")
    base.AIRequest = _StubRequest
    gemini = types.ModuleType("ai.providers.gemini")
    gemini.GeminiError = _StubGeminiError
    gemini.GeminiProvider = lambda *a, **k: fake
    monkeypatch.setitem(sys.modules, "ai.prompts.resume_intelligence", prompts)
    monkeypatch.setitem(sys.modules, "ai.providers.base", base)
    monkeypatch.setitem(sys.modules, "ai.providers.gemini", gemini)


def _intel(**overrides):
    payload = {
        "full_name": "Test Candidate",
        "email": None,
        "phone": None,
        "education": ["MCA"],
        "experience": [{"title": "AI/ML Intern", "organization": "Demo Labs", "duration": "2024"}],
        "skills": [{"name": "Java"}, {"name": "python"}, {"name": "JAVA"}, {"name": "JavaScript"}],
        "projects": [],
        "certifications": [],
        "target_roles": ["Java Backend Developer"],
        "experience_level": "Fresher / Student",
        "summary": None,
    }
    payload.update(overrides)
    return payload


def _client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


# --- file validation ------------------------------------------------------------------


def test_rejects_unsupported_extension():
    from app.services import resume_service as service

    try:
        service.validate_upload("resume.exe", "application/octet-stream", 100)
        raise AssertionError("must reject")
    except service.ResumeError as exc:
        assert exc.status == 422


def test_rejects_mime_mismatch_empty_and_oversize(monkeypatch):
    from app.services import resume_service as service

    try:
        service.validate_upload("r.pdf", "image/png", 100)
        raise AssertionError("must reject mime")
    except service.ResumeError as exc:
        assert exc.status == 422
    try:
        service.validate_upload("r.txt", "text/plain", 0)
        raise AssertionError("must reject empty")
    except service.ResumeError as exc:
        assert exc.status == 422
    monkeypatch.setattr(service, "MAX_RESUME_BYTES", 10)
    try:
        service.validate_upload("r.txt", "text/plain", 11)
        raise AssertionError("must reject oversize")
    except service.ResumeError as exc:
        assert exc.status == 413
    assert service.validate_upload("r.pdf", "application/octet-stream", 10) == ".pdf"


# --- extraction --------------------------------------------------------------------------


def test_txt_docx_pdf_extraction():
    from app.services import resume_service as service

    text = service.extract_text(TXT_RESUME.encode("utf-8"), ".txt")
    assert "Test Candidate" in text and "Spring Boot" in text
    docx = service.extract_text(_docx_bytes(["Test Candidate", "Skills: Java, SQL"]), ".docx")
    assert "Test Candidate" in docx and "SQL" in docx
    pdf = service.extract_text(_pdf_bytes(PDF_TEXT), ".pdf")
    assert "Test Candidate" in pdf and "SQL" in pdf


def test_malformed_and_empty_extraction_rejected():
    from app.services import resume_service as service

    for extension, data in [
        (".pdf", b"%PDF-1.4\n%not-a-real-pdf"),
        (".docx", b"PK definitely not a zip"),
        (".txt", b"   \n  "),
        (".pdf", _pdf_bytes("   ")),
    ]:
        try:
            service.extract_text(data, extension)
            raise AssertionError(f"must reject {extension}")
        except service.ResumeError as exc:
            assert exc.status == 422
            assert "readable text" in str(exc) or "Malformed" in str(exc)


# --- parser ---------------------------------------------------------------------------------


def test_valid_response_normalizes_skills(monkeypatch):
    from app.services import resume_service as service

    fake = _FakeGemini([_intel()])
    _stub_ai(monkeypatch, fake)
    extraction, error = service.parse_resume_text("Test Candidate ... Java ...")
    assert error is None and fake.calls == 1
    names = [s.name for s in extraction.skills]
    assert names.count("Java") == 1  # java/JAVA collapsed
    assert "JavaScript" in names  # distinct tech preserved
    assert extraction.target_roles == ["Java Backend Developer"]
    assert extraction.experience_level == "Fresher / Student"


def test_missing_fields_invalid_json_and_schema_rejected(monkeypatch):
    from app.services import resume_service as service

    fake = _FakeGemini([{"full_name": "Test Candidate"}, "{oops", {"skills": [{"name": 42}]}])
    _stub_ai(monkeypatch, fake)
    extraction, error = service.parse_resume_text("text")
    assert extraction.full_name == "Test Candidate" and extraction.skills == []
    assert error is None  # sparse but valid
    _, error = service.parse_resume_text("text")
    assert error is not None and error.code == "invalid_output"
    _, error = service.parse_resume_text("text")
    assert error is not None and error.code == "invalid_output"


def test_gemini_failure_is_controlled(monkeypatch):
    from app.services import resume_service as service

    fake = _FakeGemini([_StubGeminiError("server", "HTTP 503")], configured=True)
    _stub_ai(monkeypatch, fake)
    extraction, error = service.parse_resume_text("text")
    assert extraction is None and error.code == "ai_unavailable"
    assert "temporarily unavailable" in error.message
    assert "503" not in error.message  # kinds only, no internals


def test_unconfigured_provider_is_controlled(monkeypatch):
    from app.services import resume_service as service

    _stub_ai(monkeypatch, _FakeGemini([], configured=False))
    extraction, error = service.parse_resume_text("text")
    assert extraction is None and error.code == "ai_unavailable"


# --- endpoint ----------------------------------------------------------------------------------


def test_parse_endpoint_success_and_never_mutates(monkeypatch):
    from app.db.repositories import profiles as repo
    from app.services import resume_service as service

    fake = _FakeGemini([_intel()])
    _stub_ai(monkeypatch, fake)
    client = _client()
    with mock.patch.object(repo, "get_profile", return_value={"id": PID}), mock.patch.object(
        repo, "update_profile", side_effect=AssertionError("must not mutate")), mock.patch.object(
        repo, "add_profile_skill", side_effect=AssertionError("must not mutate")), mock.patch.object(
        repo, "add_target_role", side_effect=AssertionError("must not mutate")):
        response = client.post(
            f"/api/profiles/{PID}/resume/parse",
            files={"file": ("resume.txt", TXT_RESUME.encode("utf-8"), "text/plain")},
        )
    assert response.status_code == 200, response.text[:200]
    body = response.json()
    assert [s["name"] for s in body["extraction"]["skills"]].count("Java") == 1
    assert body["extraction"]["target_roles"] == ["Java Backend Developer"]
    assert body["parse_error"] is None
    assert body["meta"]["file_type"] == ".txt" and body["meta"]["text_chars"] > 0
    dumped = json.dumps(body)
    assert "Spring Boot" not in dumped  # raw resume text never echoed
    assert "prompt" not in dumped


def test_parse_endpoint_validation_and_ai_errors(monkeypatch):
    from app.db.repositories import profiles as repo

    client = _client()
    with mock.patch.object(repo, "get_profile", return_value={"id": PID}):
        assert client.post(f"/api/profiles/{PID}/resume/parse",
                           files={"file": ("r.exe", b"data", "application/octet-stream")}).status_code == 422
        assert client.post(f"/api/profiles/{PID}/resume/parse",
                           files={"file": ("r.txt", b"", "text/plain")}).status_code == 422
        assert client.post(f"/api/profiles/{PID}/resume/parse",
                           files={"file": ("r.txt", b"%%% $$$ ###", "text/plain")}).status_code == 422
    with mock.patch.object(repo, "get_profile", return_value=None):
        assert client.post(f"/api/profiles/{PID}/resume/parse",
                           files={"file": ("r.txt", b"hi", "text/plain")}).status_code == 404
    assert client.post("/api/profiles/not-a-uuid/resume/parse",
                       files={"file": ("r.txt", b"hi", "text/plain")}).status_code == 422
    _stub_ai(monkeypatch, _FakeGemini([_StubGeminiError("server")]))
    with mock.patch.object(repo, "get_profile", return_value={"id": PID}):
        response = client.post(f"/api/profiles/{PID}/resume/parse",
                               files={"file": ("r.txt", TXT_RESUME.encode(), "text/plain")})
    assert response.status_code == 200
    body = response.json()
    assert body["extraction"] is None and body["parse_error"]["code"] == "ai_unavailable"


def test_parse_endpoint_oversize_and_pdf(monkeypatch):
    from app.db.repositories import profiles as repo
    from app.services import resume_service as service

    _stub_ai(monkeypatch, _FakeGemini([_intel()]))
    client = _client()
    monkeypatch.setattr(service, "MAX_RESUME_BYTES", 10)
    with mock.patch.object(repo, "get_profile", return_value={"id": PID}):
        assert client.post(f"/api/profiles/{PID}/resume/parse",
                           files={"file": ("r.txt", b"x" * 11, "text/plain")}).status_code == 413
    monkeypatch.setattr(service, "MAX_RESUME_BYTES", 5 * 1024 * 1024)
    with mock.patch.object(repo, "get_profile", return_value={"id": PID}):
        response = client.post(f"/api/profiles/{PID}/resume/parse",
                               files={"file": ("r.pdf", _pdf_bytes(PDF_TEXT), "application/pdf")})
    assert response.status_code == 200
    assert response.json()["extraction"]["full_name"] == "Test Candidate"


def test_zero_gemini_modules_after_resume_tests():
    """Stub hygiene: real provider modules must never leak into sys.modules."""
    assert "ai.providers.gemini" not in sys.modules
    assert "ai.providers" not in sys.modules
