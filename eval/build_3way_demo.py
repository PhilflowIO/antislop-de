"""3-Wege-Scan-Demo: Baseline vs Prompt-only vs v2-FTPO, je Prompt nebeneinander.

Rendert die 36 Holdout-Prompts in drei Spalten (Markdown→HTML) und markiert das
blinde LLM-Judge-Urteil pro Prompt (grün = bester, rot = schlechtester). Schnell
scannbar, damit das Auge selbst entscheidet, ob der Finetune einen Prompt schlägt.

    uv run python eval/build_3way_demo.py
    -> data/eval_3way_demo.html
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import markdown as _md

ROOT = Path(__file__).resolve().parent.parent
V2 = ROOT / "data" / "eval_raven_compare_broad_t0.7_v2.json"
# Der ursprüngliche promptonly-Lauf war defekt: die Datei ohne `_rerun` enthält in
# allen 36 Fällen byteidentische Kopien der Baseline-Texte, der Arm wurde nie
# generiert. Gültig ist nur `_rerun` (Nachlauf 2026-09-04, siehe README).
PO = ROOT / "data" / "eval_raven_compare_broad_t0.7_promptonly_rerun.json"
OUT = ROOT / "data" / "eval_3way_demo.html"

# Blindes Judge-Urteil (best/worst je Prompt, A/B/C im geseedeten Blind-File).
# ACHTUNG: diese Urteile stammen aus dem defekten Lauf, in dem der Prompt-only-Arm
# byteidentisch mit der Baseline war. Sie sind ungültig und müssen auf dem
# `_rerun`-Arm neu erhoben werden. Die gültigen Aggregate stehen in der README.
VERDICTS = {
    "raven__hero__sachlich__kurz": ("A", "C"), "raven__hero__modern__ausfuehrlich": ("B", "A"),
    "raven__hero__emotional__kurz": ("A", "C"), "raven__ueber_uns__sachlich__ausfuehrlich": ("A", "B"),
    "raven__ueber_uns__modern__kurz": ("A", "C"), "raven__ueber_uns__emotional__ausfuehrlich": ("B", "C"),
    "raven__leistungen__sachlich__kurz": ("C", "A"), "raven__leistungen__modern__ausfuehrlich": ("A", "B"),
    "raven__leistungen__emotional__kurz": ("A", "B"), "raven__feature__sachlich__ausfuehrlich": ("A", "C"),
    "raven__feature__modern__kurz": ("B", "C"), "raven__feature__emotional__ausfuehrlich": ("C", "A"),
    "raven__vorteile__sachlich__kurz": ("A", "B"), "raven__vorteile__modern__ausfuehrlich": ("C", "B"),
    "raven__vorteile__emotional__kurz": ("A", "C"), "raven__ansatz__sachlich__ausfuehrlich": ("C", "B"),
    "raven__ansatz__modern__kurz": ("A", "B"), "raven__ansatz__emotional__ausfuehrlich": ("C", "A"),
    "raven__cta__sachlich__kurz": ("B", "A"), "raven__cta__modern__ausfuehrlich": ("B", "A"),
    "raven__cta__emotional__kurz": ("C", "A"), "raven__intro__sachlich__ausfuehrlich": ("B", "A"),
    "raven__intro__modern__kurz": ("A", "C"), "raven__intro__emotional__ausfuehrlich": ("C", "A"),
    "raven__pricing_intro__sachlich__kurz": ("B", "C"), "raven__pricing_intro__modern__ausfuehrlich": ("B", "C"),
    "raven__pricing_intro__emotional__kurz": ("A", "C"), "raven__faq__sachlich__ausfuehrlich": ("A", "C"),
    "raven__faq__modern__kurz": ("A", "B"), "raven__faq__emotional__ausfuehrlich": ("B", "A"),
    "raven__taglines__sachlich__na": ("A", "B"), "raven__taglines__modern__na": ("C", "B"),
    "raven__taglines__emotional__na": ("C", "B"), "raven__leistungsseite__sachlich__ausfuehrlich": ("B", "A"),
    "raven__leistungsseite__modern__kurz": ("C", "A"), "raven__leistungsseite__emotional__ausfuehrlich": ("B", "C"),
}

ARMS = {
    "baseline": "Baseline (plain gemma)",
    "promptonly": "Prompt-only (plain + Anti-Slop-Prompt)",
    "v2": "v2-FTPO (Finetune)",
}


def _render(text: str) -> str:
    return _md.markdown(text.strip(), extensions=["nl2br", "sane_lists"])


def main() -> None:
    v2 = json.loads(V2.read_text(encoding="utf-8"))
    po = {d["id"]: d["promptonly"] for d in json.loads(PO.read_text(encoding="utf-8"))}

    # Geseedetes Blind-Mapping rekonstruieren (random.Random(42), identische
    # Iteration + cands-Reihenfolge wie beim A/B-Bau) → label A/B/C zurück auf Arm.
    rnd = random.Random(42)
    label_to_arm = {}  # id -> {"A": arm, ...}
    for d in v2:
        cands = [("baseline", None), ("promptonly", None), ("v2", None)]
        rnd.shuffle(cands)
        label_to_arm[d["id"]] = {lab: arm for lab, (arm, _) in zip("ABC", cands)}

    wins = {a: 0 for a in ARMS}
    losses = {a: 0 for a in ARMS}
    for cid, (best, worst) in VERDICTS.items():
        wins[label_to_arm[cid][best]] += 1
        losses[label_to_arm[cid][worst]] += 1

    css = """
    body{font:15px/1.55 -apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:#0f1115;color:#e6e6e6}
    header{position:sticky;top:0;background:#161a22;padding:14px 20px;border-bottom:1px solid #2a2f3a;z-index:5}
    h1{font-size:18px;margin:0 0 6px} .sub{color:#9aa4b2;font-size:13px}
    .score{display:inline-block;margin-right:16px;font-size:13px}
    .prompt{padding:18px 20px;border-bottom:1px solid #222}
    .pid{color:#7aa2f7;font-size:13px;font-weight:600;margin-bottom:10px}
    .cols{display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px}
    .col{background:#161a22;border:1px solid #2a2f3a;border-radius:8px;padding:12px 14px;overflow:hidden}
    .col h3{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:#9aa4b2;margin:0 0 8px;font-weight:600}
    .col.best{border-color:#2ea043;box-shadow:inset 0 0 0 1px #2ea043}
    .col.worst{border-color:#cf3b3b;box-shadow:inset 0 0 0 1px #cf3b3b}
    .badge{float:right;font-size:11px;padding:1px 7px;border-radius:10px;font-weight:600}
    .badge.best{background:#16331f;color:#3fb950} .badge.worst{background:#3a1b1b;color:#f06a6a}
    .col :is(h1,h2,h3,h4){font-size:14px;color:#e6e6e6;margin:.5em 0 .3em}
    .col p{margin:.4em 0} .col ul,.col ol{margin:.3em 0;padding-left:1.2em} .col li{margin:.15em 0}
    .col strong{color:#fff}
    """
    parts = [f"<!doctype html><meta charset=utf-8><title>Raven Copy — 3-Wege-Scan</title><style>{css}</style>"]
    parts.append("<header><h1>Raven Website-Copy — 3-Wege-Scan (n=36, temp 0.7, du-gepinnt)</h1>")
    parts.append('<div class="sub">')
    parts.append(
        f'<span class="score">Blind-Judge BESTER: '
        + " · ".join(f"{ARMS[a].split(' (')[0]} <b>{wins[a]}</b>" for a in ARMS) + "</span>"
    )
    parts.append(
        f'<span class="score">SCHLECHTESTER: '
        + " · ".join(f"{ARMS[a].split(' (')[0]} <b>{losses[a]}</b>" for a in ARMS) + "</span>"
    )
    parts.append('</div><div class="sub">grüner Rahmen = vom blinden Judge als bester gewählt · roter = schlechtester</div></header>')

    for d in v2:
        cid = d["id"]
        best, worst = VERDICTS[cid]
        l2a = label_to_arm[cid]
        best_arm, worst_arm = l2a[best], l2a[worst]
        texts = {"baseline": d["baseline"], "promptonly": po[cid], "v2": d["ftpo"]}
        parts.append('<div class="prompt">')
        parts.append(f'<div class="pid">{cid} &nbsp;·&nbsp; {d.get("copy_type")} / {d.get("tone")} / {d.get("length")}</div>')
        parts.append('<div class="cols">')
        for arm in ("baseline", "promptonly", "v2"):
            cls = "best" if arm == best_arm else "worst" if arm == worst_arm else ""
            badge = ('<span class="badge best">★ bester</span>' if arm == best_arm
                     else '<span class="badge worst">✗ schlechtester</span>' if arm == worst_arm else "")
            parts.append(f'<div class="col {cls}"><h3>{ARMS[arm]}{badge}</h3>{_render(texts[arm])}</div>')
        parts.append("</div></div>")

    OUT.write_text("".join(parts), encoding="utf-8")
    print(f"-> {OUT}  ({len(v2)} Prompts, 3 Spalten)")


if __name__ == "__main__":
    main()
