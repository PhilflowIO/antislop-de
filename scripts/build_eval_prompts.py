"""Eval-Holdout-Prompts: echte Raven-Copy für den Baseline-vs-FTPO-Augenschein.

`build_prompts.py` überspringt `profiling:false`-Subjekte (Zeile 51-52) — und
`raven` ist das einzige davon. Die Raven-Briefs waren also NIE im Trainings-
Generierungs-Grid: gleichzeitig Anwendungsfall UND ungeleakter Holdout. Genau
das richtige Material, um zu sehen, ob das FTPO-Modell den Marketing-Slop
verliert ohne den Inhalt zu verlieren.

Dieselbe Template-/Fakten-Logik wie build_prompts.py, aber NUR raven und
stratifiziert über Copy-Typen × Töne auf ~8 Prompts (Augenschein-Breite, nicht
volles Grid).

    uv run python scripts/build_eval_prompts.py            # -> data/eval_raven_prompts.jsonl
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUBJECTS_PATH = ROOT / "configs" / "copy_prompts" / "subjects_de.json"
COPY_TYPES_PATH = ROOT / "configs" / "copy_prompts" / "copy_types_de.json"

# Stratifizierte Auswahl: breit über Copy-Typen + Töne, deterministisch.
# (copy_type, tone, length) — length="na" wo das Template keine nutzt.
SELECTION = [
    ("hero", "modern", "kurz"),
    ("ueber_uns", "sachlich", "ausfuehrlich"),
    ("leistungen", "sachlich", "kurz"),
    ("vorteile", "emotional", "kurz"),
    ("ansatz", "modern", "ausfuehrlich"),
    ("cta", "emotional", "kurz"),
    ("faq", "sachlich", "ausfuehrlich"),
    ("taglines", "premium", "na"),
]


def _fakten_block(subject: dict) -> str:
    fakten = subject.get("fakten", [])
    if not fakten:
        return ""
    return "Das Wichtigste in Kürze: " + "; ".join(fakten) + "."


def _broad_selection(copy_cfg: dict) -> list[tuple[str, str, str]]:
    """Breiter Holdout: alle Copy-Typen × 3 Töne (~36 Prompts) — genug n für die
    Struktur-Statistik, längen-alternierend wo das Template Länge nutzt."""
    tones = ["sachlich", "modern", "emotional"]
    lengths = ["kurz", "ausfuehrlich"]
    sel = []
    for i, ct in enumerate(copy_cfg["copy_types"]):
        for j, tone in enumerate(tones):
            length = lengths[(i + j) % 2]
            sel.append((ct["id"], tone, length))
    return sel


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--subject", default="raven")
    ap.add_argument("--broad", action="store_true", help="~36 Prompts (alle Copy-Typen × 3 Töne)")
    args = ap.parse_args()
    if args.out is None:
        name = "eval_raven_prompts_broad.jsonl" if args.broad else "eval_raven_prompts.jsonl"
        args.out = ROOT / "data" / name

    subjects = json.loads(SUBJECTS_PATH.read_text(encoding="utf-8"))["subjects"]
    copy_cfg = json.loads(COPY_TYPES_PATH.read_text(encoding="utf-8"))
    selection = _broad_selection(copy_cfg) if args.broad else SELECTION

    subject = next(x for x in subjects if x["id"] == args.subject)
    fakten_block = _fakten_block(subject)
    ct_by_id = {ct["id"]: ct for ct in copy_cfg["copy_types"]}
    tone_by_id = {t["id"]: t for t in copy_cfg["tones"]}
    len_by_id = {x["id"]: x for x in copy_cfg["lengths"]}
    len_by_id["na"] = {"id": "na", "hint": ""}

    prompts: list[dict] = []
    for ct_id, tone_id, length_id in selection:
        ct = ct_by_id[ct_id]
        tmpl = ct["template"]
        length = len_by_id[length_id] if "{length_hint}" in tmpl else len_by_id["na"]
        prompt = tmpl.format(
            name=subject["name"],
            branche=subject["branche"],
            fakten_block=fakten_block,
            tone_hint=tone_by_id[tone_id]["hint"],
            length_hint=length["hint"],
        )
        prompt = " ".join(prompt.split())
        prompts.append(
            {
                "id": f"{subject['id']}__{ct_id}__{tone_id}__{length['id']}",
                "subject_id": subject["id"],
                "copy_type": ct_id,
                "tone": tone_id,
                "length": length["id"],
                "prompt": prompt,
            }
        )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as fh:
        for p in prompts:
            fh.write(json.dumps(p, ensure_ascii=False) + "\n")
    print(f"{len(prompts)} Eval-Prompts ({args.subject}) -> {args.out}")
    for p in prompts:
        print(f"  [{p['copy_type']} · {p['tone']}/{p['length']}]")


if __name__ == "__main__":
    main()
