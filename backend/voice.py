"""Voice onboarding: transcription + rule-based parsing.

Flow:
  audio --(faster-whisper)--> transcript --(parse)--> [(item, qty, unit)]
The same parser is used for the "type instead" fallback, so the demo works even
if the mic or the Whisper model misbehaves.

Parsing is deliberately simple and rule-based (no LLM): split the sentence into
segments, pull out a quantity (digit or number word) and a unit, treat the rest
as the item name, then fuzzy-match that name to existing SKUs with rapidfuzz.
"""
from __future__ import annotations

import os
import re
import tempfile

from rapidfuzz import fuzz, process

# --------------------------------------------------------------------------- #
# Whisper model (lazy singleton, preloaded at startup in main.py)
# --------------------------------------------------------------------------- #
_MODEL = None


def load_model():
    """Load faster-whisper 'base' on CPU with int8. Cached after first call."""
    global _MODEL
    if _MODEL is None:
        from faster_whisper import WhisperModel

        _MODEL = WhisperModel("base", device="cpu", compute_type="int8")
    return _MODEL


def transcribe_file(audio_bytes: bytes, suffix: str = ".m4a") -> str:
    """Write bytes to a temp file, transcribe, return the text."""
    model = load_model()
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name
        segments, _info = model.transcribe(tmp_path, beam_size=1)
        return " ".join(seg.text for seg in segments).strip()
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


# --------------------------------------------------------------------------- #
# Rule-based parser
# --------------------------------------------------------------------------- #
NUMBER_WORDS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "fifteen": 15, "twenty": 20, "twenty-five": 25, "thirty": 30,
    "forty": 40, "fifty": 50, "hundred": 100,
}

# Map many spoken forms to a canonical unit.
UNIT_ALIASES = {
    "kg": "kg", "kgs": "kg", "kilo": "kg", "kilos": "kg", "kilogram": "kg",
    "kilograms": "kg", "kilogramme": "kg",
    "litre": "litre", "litres": "litre", "liter": "litre", "liters": "litre", "l": "litre",
    "packet": "packet", "packets": "packet", "pack": "packet", "packs": "packet", "pkt": "packet",
    "piece": "piece", "pieces": "piece", "pcs": "piece", "pc": "piece", "unit": "piece", "units": "piece",
}

# Words to drop from the item name after pulling qty/unit out.
FILLER = {"of", "please", "add", "stock", "kg", "and"}


def _to_number(token: str) -> float | None:
    token = token.strip().lower()
    if re.fullmatch(r"\d+(\.\d+)?", token):
        return float(token)
    return float(NUMBER_WORDS[token]) if token in NUMBER_WORDS else None


def _split_segments(text: str) -> list[str]:
    # Split on commas and the word "and".
    parts = re.split(r",|\band\b", text, flags=re.IGNORECASE)
    return [p.strip() for p in parts if p.strip()]


def parse_segment(segment: str) -> tuple[float, str | None, str] | None:
    """Return (quantity, unit_or_None, item_name) for one segment, or None."""
    tokens = re.findall(r"[a-zA-Z]+(?:-[a-zA-Z]+)?|\d+(?:\.\d+)?", segment.lower())
    if not tokens:
        return None

    quantity: float | None = None
    unit: str | None = None
    item_tokens: list[str] = []

    for tok in tokens:
        num = _to_number(tok)
        if num is not None and quantity is None:
            quantity = num
            continue
        if tok in UNIT_ALIASES and unit is None:
            unit = UNIT_ALIASES[tok]
            continue
        if tok not in FILLER:
            item_tokens.append(tok)

    item_name = " ".join(item_tokens).strip()
    if quantity is None:
        quantity = 1.0
    if not item_name:
        return None
    return quantity, unit, item_name


def match_item(name: str, known: list[tuple[int, str, str]], threshold: int = 70):
    """Fuzzy-match `name` to known items.

    `known` is a list of (id, name, unit). Returns (item_id, canonical_name,
    unit) on a confident match, else None.
    """
    if not known:
        return None
    choices = {kid: kname for kid, kname, _ in known}
    # Lowercase both sides so short names ("tea" vs "Tea") aren't penalised.
    result = process.extractOne(name, choices, scorer=fuzz.WRatio, processor=str.lower)
    if result is None:
        return None
    _matched_name, score, matched_id = result
    if score < threshold:
        return None
    kid, kname, kunit = next(k for k in known if k[0] == matched_id)
    return kid, kname, kunit


def parse_order(text: str, known: list[tuple[int, str, str]]) -> list[dict]:
    """Parse a full sentence into reviewable lines.

    Each line: {item, quantity, unit, matched_item_id}. When an item matches an
    existing SKU we use its canonical name + unit (unless the user said a unit).
    """
    lines: list[dict] = []
    for seg in _split_segments(text):
        parsed = parse_segment(seg)
        if parsed is None:
            continue
        quantity, unit, raw_name = parsed
        matched = match_item(raw_name, known)
        if matched:
            mid, cname, munit = matched
            lines.append({
                "item": cname,
                "quantity": quantity,
                "unit": unit or munit,
                "matched_item_id": mid,
            })
        else:
            lines.append({
                "item": raw_name.title(),
                "quantity": quantity,
                "unit": unit or "piece",
                "matched_item_id": None,
            })
    return lines
