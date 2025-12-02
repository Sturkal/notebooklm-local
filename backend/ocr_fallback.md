OCR fallback proposal

Overview:
- Add an OCR fallback for scanned PDFs (image-only PDFs) using Tesseract OCR.
- When `extract(path)` returns empty text for PDFs, run pdf2image to convert pages to images and then run pytesseract on each image.

Required Python packages (add to `backend/requirements.txt`):
- pytesseract
- pdf2image

System packages (in `backend/Dockerfile`, apt-get install):
- tesseract-ocr
- poppler-utils (already present in Dockerfile)
- libtesseract-dev (sometimes needed)

Implementation outline:
1. Modify `extract.extract_pdf()` to detect empty text and call `ocr_pdf()`.
2. Implement `ocr_pdf(file_path)` that uses `pdf2image.convert_from_path(file_path)` to get PIL images, then `pytesseract.image_to_string(img, lang='eng')` on each page and concat.
3. Ensure Dockerfile installs `tesseract-ocr` and `poppler-utils` (poppler already installed earlier).
4. Add `pytesseract` and `pdf2image` to `requirements.txt` and rebuild the backend image.

Caveats:
- OCR will increase image processing CPU and disk usage.
- PDF with many pages can be slow; consider adding a page limit or user-controlled toggle.

If you approve, I'll apply the code changes and update `requirements.txt` and `Dockerfile`, then rebuild the backend image and run a test on a scanned-PDF sample (if you provide one).