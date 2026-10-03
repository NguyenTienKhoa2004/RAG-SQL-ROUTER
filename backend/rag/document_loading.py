"""Read text documents directly and use OCR only when PDF text is missing."""

from pathlib import Path

from llama_index.core import SimpleDirectoryReader
from llama_index.core.readers.base import BaseReader
from llama_index.readers.file import FlatReader, PDFReader


class UploadedDocumentReader(BaseReader):
    def __init__(self):
        self._pdf_reader = PDFReader()
        self._docling_reader = None

    def load_data(self, file, extra_info=None, fs=None):
        file = Path(file)
        print(f"[Documents] Reading {file.name}", flush=True)
        try:
            if file.suffix.lower() == ".pdf":
                docs = self._pdf_reader.load_data(file, extra_info=extra_info, fs=fs)
                if docs and all(doc.text.strip() for doc in docs):
                    return docs
                print(f"[Documents] {file.name}: pages without text; trying OCR", flush=True)
            if self._docling_reader is None:
                from llama_index.readers.docling import DoclingReader

                self._docling_reader = DoclingReader()
            return self._docling_reader.load_data(file, extra_info=extra_info, fs=fs)
        except Exception as exc:
            raise ValueError(f"Could not read {file.name}: {exc}") from exc


def load_uploaded_documents(file_dir):
    reader = UploadedDocumentReader()
    text_reader = FlatReader()
    loader = SimpleDirectoryReader(
        input_dir=file_dir,
        raise_on_error=True,
        file_extractor={
            ".pdf": reader,
            ".docx": reader,
            ".pptx": reader,
            ".txt": text_reader,
            ".md": text_reader,
        },
    )
    try:
        docs = loader.load_data()
    except Exception as exc:
        # SimpleDirectoryReader wraps reader errors as the generic "Error loading file".
        details = []
        current = exc
        while current is not None:
            message = str(current)
            if message and message not in details:
                details.append(message)
            current = current.__cause__
        raise ValueError("; caused by: ".join(details)) from exc
    if not docs or not any(doc.text.strip() for doc in docs):
        raise ValueError("Uploaded documents contain no readable text.")
    print(
        f"[Documents] Loaded {len(docs)} document segment(s), "
        f"{sum(len(doc.text) for doc in docs)} characters",
        flush=True,
    )
    return docs
