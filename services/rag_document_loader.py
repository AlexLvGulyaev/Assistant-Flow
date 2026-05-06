"""Load and chunk local files (txt, md, pdf) for indexing."""

from __future__ import annotations

from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from utils.config import AppConfig


def _load_file_documents(file_path: Path) -> list[Document]:
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        loader = PyPDFLoader(str(file_path))
    elif suffix in (".txt", ".md"):
        loader = TextLoader(str(file_path), encoding="utf-8")
    else:
        raise ValueError(f"Unsupported file format: {suffix}")
    return loader.load()


def iter_supported_files(directory: Path) -> list[Path]:
    """Sorted list of .pdf / .txt / .md files under directory (recursive)."""
    directory = Path(directory)
    if not directory.is_dir():
        raise FileNotFoundError(f"Not a directory: {directory}")
    supported = {".pdf", ".txt", ".md"}
    out: list[Path] = []
    for file_path in sorted(directory.rglob("*")):
        if file_path.is_file() and file_path.suffix.lower() in supported:
            out.append(file_path)
    return out


def load_and_split_file(file_path: Path, config: AppConfig) -> list[Document]:
    """Load one file and return chunked Documents with source metadata."""
    file_path = Path(file_path)
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=config.rag_chunk_size,
        chunk_overlap=config.rag_chunk_overlap,
        length_function=len,
    )
    docs = _load_file_documents(file_path)
    for doc in docs:
        doc.metadata.setdefault("source", file_path.name)
        doc.metadata.setdefault("file_path", str(file_path.resolve()))
    return splitter.split_documents(docs)


def load_and_split_directory(
    directory: Path,
    config: AppConfig,
) -> list[Document]:
    """
    Load all supported files under directory (recursive).
    Assigns metadata['source'] to the file name for citation.
    """
    directory = Path(directory)
    if not directory.is_dir():
        raise FileNotFoundError(f"Not a directory: {directory}")

    all_chunks: list[Document] = []
    for file_path in iter_supported_files(directory):
        all_chunks.extend(load_and_split_file(file_path, config))
    return all_chunks
