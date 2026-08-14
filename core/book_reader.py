"""Extract sampled text from EPUB, PDF, or TXT for DNA analysis."""

import zipfile
from pathlib import Path
from bs4 import BeautifulSoup


def _resolve_opf(z):
    try:
        container = z.read("META-INF/container.xml")
        soup = BeautifulSoup(container, "xml")
        rootfile = soup.find("rootfile")
        if rootfile:
            return rootfile.get("full-path", "")
    except Exception:
        pass
    return next((f for f in z.namelist() if f.endswith(".opf")), None)


def _opf_dir(opf_path):
    parts = opf_path.split("/")[:-1]
    return "/".join(parts)


def _normalize_path(base_dir, rel_path):
    raw = f"{base_dir}/{rel_path}" if base_dir else rel_path
    parts = []
    for part in raw.split("/"):
        if part in ("", "."):
            continue
        elif part == "..":
            if parts:
                parts.pop()
        else:
            parts.append(part)
    return "/".join(parts)


def _html_to_text(html_bytes, max_chars=None):
    soup = BeautifulSoup(html_bytes, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    return text[:max_chars] if max_chars else text


def _sample_content(full_text: str, target_chars: int = 8000, num_samples: int = 4) -> str:
    """
    Sample evenly-spaced excerpts across the full text so the AI sees
    beginning, early-middle, mid, and late sections of the book.
    Excerpts are joined with a separator so the model knows they are not contiguous.
    """
    total = len(full_text)
    if total <= target_chars:
        return full_text
    chunk = target_chars // num_samples
    parts = []
    for i in range(num_samples):
        pos = int(total * i / num_samples)
        parts.append(full_text[pos: pos + chunk])
    return "\n[...]\n".join(parts)


def read_epub_for_dna(epub_path):
    title = "Unknown Book"
    content_parts = []
    try:
        with zipfile.ZipFile(epub_path, "r") as z:
            opf_path = _resolve_opf(z)
            if not opf_path:
                return title, ""
            opf_dir = _opf_dir(opf_path)
            opf_soup = BeautifulSoup(z.read(opf_path), "xml")
            dc_title = opf_soup.find("dc:title")
            if dc_title and dc_title.text.strip():
                title = dc_title.text.strip()
            spine = opf_soup.find("spine")
            manifest_items = {
                item.get("id"): _normalize_path(opf_dir, item.get("href", ""))
                for item in opf_soup.find_all("item")
                if "html" in (item.get("media-type") or "")
                or (item.get("href") or "").endswith((".xhtml", ".html", ".htm"))
            }
            all_files = z.namelist()
            if spine:
                for itemref in spine.find_all("itemref"):
                    idref = itemref.get("idref", "")
                    file_path = manifest_items.get(idref)
                    if file_path and file_path in all_files:
                        content_parts.append(_html_to_text(z.read(file_path)))
    except Exception as e:
        print(f"read_epub_for_dna failed: {e}")
    full_text = " ".join(content_parts)
    return title, _sample_content(full_text)


def read_txt_for_dna(txt_path):
    title = Path(txt_path).stem.replace("_", " ").replace("-", " ")
    try:
        for enc in ("utf-8", "gbk", "latin-1"):
            try:
                with open(txt_path, encoding=enc) as f:
                    full_text = f.read()
                return title, _sample_content(full_text)
            except UnicodeDecodeError:
                continue
    except Exception as e:
        print(f"read_txt_for_dna failed: {e}")
    return title, ""


def read_pdf_for_dna(pdf_path):
    title = Path(pdf_path).stem.replace("_", " ").replace("-", " ")
    content_parts = []
    try:
        from pypdf import PdfReader
        reader = PdfReader(pdf_path)
        meta = reader.metadata
        if meta and getattr(meta, "title", None) and meta.title.strip():
            title = meta.title.strip()
        for page in reader.pages:
            content_parts.append(page.extract_text() or "")
    except Exception as e:
        print(f"read_pdf_for_dna failed: {e}")
    full_text = " ".join(content_parts)
    return title, _sample_content(full_text)


def read_file_for_dna(file_path):
    ext = Path(file_path).suffix.lower()
    if ext == ".epub":
        return read_epub_for_dna(file_path)
    elif ext == ".txt":
        return read_txt_for_dna(file_path)
    elif ext == ".pdf":
        return read_pdf_for_dna(file_path)
    else:
        raise ValueError(f"Unsupported format: {ext}")
