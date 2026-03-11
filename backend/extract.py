"""
extract.py - Document Text Extraction with Automatic OCR Fallback
===================================================================

This module extracts text from various document formats:
- PDF: Uses PyMuPDF (fitz) for fast extraction; automatically falls back to OCR (pytesseract + pdf2image) if no text
- DOCX: Extracts paragraphs from Word documents using python-docx
- TXT: Plain text file reading (UTF-8)

Key Features:
- Automatic OCR Fallback: If PDF extraction yields no text,
  the module automatically renders PDF pages to images and uses Tesseract OCR
- Full Page OCR: All PDF pages are processed (no page limits)
- Metadata: Returns tuple (filename, text, ocr_used, page_count, ocr_truncated)
  to track extraction method and coverage
- Error Handling: Graceful failures with informative error messages

Environment / System Requirements:
  For OCR support (pytesseract + pdf2image):
  - System: tesseract-ocr, poppler-utils (linux) or poppler (Windows/Mac)
  - Python: pytesseract, pdf2image
  - Note: Tesseract must be in PATH or TESSERACT_CMD configured
"""

from typing import Optional, Tuple
import fitz  # PyMuPDF
import docx
import os

try:
    import pytesseract
    from pdf2image import convert_from_path
    OCR_AVAILABLE = True
except Exception:
    OCR_AVAILABLE = False

def extract_pdf(file_path: str) -> Optional[Tuple[str, str, bool, int, bool]]:
    """
    Extract text from a PDF file with automatic OCR fallback.
    
    Strategy:
    1. Try PyMuPDF (fitz) for fast text extraction (works for PDFs with embedded text)
    2. If no text extracted, automatically fall back to OCR (convert to images and use Tesseract)
    3. Process all pages (no page limit)
    
    Args:
        file_path (str): Path to the PDF file
        
    Returns:
        Optional[Tuple[str, str, bool, int, bool]]: (filename, text, ocr_used, page_count, ocr_truncated)
        - filename: Original filename (basename)
        - text: Extracted text content
        - ocr_used: Whether OCR was actually used
        - page_count: Total pages in PDF
        - ocr_truncated: Always False (all pages are processed)
        
        Returns None on failure
        
    Notes:
        - PyMuPDF extraction is fast (~milliseconds) but only works for searchable PDFs
        - OCR is slower (~seconds per page) but works for scanned documents
        - OCR fallback is automatically triggered if PyMuPDF extracts no text
        - OCR processes all pages (no maximum page limit)
    """
    try:
        # Step 1: Try fast text extraction with PyMuPDF
        doc = fitz.open(file_path)
        page_count = doc.page_count if hasattr(doc, 'page_count') else len(doc)
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()

        ocr_used = False
        ocr_truncated = False
        
        # Step 2: If extraction yielded no text, try OCR fallback (always enabled)
        if (not text.strip()) and OCR_AVAILABLE:
            try:
                # Convert PDF pages to images using poppler/pdf2image
                images = convert_from_path(file_path)
                total_pages = len(images)

                # Run Tesseract OCR on each image (no page limit)
                ocr_text = []
                for img in images:
                    ocr_text.append(pytesseract.image_to_string(img))
                text = "\n".join(ocr_text)
                ocr_used = True
                print(f"[INFO] OCR fallback used for '{file_path}', pages processed: {total_pages}")
            except Exception as e:
                print(f"[ERROR] OCR fallback failed for '{file_path}': {e}")

        return os.path.basename(file_path), text, ocr_used, page_count, ocr_truncated
    except Exception as e:
        print(f"[ERROR] Failed to extract PDF '{file_path}': {e}")
        return None

def extract_docx(file_path: str) -> Optional[Tuple[str, str, bool, int, bool]]:
    """
    Extract text from a DOCX (Word) file.
    
    Extracts all paragraphs from the document in order.
    
    Args:
        file_path (str): Path to the DOCX file
        
    Returns:
        Optional[Tuple[str, str, bool, int, bool]]: (filename, text, False, 0, False)
        - filename: Original filename (basename)
        - text: Extracted text content (paragraphs joined with newlines)
        - False: OCR not applicable for DOCX
        - 0: Page count not tracked for DOCX
        - False: Truncation not applicable for DOCX
        
        Returns None on failure
        
    Notes:
        - Extracts paragraphs in document order
        - Preserves paragraph structure (each paragraph on a new line)
        - Does not extract from embedded shapes, text boxes, or headers/footers
        - Tables are not specially handled (content is extracted as text)
    """
    try:
        doc = docx.Document(file_path)
        text = "\n".join([p.text for p in doc.paragraphs])
        return os.path.basename(file_path), text, False, 0, False
    except Exception as e:
        print(f"[ERROR] Failed to extract DOCX '{file_path}': {e}")
        return None

def extract_txt(file_path: str) -> Optional[Tuple[str, str, bool, int, bool]]:
    """
    Extract text from a TXT (plain text) file.
    
    Args:
        file_path (str): Path to the TXT file
        
    Returns:
        Optional[Tuple[str, str, bool, int, bool]]: (filename, text, False, 0, False)
        - filename: Original filename (basename)
        - text: File content (UTF-8 decoded)
        - False: OCR not applicable for TXT
        - 0: Page count not applicable for TXT
        - False: Truncation not applicable for TXT
        
        Returns None on failure
        
    Notes:
        - Assumes UTF-8 encoding
        - Preserves all whitespace (newlines, tabs, etc.)
        - No text extraction needed (plain text only)
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            text = f.read()
        return os.path.basename(file_path), text, False, 0, False
    except Exception as e:
        print(f"[ERROR] Failed to extract TXT '{file_path}': {e}")
        return None

def extract(file_path: str) -> Optional[Tuple[str, str, bool, int, bool]]:
    """
    Dispatch extraction based on file extension.
    
    This is the main entry point for document extraction. It determines the
    file type and calls the appropriate extraction function.
    
    Args:
        file_path (str): Path to the file to extract
        
    Returns:
        Optional[Tuple[str, str, bool, int, bool]]: (filename, text, ocr_used, page_count, ocr_truncated)
        - filename: Original filename (basename)
        - text: Extracted text content
        - ocr_used: Whether OCR was actually used (PDF only)
        - page_count: Page count (PDF only, 0 for other types)
        - ocr_truncated: Whether OCR hit the max_pages limit (always False)
        
        Returns None if file type is not supported or extraction fails
        
    Supported Formats:
        .pdf  : PDF files (with automatic OCR fallback if no text extracted)
        .docx : Microsoft Word documents
        .txt  : Plain text files
        
    Notes:
        - File type is determined by file extension (case-insensitive)
        - Unsupported types log a warning and return None
        - The frontend should validate file types before upload, but this
          provides a second line of defense
        - For PDFs: OCR is automatically attempted if PyMuPDF finds no text
    """
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        return extract_pdf(file_path)
    elif ext == ".docx":
        return extract_docx(file_path)
    elif ext == ".txt":
        return extract_txt(file_path)
    else:
        print(f"[WARNING] Unsupported file type: {file_path}")
        return None
