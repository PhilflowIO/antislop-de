"""Schritt-2 Prompt-Generator: deutsche Website-Copy-Profiling-Prompts.

Erzeugt das Reizmaterial für die FTPO-Profiling-Phase — die Aufträge, die gemma
deutschen Website-Text schreiben lassen, an dem sich sein Marketing-Slop gegen
die Human-Baseline sichtbar macht.

Design (Issue #7): Aufgabe KONSTANT ('schreib Website-Text'), Subjekt + Copy-Typ
+ Ton + Länge VARIIERT. Breite Subjekt-Streuung wäscht Themenwörter raus (sonst
würden Raven-Begriffe wie 'Meeting'/'Souveränität' gegen die Baseline
über-repräsentiert und fälschlich als Slop geflaggt). Übrig bleibt der echte,
subjekt-unabhängige Copy-Slop.

Grid: subjects × copy_types × tones × lengths (length nur, wo das Template sie
nutzt). Mit den Defaults ~1,5k Prompts; --smoke zieht ein stratifiziertes Sample.

    uv run python scripts/build_prompts.py                 # volles Set -> data/prompts_de.jsonl
    uv run python scripts/build_prompts.py --smoke 20      # Smoke-Sample, geprintet + Datei
"""

from __future__ import annotations

import argparse
import json
import logging
import random
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("build_prompts")

ROOT = Path(__file__).resolve().parent.parent
SUBJECTS_PATH = ROOT / "configs" / "copy_prompts" / "subjects_de.json"
COPY_TYPES_PATH = ROOT / "configs" / "copy_prompts" / "copy_types_de.json"


def _fakten_block(subject: dict) -> str:
    """Fakten als knapper Brief-Satz — geerdet, aber nicht überdeterminiert."""
    fakten = subject.get("fakten", [])
    if not fakten:
        return ""
    return "Das Wichtigste in Kürze: " + "; ".join(fakten) + "."


def build_grid(subjects: list[dict], copy_cfg: dict) -> list[dict]:
    """Voller Cartesischer Grid Subjekt × Copy-Typ × Ton × (Länge wo genutzt)."""
    tones = copy_cfg["tones"]
    lengths = copy_cfg["lengths"]
    prompts: list[dict] = []

    for subject in subjects:
        if not subject.get("profiling", True):
            continue  # Flaggschiff (Raven) = Anwendungsfall, nicht Slop-Treibstoff
        fakten_block = _fakten_block(subject)
        for ct in copy_cfg["copy_types"]:
            tmpl = ct["template"]
            uses_length = "{length_hint}" in tmpl
            length_axis = lengths if uses_length else [{"id": "na", "hint": ""}]
            for tone in tones:
                for length in length_axis:
                    prompt = tmpl.format(
                        name=subject["name"],
                        branche=subject["branche"],
                        fakten_block=fakten_block,
                        tone_hint=tone["hint"],
                        length_hint=length["hint"],
                    )
                    # doppelte Leerzeichen aus leeren Platzhaltern glätten
                    prompt = " ".join(prompt.split())
                    prompts.append(
                        {
                            "id": f"{subject['id']}__{ct['id']}__{tone['id']}__{length['id']}",
                            "subject_id": subject["id"],
                            "branche": subject["branche"],
                            "copy_type": ct["id"],
                            "tone": tone["id"],
                            "length": length["id"],
                            "prompt": prompt,
                        }
                    )
    return prompts


def stratified_smoke(prompts: list[dict], n: int, rng: random.Random) -> list[dict]:
    """Sample, das jeden Copy-Typ und Raven garantiert trifft (Augenschein-Breite)."""
    by_type: dict[str, list[dict]] = {}
    for p in prompts:
        by_type.setdefault(p["copy_type"], []).append(p)

    picked: list[dict] = []
    seen: set[str] = set()

    # Raven-Flaggschiff zuerst sicherstellen
    raven = [p for p in prompts if p["subject_id"] == "raven"]
    if raven:
        first = rng.choice(raven)
        picked.append(first)
        seen.add(first["id"])

    # je Copy-Typ mindestens einen
    for ct in sorted(by_type):
        pool = [p for p in by_type[ct] if p["id"] not in seen]
        if pool and len(picked) < n:
            choice = rng.choice(pool)
            picked.append(choice)
            seen.add(choice["id"])

    # Rest zufällig auffüllen
    rest = [p for p in prompts if p["id"] not in seen]
    rng.shuffle(rest)
    while len(picked) < n and rest:
        picked.append(rest.pop())

    return picked[:n]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "prompts_de.jsonl")
    ap.add_argument("--smoke", type=int, default=0, help="N: stratifiziertes Smoke-Sample statt vollem Set")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    subjects = json.loads(SUBJECTS_PATH.read_text(encoding="utf-8"))["subjects"]
    copy_cfg = json.loads(COPY_TYPES_PATH.read_text(encoding="utf-8"))

    prompts = build_grid(subjects, copy_cfg)
    log.info(
        "Grid: %d Subjekte × %d Copy-Typen × %d Töne -> %d Prompts",
        len(subjects), len(copy_cfg["copy_types"]), len(copy_cfg["tones"]), len(prompts),
    )

    rng = random.Random(args.seed)
    if args.smoke:
        sample = stratified_smoke(prompts, args.smoke, rng)
        out = args.out.with_name("prompts_smoke_de.jsonl")
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as fh:
            for p in sample:
                fh.write(json.dumps(p, ensure_ascii=False) + "\n")
        log.info("Smoke-Sample (%d) -> %s", len(sample), out)
        for p in sample:
            print(f"\n[{p['subject_id']} · {p['copy_type']} · {p['tone']}/{p['length']}]")
            print(f"  {p['prompt']}")
        return

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as fh:
        for p in prompts:
            fh.write(json.dumps(p, ensure_ascii=False) + "\n")
    log.info("Volles Set (%d) -> %s", len(prompts), args.out)


if __name__ == "__main__":
    main()
