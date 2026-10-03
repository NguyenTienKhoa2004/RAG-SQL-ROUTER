import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from llama_index.core import Document

from backend.rag.document_loading import UploadedDocumentReader, load_uploaded_documents


class DocumentLoadingTests(unittest.TestCase):
    def test_text_pdf_skips_ocr_and_keeps_metadata(self):
        reader = UploadedDocumentReader()
        docs = [Document(text="Store opens at 9 AM", metadata={"page_label": "1"})]
        reader._pdf_reader = Mock()
        reader._pdf_reader.load_data.return_value = docs
        reader._docling_reader = Mock()
        self.assertEqual(reader.load_data(Path("hours.pdf")), docs)
        reader._docling_reader.load_data.assert_not_called()

    def test_pdf_with_scanned_page_uses_ocr(self):
        reader = UploadedDocumentReader()
        reader._pdf_reader = Mock()
        reader._pdf_reader.load_data.return_value = [Document(text="Text"), Document(text="")]
        reader._docling_reader = Mock()
        reader._docling_reader.load_data.return_value = [Document(text="OCR result")]
        docs = reader.load_data(Path("scan.pdf"))
        self.assertEqual(docs[0].text, "OCR result")
        reader._docling_reader.load_data.assert_called_once()

    def test_md_and_txt_preserve_vietnamese_content_without_ocr(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "hours.md").write_text("# Giờ mở cửa\nCửa hàng mở lúc 9 giờ.", encoding="utf-8")
            Path(directory, "notes.txt").write_text("Đóng lúc 18 giờ.", encoding="utf-8")
            with patch.object(UploadedDocumentReader, "load_data", side_effect=AssertionError("OCR should not run")):
                docs = load_uploaded_documents(directory)
            self.assertEqual(len(docs), 2)
            self.assertTrue(any("Cửa hàng mở lúc 9 giờ." in doc.text for doc in docs))

    def test_wrapped_error_retains_file_and_original_cause(self):
        reader = UploadedDocumentReader()
        reader._pdf_reader = Mock()
        reader._pdf_reader.load_data.side_effect = RuntimeError("PDF is encrypted")
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "locked.pdf").write_bytes(b"placeholder")
            with patch("backend.rag.document_loading.UploadedDocumentReader", return_value=reader):
                with self.assertRaisesRegex(ValueError, "locked.pdf.*PDF is encrypted"):
                    load_uploaded_documents(directory)

    def test_empty_content_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "empty.txt").write_text(" ", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "no readable text"):
                load_uploaded_documents(directory)


if __name__ == "__main__":
    unittest.main()
