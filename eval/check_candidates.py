"""Stufe-0-Abnahme: prüft deutsche KI-Floskel-Kandidaten gegen die Human-Baseline.

Wendet exakt dieselbe Content-Token-Transformation an wie der spätere Slop-Detektor
(scripts.baseline.content_tokens), schlägt die resultierenden Bi/Trigramme in der
Baseline nach und urteilt: fehlt die Floskel im natürlichen Deutsch (→ korrekt als
Slop bannbar), oder ist sie real präsent (→ kein Ban-Kandidat, Schutz vor False-Positive)?

Output ist Phils Augenschein-Material — die Zahlen stützen das Urteil, ersetzen es nicht.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from baseline import content_tokens  # noqa: E402

try:
    from wordfreq import zipf_frequency
except ImportError:
    zipf_frequency = None


def load_profile(path: Path) -> tuple[dict, dict]:
    p = json.loads(path.read_text(encoding="utf-8"))["human-authored"]
    bi = {x["ngram"]: x["frequency"] for x in p["top_bigrams"]}
    tri = {x["ngram"]: x["frequency"] for x in p["top_trigrams"]}
    return bi, tri


def load_opensub_words(path: Path) -> dict:
    if not path.is_file():
        return {}
    d = {}
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            d[row["word"].lower()] = int(row["count"])
    return d


def lookup_phrase(phrase: str, bi: dict, tri: dict) -> tuple[str, int, str]:
    """Gibt (geprüftes-ngram, freq, verdict) für eine Floskel zurück."""
    toks = content_tokens(phrase)
    if not toks:
        return "(leer nach Normierung)", -1, "n/a"
    if len(toks) == 1:
        return toks[0], -1, "unigram→Wort-Pfad"
    # repräsentatives n-gram: das seltenste enthaltene Bi/Trigramm
    cands: list[tuple[str, int]] = []
    for i in range(len(toks) - 1):
        ng = f"{toks[i]} {toks[i+1]}"
        cands.append((ng, bi.get(ng, 0)))
    for i in range(len(toks) - 2):
        ng = f"{toks[i]} {toks[i+1]} {toks[i+2]}"
        cands.append((ng, tri.get(ng, 0)))
    ng, freq = min(cands, key=lambda c: c[1])  # seltenstes Glied bestimmt Bannbarkeit
    if freq == 0:
        v = "✓ SLOP  (fehlt im natürlichen Deutsch)"
    elif freq < 100:
        v = "✓ slop  (sehr selten)"
    elif freq < 1000:
        v = "~ grenzwertig"
    else:
        v = "⚠ PRÄSENT (natürlich, NICHT bannen)"
    return ng, freq, v


def main() -> None:
    base = Path(__file__).resolve().parent.parent
    prof = Path(sys.argv[1]) if len(sys.argv) > 1 else base / "data/baseline/human_writing_profile_de.json"
    bi, tri = load_profile(prof)
    os_words = load_opensub_words(base / "data/raw/de_top_words.csv")
    cfg = json.loads((base / "eval/slop_candidates.json").read_text(encoding="utf-8"))

    print(f"\nBaseline: {prof.name}  ({len(bi):,} Bigramme / {len(tri):,} Trigramme)\n")

    print("═══ KI-FLOSKELN · n-gram-Pfad (sollten near-zero sein = korrekt als Slop erkennbar) ═══")
    print(f"  {'Floskel':<34}{'geprüftes n-gram':<26}{'Freq':>9}  Urteil")
    for ph in cfg["slop_phrases"]:
        ng, freq, v = lookup_phrase(ph, bi, tri)
        fs = "—" if freq < 0 else f"{freq:,}"
        print(f"  {ph:<34}{ng:<26}{fs:>9}  {v}")

    print("\n═══ KI-FLOSKELN · Funktionswort-lastig (kollabieren als n-gram → Slop-PHRASE-Pfad) ═══")
    print("  (auto-antislop bannt diese über die rohe Phrasen-Liste, nicht über Content-n-grams)")
    for ph in cfg.get("slop_phrases_functionword", []):
        toks = content_tokens(ph)
        print(f"  {ph:<34}→ Content-Token: {toks}")

    print("\n═══ KI-WÖRTER (Unigram: wordfreq-DE Zipf + OpenSubtitles-Dialog-Count) ═══")
    print(f"  {'Wort':<20}{'wordfreq-zipf':>14}{'OpenSubs-count':>16}  Hinweis")
    for w in cfg["slop_words"]:
        z = zipf_frequency(w, "de") if zipf_frequency else float("nan")
        c = os_words.get(w.lower(), 0)
        hint = "selten gesprochen" if c < 500 else "auch im Dialog üblich"
        print(f"  {w:<20}{z:>14.2f}{c:>16,}  {hint}")

    def run_controls(title: str, key: str, hint: str) -> tuple[int, int]:
        print(f"\n═══ {title} ═══")
        print(f"  {'Phrase':<28}{'geprüftes n-gram':<26}{'Freq':>9}  Urteil")
        ok = 0
        items = cfg.get(key, [])
        for ph in items:
            ng, freq, v = lookup_phrase(ph, bi, tri)
            fs = "—" if freq < 0 else f"{freq:,}"
            if freq > 0:
                ok += 1
            print(f"  {ph:<28}{ng:<26}{fs:>9}  {v}")
        print(f"  → präsent: {ok}/{len(items)}  {hint if ok == len(items) else '⚠ FEHLBETRAG — prüfen'}")
        return ok, len(items)

    run_controls("CONTROLS · Alltagssprache (MUSS präsent sein)",
                 "control_phrases", "✓ Baseline kennt gesprochenes Deutsch")
    run_controls("CONTROLS · Sachtext/expository (MUSS präsent sein — Gutachter-A-Gegenprobe)",
                 "expository_controls", "✓ Baseline kennt argumentatives Sachdeutsch")


if __name__ == "__main__":
    main()
