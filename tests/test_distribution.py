from pathlib import Path

from pypdf import PdfReader


PROJECT_DIR = Path(__file__).resolve().parents[1]
REFERENCE_PDF = (
    PROJECT_DIR
    / "20260813 2026年复旦大学研究生学习和申请学位基本文件选编-洁版final.pdf"
)


def test_bundled_reference_pdf_is_readable() -> None:
    assert REFERENCE_PDF.is_file()
    reader = PdfReader(REFERENCE_PDF)
    assert len(reader.pages) > 0
    assert any((page.extract_text() or "").strip() for page in reader.pages[:3])


def test_example_configuration_contains_required_user_inputs() -> None:
    example = (PROJECT_DIR / ".env.example").read_text(encoding="utf-8")
    assert "TARGET_URL=https://example.com/quiz" in example
    assert "LLM_API_KEY=your-api-key" in example
    assert "LLM_MODEL=your-model-name" in example
