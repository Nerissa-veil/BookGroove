"""Local library persistence: book DNA, BGM versions, and session timestamps."""

import os
import json
import shutil
import re
from pathlib import Path
from typing import Optional

LIBRARY_DIR = Path("library")

# Legacy per-chapter BGM fields (removed in 2.1+)
_LEGACY_DNA_KEYS = ("chapters", "cached_chapters")


def normalize_book_dna(dna: Optional[dict]) -> Optional[dict]:
    """Strip deprecated chapter-based BGM fields from stored DNA."""
    if not dna:
        return dna
    for key in _LEGACY_DNA_KEYS:
        dna.pop(key, None)
    return dna


def _sanitize_name(name: str) -> str:
    cleaned = re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9_-]", "_", name)
    cleaned = re.sub(r"_+", "_", cleaned)
    return cleaned.strip("_")


def _book_dir(title):
    safe = _sanitize_name(title)
    if not safe:
        safe = "Unknown_Book"
    p = LIBRARY_DIR / safe
    p.mkdir(parents=True, exist_ok=True)
    return p

def save_book_dna(title, dna):
    normalize_book_dna(dna)
    p = _book_dir(title) / "book_dna.json"
    p.write_text(json.dumps(dna, ensure_ascii=False, indent=2), encoding="utf-8")

def load_book_dna(title):
    p = _book_dir(title) / "book_dna.json"
    if not p.exists():
        return None
    for enc in ("utf-8", "gbk", "latin-1"):
        try:
            dna = json.loads(p.read_text(encoding=enc))
            if any(k in dna for k in _LEGACY_DNA_KEYS):
                normalize_book_dna(dna)
                p.write_text(json.dumps(dna, ensure_ascii=False, indent=2), encoding="utf-8")
            return dna
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
    return None

def save_session(title, session):
    p = _book_dir(title) / "sessions.json"
    data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
    data.append(session)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _bgm_versions(title):
    """Return sorted list of (version_int, path) for all bgm files."""
    bd = _book_dir(title)
    versions = []
    for ext in (".mp3", ".wav", ".ogg"):
        p = bd / ("bgm" + ext)
        if p.exists():
            versions.append((0, str(p)))
    for f in bd.glob("bgm_v*.*"):
        m = re.match(r"bgm_v(\d+)\.", f.name)
        if m:
            versions.append((int(m.group(1)), str(f)))
    return sorted(versions, key=lambda x: x[0])


def save_book_bgm(title, src_path):
    ext = Path(src_path).suffix or ".mp3"
    bd = _book_dir(title)
    # migrate legacy bgm.* -> bgm_v1.*
    for _ext in (".mp3", ".wav", ".ogg"):
        legacy = bd / ("bgm" + _ext)
        if legacy.exists():
            legacy.rename(bd / f"bgm_v1{_ext}")
    existing = _bgm_versions(title)
    next_v = (max(v for v, _ in existing) + 1) if existing else 1
    dest = bd / f"bgm_v{next_v}{ext}"
    shutil.move(src_path, str(dest))
    return str(dest)


def get_book_bgm(title):
    versions = _bgm_versions(title)
    return versions[-1][1] if versions else None


def list_book_bgm_versions(title):
    """Return list of (label, path) for all versions, newest last."""
    return [(f"Version {v if v > 0 else 1}", p) for v, p in _bgm_versions(title)]


def delete_book(title):
    """Permanently remove all cached data for a book."""
    safe = _sanitize_name(title)
    if not safe:
        return
    bd = LIBRARY_DIR / safe
    if bd.exists():
        shutil.rmtree(bd)


def list_books_with_titles():
    """Return [(dir_name, display_title)]. display_title from DNA json when available."""
    if not LIBRARY_DIR.exists():
        return []
    result = []
    for d in LIBRARY_DIR.iterdir():
        if d.is_dir():
            dir_name = d.name
            display_title = dir_name.replace("_", " ")
            dna_path = d / "book_dna.json"
            if dna_path.exists():
                try:
                    for enc in ("utf-8", "gbk", "latin-1"):
                        try:
                            data = json.loads(dna_path.read_text(encoding=enc))
                            if data.get("title"):
                                display_title = data["title"]
                            break
                        except (UnicodeDecodeError, json.JSONDecodeError):
                            continue
                except Exception:
                    pass
            result.append((dir_name, display_title))
    return result
