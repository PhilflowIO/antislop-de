"""Rechnet menschliche Struktur-Referenzwerte pro German-Commons-Register.

Zeigt den strukturellen Kontrast zwischen Registern (lebendig vs. dröge/nominal) —
die Zahlen-Grundlage für die Register-Gewichtung UND die Human-Targets, gegen die
die Modal-Phase gemma-vorher/nachher misst. Output: eval/structural_reference.json
"""

from __future__ import annotations

import itertools
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from structural_slop import analyze  # noqa: E402

SAMPLE = {
    "dialog/literary (cultural/dibilit)": ("cultural", "dibilit"),
    "forum (web/wikidiscussions)": ("web", "wikidiscussions"),
    "forum-AT (web/onemillionposts)": ("web", "onemillionposts"),
    "encyclopedic (web/wikipedia)": ("web", "wikipedia"),
    "academic (scientific/openalex)": ("scientific", "openalex"),
    "speech (political/germanpoliticalspeeches)": ("political", "germanpoliticalspeeches"),
}
N_DOCS = int(sys.argv[1]) if len(sys.argv) > 1 else 250


def main() -> None:
    from datasets import load_dataset
    out = {}
    for label, (cfg, split) in SAMPLE.items():
        ds = load_dataset("coral-nlp/german-commons", cfg, split=split, streaming=True)
        texts = [(r.get("text") or "")[:4000] for r in itertools.islice(ds, N_DOCS)]
        m = analyze(texts)
        out[label] = m
        print(f"{label:<48} nom/100={m.get('nominalization_per_100')}  "
              f"noun/verb={m.get('noun_verb_ratio')}  satzlen={m.get('mean_sentence_len')}  "
              f"passiv={m.get('passive_ratio')}")
        Path(__file__).parent.joinpath("structural_reference.json").write_text(
            json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n-> eval/structural_reference.json")


if __name__ == "__main__":
    main()
