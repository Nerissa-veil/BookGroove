"""Music generation via MusicGen, reading-oriented post-processing, and stitching."""

from __future__ import annotations

import os
import time
import tempfile
import re
from pathlib import Path

import requests
import static_ffmpeg
static_ffmpeg.add_paths()  # ensure bundled ffmpeg is on PATH for pydub

INSTRUMENTAL_SUFFIX = (
    "instrumental only, no vocals, no singing, no lyrics, no voice, "
    "single clear lead melody, one main melodic line easy to follow, crisp not muffled, "
    "soft minimal accompaniment, sparse arrangement, only two layers, "
    "no drums, no percussion, no beat, no rhythm section, no kick, no snare, no hi-hat, "
    "no bass drum, no cymbals, no pulsing rhythm, "
    "slow tempo 55 to 65 bpm, gentle and calm, "
    "warm mellow timbre, soft dynamics, consonant harmonies, "
    "ambient reading background music, peaceful and unobtrusive"
)

# Replicate MusicGen valid versions: stereo-melody-large | stereo-large | melody-large | large
# (no medium/small on Replicate — use post-processing + peak normalization instead)
_VALID_REPLICATE_VERSIONS = frozenset({
    "stereo-melody-large", "stereo-large", "melody-large", "large",
})
_REPLICATE_VERSION_ALIASES = {
    "medium": "large",
    "small": "large",
    "stereo-medium": "stereo-large",
    "stereo-melody-medium": "melody-large",
}


def _resolve_replicate_model_version() -> str:
    raw = (os.getenv("MUSICGEN_MODEL_VERSION", "melody-large") or "melody-large").strip()
    if raw in _VALID_REPLICATE_VERSIONS:
        return raw
    mapped = _REPLICATE_VERSION_ALIASES.get(raw.lower())
    if mapped:
        print(f"[Generator] MUSICGEN_MODEL_VERSION={raw!r} not on Replicate; using {mapped!r}")
        return mapped
    print(f"[Generator] Unknown MUSICGEN_MODEL_VERSION={raw!r}; using 'large'")
    return "large"


REPLICATE_NORMALIZATION = os.getenv("MUSICGEN_NORMALIZATION", "peak").strip() or "peak"

# Post-processing: tame ghost drums without muffling the melody.
# Previous chain was too aggressive (6.8 kHz lowpass + 3.5 kHz cut) and sounded "糊".
_POSTPROCESS_AF = (
    "highpass=f=90,"
    "lowpass=f=11500,"
    "equalizer=f=200:t=q:w=1.0:g=-3,"
    "equalizer=f=2800:t=q:w=1.8:g=+2,"
    "equalizer=f=6000:t=q:w=2:g=+1,"
    "acompressor=threshold=-18dB:ratio=2.5:attack=30:release=300:makeup=1"
)
_POSTPROCESS_ATTENUATION_DB = float(os.getenv("MUSICGEN_BG_ATTENUATION_DB", "2"))

# Model cache: stored next to the app so it follows wherever the app is installed
MODEL_DIR = Path(__file__).parent.parent / "models"

# Module-level cache so the model is only loaded once per process
_LOCAL_MODEL = None
_LOCAL_PROCESSOR = None


def _is_network_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    if isinstance(
        exc,
        (
            requests.exceptions.Timeout,
            requests.exceptions.ConnectionError,
            requests.exceptions.SSLError,
            requests.exceptions.ChunkedEncodingError,
        ),
    ):
        return True
    return any(
        token in msg
        for token in (
            "ssl", "handshake", "timed out", "timeout",
            "connection reset", "connection aborted", "temporary failure",
        )
    )


def _with_network_retry(fn, *, label: str, retries: int = 4, base_delay: float = 6.0):
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            return fn()
        except Exception as exc:
            last_err = exc
            if attempt < retries and _is_network_error(exc):
                wait = base_delay * attempt
                print(f"[Generator] {label} network error, retry {attempt}/{retries} in {wait:.0f}s...")
                time.sleep(wait)
                continue
            raise
    raise last_err


def _download_with_retry(
    url: str,
    dest: str,
    retries: int = 5,
    connect_timeout: int = 45,
    read_timeout: int = 300,
):
    """Download a URL to dest with retry on timeout / SSL / connection errors."""
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            print(f"[Generator] Download attempt {attempt}/{retries}: {url[:80]}...")
            with requests.get(
                url, stream=True, timeout=(connect_timeout, read_timeout)
            ) as r:
                r.raise_for_status()
                with open(dest, "wb") as f:
                    for chunk in r.iter_content(chunk_size=65536):
                        if chunk:
                            f.write(chunk)
            print(f"[Generator] Download complete: {dest}")
            return
        except Exception as e:
            if not _is_network_error(e):
                raise
            last_err = e
            print(f"[Generator] Download failed (attempt {attempt}): {e}")
            if attempt < retries:
                time.sleep(6 * attempt)
    raise RuntimeError(f"Download failed after {retries} attempts: {last_err}")


def _wait_replicate_prediction(client, prediction, *, label: str):
    poll_interval = 30
    max_wait = 1800
    waited = 0
    print(f"[Generator] {label} prediction: {prediction.id}")
    while prediction.status not in ("succeeded", "failed", "canceled"):
        time.sleep(poll_interval)
        waited += poll_interval
        _with_network_retry(
            prediction.reload,
            label=f"{label} poll",
            retries=3,
            base_delay=5.0,
        )
        print(f"[Generator] {label} status: {prediction.status} ({waited}s)")
        if waited >= max_wait:
            raise RuntimeError(f"{label} timed out after 30 minutes")
    if prediction.status != "succeeded":
        raise RuntimeError(f"{label} {prediction.status}: {prediction.error}")
    return prediction.output


def _replicate_client(api_token: str):
    import replicate
    return replicate.Client(api_token=api_token, timeout=120)


def _create_replicate_prediction(client, **kwargs):
    return _with_network_retry(
        lambda: client.predictions.create(**kwargs),
        label="Replicate create",
        retries=4,
    )


def _extract_output_url(output) -> str:
    if isinstance(output, str) and output.startswith("http"):
        return output
    output_str = str(output)
    url_match = re.search(r"https?://\S+?\.(?:wav|mp3|flac|ogg)\S*", output_str, re.IGNORECASE)
    if url_match:
        return url_match.group(0)
    url_fallback = re.search(r"https?://\S+", output_str)
    if url_fallback:
        return url_fallback.group(0)
    raise RuntimeError(f"Failed to extract audio URL from output: {output}")


def _postprocess_reading_track(path: str) -> str:
    """
    Balance MusicGen output for reading BGM:
    - light rumble cut (90 Hz) without removing warmth
    - keep air up to ~11.5 kHz so melody stays clear, not muffled
    - gentle low-mid cut for ghost kick; presence/air boost for the lead line
    """
    from pydub import AudioSegment

    seg = AudioSegment.from_file(path)
    out = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    out.close()
    try:
        seg.export(
            out.name,
            format="wav",
            parameters=["-af", _POSTPROCESS_AF],
        )
        seg = AudioSegment.from_file(out.name)
    except Exception as exc:
        print(f"[Generator] FFmpeg post-process failed ({exc}), using pydub filters")
        seg = seg.high_pass_filter(90).low_pass_filter(11500)
        seg.export(out.name, format="wav")

    if _POSTPROCESS_ATTENUATION_DB:
        seg = seg - _POSTPROCESS_ATTENUATION_DB
        seg.export(out.name, format="wav")

    if path != out.name:
        try:
            os.unlink(path)
        except OSError:
            pass
    print(f"[Generator] Post-processed: {out.name}")
    return out.name


# -- Local MusicGen -----------------------------------------------------------

def _load_local_model():
    """Load MusicGen Medium into GPU/CPU memory. Cached after first call."""
    global _LOCAL_MODEL, _LOCAL_PROCESSOR
    if _LOCAL_MODEL is not None:
        return _LOCAL_MODEL, _LOCAL_PROCESSOR

    from transformers import AutoProcessor, MusicgenForConditionalGeneration
    import torch

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model_name = "facebook/musicgen-medium"
    print("[Generator] Loading local MusicGen Medium model...")
    print(f"[Generator] Cache dir: {MODEL_DIR}")
    print("[Generator] First run will download ~3 GB -- please wait...")

    _LOCAL_PROCESSOR = AutoProcessor.from_pretrained(
        model_name, cache_dir=str(MODEL_DIR)
    )
    dtype = torch.float16 if torch.cuda.is_available() else torch.float32
    _LOCAL_MODEL = MusicgenForConditionalGeneration.from_pretrained(
        model_name, cache_dir=str(MODEL_DIR), torch_dtype=dtype
    )

    if torch.cuda.is_available():
        _LOCAL_MODEL = _LOCAL_MODEL.to("cuda")
        print(f"[Generator] Model ready on GPU: {torch.cuda.get_device_name(0)}")
    else:
        print("[Generator] No CUDA GPU found -- running on CPU (slow but works)")

    return _LOCAL_MODEL, _LOCAL_PROCESSOR


def _generate_music_local(prompt: str, duration: int = 40) -> str:
    """Generate audio locally using MusicGen Medium. Returns path to WAV file."""
    import torch
    import scipy.io.wavfile
    import numpy as np

    full_prompt = f"{prompt}, {INSTRUMENTAL_SUFFIX}"
    print(f"[Generator] Local prompt: {full_prompt[:120]}...")
    print(f"[Generator] Local duration: {duration}s")

    model, processor = _load_local_model()
    max_new_tokens = int(duration * 50)
    print(f"[Generator] Generating {max_new_tokens} tokens...")

    inputs = processor(text=[full_prompt], padding=True, return_tensors="pt")
    if torch.cuda.is_available():
        inputs = {k: v.to("cuda") for k, v in inputs.items()}

    with torch.no_grad():
        audio_values = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            guidance_scale=3.5,
            do_sample=True,
            temperature=0.85,
        )

    audio_np = audio_values[0, 0].cpu().float().numpy()
    sample_rate = model.config.audio_encoder.sampling_rate

    peak = max(float(np.abs(audio_np).max()), 1e-6)
    audio_int16 = (audio_np / peak * 32767).astype(np.int16)

    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    scipy.io.wavfile.write(tmp.name, rate=sample_rate, data=audio_int16)
    print(f"[Generator] Local audio saved: {tmp.name}")
    return _postprocess_reading_track(tmp.name)


# -- Replicate MusicGen -------------------------------------------------------

def _generate_music_replicate(prompt: str, duration: int = 40) -> str:
    """Generate audio via Replicate MusicGen. Returns path to downloaded audio file."""
    api_token = os.environ.get("REPLICATE_API_TOKEN")
    model_version = "meta/musicgen:671ac645ce5e552cc63a54a2bbff63fcf798043055d2dac5fc9e36a837eedcfb"
    full_prompt = f"{prompt}, {INSTRUMENTAL_SUFFIX}"
    model_ver = _resolve_replicate_model_version()
    print(f"[Generator] Replicate prompt: {full_prompt[:120]}...")
    print(f"[Generator] Duration: {duration}s, model: {model_ver}")

    client = _replicate_client(api_token)
    prediction = _create_replicate_prediction(
        client,
        version=model_version,
        input={
            "prompt": full_prompt,
            "duration": duration,
            "model_version": model_ver,
            "normalization_strategy": REPLICATE_NORMALIZATION,
        },
    )
    output = _wait_replicate_prediction(client, prediction, label="MusicGen")
    url = _extract_output_url(output)

    ext = ".wav" if ".wav" in url.lower() else ".mp3"
    local_filename = os.path.join(tempfile.gettempdir(), f"temp_track_{int(time.time())}{ext}")
    _download_with_retry(url, local_filename)
    return _postprocess_reading_track(local_filename)


def generate_music(prompt: str, duration: int = 40) -> str:
    """
    Generate music with MusicGen.
      USE_LOCAL_MODEL=true  -> local MusicGen Medium
      otherwise             -> Replicate MusicGen
    """
    if os.getenv("USE_LOCAL_MODEL", "").strip().lower() in ("1", "true", "yes"):
        return _generate_music_local(prompt, duration)
    return _generate_music_replicate(prompt, duration)


def _trim_track_silence(seg, silence_thresh_db: int = -38, min_silence_ms: int = 350, pad_ms: int = 100):
    """Remove leading/trailing silence so crossfades blend actual music, not empty air."""
    from pydub.silence import detect_nonsilent

    nonsilent = detect_nonsilent(
        seg, min_silence_len=min_silence_ms, silence_thresh=silence_thresh_db
    )
    if not nonsilent:
        return seg
    start = max(0, nonsilent[0][0] - pad_ms)
    end = min(len(seg), nonsilent[-1][1] + pad_ms)
    trimmed = seg[start:end]
    edge_fade = min(150, max(30, len(trimmed) // 10))
    return trimmed.fade_in(edge_fade).fade_out(edge_fade)


def stitch_with_crossfade(track_paths: list, crossfade_sec: int = 4) -> str:
    """Stitch multiple audio files with crossfade transitions. Returns one mp3 path."""
    if not track_paths:
        raise ValueError("No audio tracks to stitch.")
    try:
        from pydub import AudioSegment
    except ImportError:
        raise ImportError(
            "pydub is not installed. Your generated track files are still in system Temp.\n"
            "Fix: pip install pydub   +   winget install ffmpeg"
        )
    desired_cf_ms = crossfade_sec * 1000
    combined = _trim_track_silence(AudioSegment.from_file(track_paths[0]))
    for p in track_paths[1:]:
        nxt = _trim_track_silence(AudioSegment.from_file(p))
        crossfade_ms = min(desired_cf_ms, len(combined) // 3, len(nxt) // 3)
        crossfade_ms = max(crossfade_ms, 500)
        combined = combined.append(nxt, crossfade=crossfade_ms)
    fade_ms = min(3000, len(combined) // 6)
    combined = combined.fade_in(fade_ms).fade_out(fade_ms)
    out = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    out.close()
    combined.export(out.name, format="mp3", bitrate="192k")
    return out.name
