# Books connector

EPUB and PDF ingestion for the knowledge-engine pipeline (#521).

## What it does

Reads a book file and emits **one `Document` per chapter/section** so that RAG
retrieval can cite an answer to "chapter 3, section 2" rather than just "the
book". Each document carries a `section_path` breadcrumb in its `metadata`.

```
book.epub  ->  BookConnector.harvest()  ->  Document(source_type="book", metadata={"section_path": ["Part I", "Chapter 3"]}, ...)
```

## Usage

```python
from src.ingestion.connectors import get_connector

connector = get_connector("book")
for doc in connector.harvest(["path/to/book.epub", "path/to/book.pdf"]):
    print(doc.title, doc.metadata["section_path"])
    # "The Pragmatic Programmer › Chapter 3 › The Basic Tools" | ["Chapter 3", "The Basic Tools"]
```

### Structure-aware chunking

After harvesting, pass each document's section tree through `chunk_document` for
citation-level RAG chunks:

```python
from services.rag.chunking import chunk_document, DocumentSection

# If you want chunks within a section (for very long chapters):
chunks = chunk_document(
    [DocumentSection(title=doc.title, text=doc.content)],
    metadata={"document_id": doc.document_id, "section_path": doc.metadata["section_path"]},
)
# chunks[0]["path"] == ["Chapter 3", "The Basic Tools"]
```

## Extraction chain

| Format | Backend         | Notes                                                    |
|--------|----------------|----------------------------------------------------------|
| EPUB   | `ebooklib`      | Full ToC + per-chapter HTML; best structure              |
| EPUB   | stdlib zip+XML  | Fallback: NCX nav → spine; works without `ebooklib`      |
| PDF    | PyMuPDF (`fitz`)| Bookmark outline → chapter tree; best for tagged PDFs    |
| PDF    | `pdfminer.six`  | Pure-Python text extraction; heuristic heading split     |
| PDF    | `pytesseract`   | OCR fallback for scanned/image-only PDFs                 |

All backends are optional — the connector degrades gracefully when a library is
not installed, falling to the next level.

## Optional dependencies

```
pip install ebooklib PyMuPDF pdfminer.six pytesseract pdf2image
```

OCR also requires system packages: `tesseract` and `poppler-utils`.

## Document metadata fields

| Field                        | Description                                      |
|------------------------------|--------------------------------------------------|
| `metadata["book_title"]`     | Full book title                                  |
| `metadata["book_id"]`        | Stable `isbn:…` or `book:<hash>` identifier      |
| `metadata["section_path"]`   | Breadcrumb list, e.g. `["Part I", "Chapter 3"]`  |
| `metadata["section_level"]`  | Depth (0 = part, 1 = chapter, 2 = section, …)    |
| `metadata["format"]`         | `"epub"` or `"pdf"`                              |
| `metadata["extractor"]`      | Which backend extracted the text                 |
| `content_ref`                | `file:///path/to/book.epub#part-i/chapter-3` URI |
