"""Book DNA analysis and 3-movement suite design via DeepSeek-V3 (SiliconFlow)."""

import os
import json
import time
from openai import OpenAI

def _get_client():
    """Fresh client each call - always picks up the latest API key."""
    return OpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url="https://api.siliconflow.cn/v1"
    )

BOOK_DNA_PROMPT = """
You are a literary atmosphere analyst. Analyze the overall qualities of this book and output JSON.

Title: {title}
Content excerpt:
{content}

Output this JSON:
{{
  "title": "book title",
  "overall_mood": "overall mood (e.g. melancholic, warm, tense)",
  "emotional_range": "description of emotional range",
  "themes": ["theme1", "theme2"],
  "setting": "time period and environment",
  "rhythm": "narrative rhythm",
  "music_direction": "suitable music direction (instruments, style, tempo)"
}}
Output JSON only, no other text.
"""


def _is_retryable_sf_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(
        token in msg
        for token in ("503", "429", "50508", "too busy", "timeout", "overload", "unavailable")
    )


def _chat_json(messages: list, *, retries: int = 3, base_delay: float = 4.0) -> dict:
    """Call DeepSeek via SiliconFlow with retry on transient busy/overload errors."""
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            response = _get_client().chat.completions.create(
                model="deepseek-ai/DeepSeek-V3",
                messages=messages,
                response_format={"type": "json_object"},
            )
            return json.loads(response.choices[0].message.content)
        except Exception as exc:
            last_err = exc
            if attempt < retries and _is_retryable_sf_error(exc):
                wait = base_delay * attempt
                print(f"[Analyzer] SiliconFlow busy, retry {attempt}/{retries} in {wait:.0f}s...")
                time.sleep(wait)
                continue
            raise
    raise last_err


def analyze_book_dna(title: str, content: str) -> dict:
    return _chat_json([{
        "role": "user",
        "content": BOOK_DNA_PROMPT.format(title=title, content=content),
    }])


SUITE_PROMPT = """
You are a film score composer. Given this book's DNA, create exactly 3 musical movements for a reading suite.
The 3 movements form a narrative arc: Opening -> Development -> Finale.
Each movement must reflect the book's core identity: its instruments, cultural style, and emotional register from the DNA.

Rules for musical coherence:
- This is BACKGROUND music for reading — calm, sparse, never busy or rhythmic
- Use at most TWO elements: ONE lead melody instrument + ONE very soft pad or accompaniment
- The lead must carry a clear, singable main melody — simple 4-to-8 note motif, easy to follow
- NO drums, NO percussion, NO beat, NO rhythm section, NO pulsing bass — ever
- Tempo: slow 55–65 bpm only; long sustained notes; plenty of silence between phrases
- Choose ONE tonal key that fits the book's cultural origin AND emotional character. Use this guide:
  * Chinese traditional (erhu/guzheng/pipa): bright/heroic -> G major, D major; melancholic/longing -> D minor, A minor; ancient/solemn -> E minor pentatonic
  * Japanese (koto/shakuhachi/biwa): melancholic/nostalgic -> A minor (hirajoshi scale); eerie/tense -> E minor (in sen scale); peaceful/serene -> D major pentatonic
  * Russian/Eastern European: tragic/existential -> D minor, C minor; passionate/turbulent -> E minor harmonic; brooding/fatalistic -> B minor
  * Latin American/magical realism: vibrant/festive -> A major, E major; bittersweet -> A minor Dorian; haunted -> G minor
  * Western classical/literary: heroic/triumphant -> C major, Eb major; tragic/dramatic -> C minor, F minor; mysterious/gothic -> F# minor, B minor; romantic/lush -> E major, Ab major
  * Middle Eastern/Persian: mystical/longing -> D Hijaz (D Eb F# G); meditative/spiritual -> C Rast
  * Nordic/Scandinavian folk: open/pastoral -> E Dorian, D Dorian; melancholic/wintry -> F# minor
  * African/spiritual: joyful/ceremonial -> G major pentatonic, D major; ancestral/solemn -> A minor pentatonic
  * Modern/urban thriller: tense/paranoid -> C# minor, F minor; noir/cynical -> Eb minor
  * Chinese web novel (xianxia/infinite-flow/system): epic/heroic -> D major, A major; tense dungeon/boss -> C# minor; mystical cultivation -> E minor pentatonic
  * Universal rule: minor keys for tragedy/mystery/tension/grief; major keys for hope/adventure/warmth/triumph
- State the chosen key explicitly in every movement prompt
- Define the same short main melodic motif in the Opening and develop it across all movements
- All 3 movements share the same lead instrument for unity
- Harmonies must be consonant, minimal, and stay behind the melody

Book DNA:
{book_dna}

Output a JSON object:
{{"sections": [
  {{"name": "evocative movement name",
    "atmosphere": "one sentence on this movement's emotional quality",
    "music_prompt": "MusicGen prompt: ONE lead instrument with clear main melody, optional ONE soft pad, key signature, 55-65 bpm, simple singable motif, soft dynamics, sparse minimal arrangement. NO drums NO percussion NO beat. Purely instrumental, no vocals. IMPORTANT: use MusicGen-compatible names — erhu->Chinese fiddle bowed string, guzheng->Chinese zither plucked strings, pipa->Chinese lute plucked, dizi->Chinese breathy flute, shakuhachi->Japanese bamboo flute breathy, koto->Japanese zither plucked"
  }}
]}}
Exactly 3 sections. All movements must share the same key and core instrumentation. JSON only, no other text.
"""


def generate_suite_sections(dna: dict) -> list:
    """Call DeepSeek once to produce 3 music prompts for Opening/Development/Finale."""
    prompt = SUITE_PROMPT.format(book_dna=json.dumps(dna, ensure_ascii=False))
    raw = _chat_json([{"role": "user", "content": prompt}])
    if isinstance(raw, list):
        return raw[:3]
    for key in raw:
        if isinstance(raw[key], list):
            return raw[key][:3]
    return []
