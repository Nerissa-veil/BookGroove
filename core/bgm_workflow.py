"""Shared BGM generation workflow (suite design + MusicGen + stitch)."""

from __future__ import annotations

import os
from typing import Optional

import streamlit as st

from core.analyzer import generate_suite_sections
from core.cache import save_book_dna, save_book_bgm
from core.generator import generate_music, stitch_with_crossfade

MOVEMENT_DURATION = 40


def check_audio_deps(T: dict) -> None:
    """Preflight: verify pydub + ffmpeg before spending API credits."""
    import shutil

    try:
        import pydub  # noqa: F401
    except ImportError:
        st.error(T["err_pydub"])
        st.stop()
    if not shutil.which("ffmpeg"):
        st.error(T["err_ffmpeg"])
        st.stop()


def _cleanup_tracks(track_paths: list) -> None:
    for path in track_paths:
        try:
            if path and os.path.exists(path):
                os.unlink(path)
        except OSError:
            pass


def _resolve_sections(dna: dict, T: dict, *, redesign: bool, prog, composing_text: str):
    """Return (sections, dna, had_ai_compose)."""
    if redesign or not dna.get("suite_sections"):
        prog.progress(0, text=composing_text)
        sections = generate_suite_sections(dna)
        if not sections:
            raise ValueError(T["err_no_suite"])
        dna["suite_sections"] = sections
        return sections, dna, True
    prog.progress(0, text=T["gen_start"])
    return dna["suite_sections"], dna, False


def generate_bgm_suite(
    dna: dict,
    book_id: str,
    T: dict,
    *,
    redesign_sections: bool = False,
    composing_text: Optional[str] = None,
    stitching_text: Optional[str] = None,
) -> tuple[str, dict]:
    """
    Design (or reuse) suite sections, generate movements, stitch, and save BGM.
    Returns (saved_bgm_path, updated_dna).
    """
    composing_text = composing_text or T["composing"]
    stitching_text = stitching_text or T["stitching"]
    prog = st.progress(0, text=composing_text)

    try:
        sections, dna, had_ai = _resolve_sections(
            dna, T, redesign=redesign_sections, prog=prog, composing_text=composing_text
        )
        if had_ai:
            save_book_dna(book_id, dna)
            prog.progress(0.2, text=T["suite_ready"])

        tracks = []
        for i, sec in enumerate(sections):
            name = sec.get("name") or T["movement_default"].format(i=i + 1)
            frac = (0.2 + 0.8 * (i / len(sections))) if had_ai else (i / len(sections))
            prog.progress(
                frac,
                text=T["gen_movement"].format(i=i + 1, total=len(sections), name=name),
            )
            tracks.append(generate_music(sec.get("music_prompt", ""), duration=MOVEMENT_DURATION))

        prog.progress(1.0, text=T["gen_done"])
        with st.spinner(stitching_text):
            stitched = stitch_with_crossfade(tracks, crossfade_sec=4)
            bgm_path = save_book_bgm(book_id, stitched)
        _cleanup_tracks(tracks)
        return bgm_path, dna
    except Exception:
        prog.empty()
        raise
    finally:
        prog.empty()


def show_bgm_error(e: Exception, T: dict) -> None:
    msg = str(e)
    if "401" in msg or "unauthorized" in msg.lower():
        st.error(T["err_rep_401"])
    elif "429" in msg:
        st.error(T["err_rep_429"])
    elif "connect" in msg.lower() or "timeout" in msg.lower() or "ssl" in msg.lower() or "handshake" in msg.lower():
        st.error(T["err_network"])
    else:
        st.error(T["err_bgm"].format(msg=msg))
