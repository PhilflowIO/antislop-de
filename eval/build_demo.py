"""Side-by-side-Demo: Baseline-gemma vs. FTPO-antislop-DE auf deutscher Copy.

Der eigentliche Deliverable (#33): ein self-contained HTML, das den Unterschied
*zeigt* — jede Slop-Phrase der emergenten Banlist im Text farbig markiert, plus
ein Kopf-Panel mit den objektiven Metriken (Phrasen-Slop, struktureller Slop,
Passiv, Diversität, Capability) als Vorher/Nachher.

Wissenschaftlich ehrlich: zeigt den klaren Sieg (Phrasen-Slop) UND die offene
Flanke (Struktur/Passiv) nebeneinander — keine Cherry-Picks.

    uv run python eval/build_demo.py            # nutzt den breiten du-Holdout
    uv run python eval/build_demo.py --compare data/eval_raven_compare_t0.7.json
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

import markdown as _md

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))

from run_holdout_eval import _load_banphrases, _side  # noqa: E402

REF_PATH = ROOT / "eval" / "structural_reference.json"
REF_LIVELY = "dialog/literary (cultural/dibilit)"
BANLIST = ROOT / "data" / "eval_banlists" / "banned_slop_phrases.json"
DEFAULT_COMPARE = ROOT / "data" / "eval_raven_compare_broad_t0.7.json"
CAPABILITY = ROOT / "data" / "eval_capability.json"


# Sentinels überleben die Markdown-Konvertierung — alnum-Tokens (Control-Chars wie
# \x00 werden vom Markdown-Prozessor verschluckt), damit Slop-Markierung + Render
# nicht kollidieren.
_MK_OPEN, _MK_CLOSE = "zZmarkopenZz", "zZmarkcloseZz"


def _highlight(text: str, pattern: re.Pattern | None) -> tuple[str, int]:
    """Rendert Modell-Output als Markdown→HTML, Slop-Phrasen in <mark>.
    Reihenfolge: escapen → Slop mit Sentinels markieren → Markdown rendern →
    Sentinels in <mark> tauschen. Gibt (html, n_treffer)."""
    safe = html.escape(text)
    hits = 0
    if pattern is not None:
        def _wrap(m):
            nonlocal hits
            hits += 1
            return f"{_MK_OPEN}{m.group(0)}{_MK_CLOSE}"
        # auf dem escapten Text matchen (deutsche Phrasen unberührt vom Escapen)
        safe = pattern.sub(_wrap, safe)
    rendered = _md.markdown(safe, extensions=["nl2br", "sane_lists"])
    rendered = rendered.replace(_MK_OPEN, "<mark>").replace(_MK_CLOSE, "</mark>")
    return rendered, hits


def _build_pattern(phrases: list[str]) -> re.Pattern:
    # längste zuerst, damit die spezifischste Phrase markiert wird
    ordered = sorted({p for p in phrases if len(p) >= 4}, key=len, reverse=True)
    return re.compile("|".join(re.escape(p) for p in ordered), re.IGNORECASE)


def _metric_panel(base: dict, ftpo: dict, cap: dict | None) -> str:
    def row(label, b, f, good_down=True):
        try:
            better = (f < b) if good_down else (f > b)
        except TypeError:
            better = False
        cls = "win" if better else "loss"
        arrow = "▼" if good_down else "▲"
        return (f"<tr><td>{label}</td><td>{b}</td>"
                f"<td class='{cls}'>{f} {arrow if better else '✗'}</td></tr>")

    rows = [
        row("Slop-Phrasen / 1000 Tokens", base["banlist_hits_per_1k_tokens"], ftpo["banlist_hits_per_1k_tokens"]),
        row("struktureller Slop-Score (Median)", base["median_slop_score"], ftpo["median_slop_score"]),
        row("Passiv-Quote (Median)", base["median_passive_ratio"], ftpo["median_passive_ratio"]),
        row("Nominalisierung /100 (Median)", base["median_nominalization_per_100"], ftpo["median_nominalization_per_100"]),
        row("Lexik. Diversität MATTR", base["median_mattr"], ftpo["median_mattr"], good_down=False),
        row("degenerierte Run-ons", base["n_degenerate"], ftpo["n_degenerate"]),
    ]
    if cap:
        rows.append(row("GSM8K Accuracy %", cap["baseline"]["gsm8k"], cap["ftpo"]["gsm8k"], good_down=False))
        rows.append(row("MMLU Accuracy %", cap["baseline"]["mmlu"], cap["ftpo"]["mmlu"], good_down=False))
    return (
        "<table class='metrics'><tr><th>Metrik</th><th>Baseline gemma</th>"
        "<th>FTPO antislop-DE</th></tr>" + "".join(rows) + "</table>"
    )


CSS = """
body{font:15px/1.55 -apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:#0f1115;color:#e6e6e6}
.wrap{max-width:1200px;margin:0 auto;padding:32px}
h1{font-size:24px;margin:0 0 4px}.sub{color:#9aa4b2;margin:0 0 24px}
table.metrics{border-collapse:collapse;width:100%;margin:0 0 28px;background:#171a21;border-radius:8px;overflow:hidden}
.metrics th,.metrics td{padding:9px 14px;text-align:left;border-bottom:1px solid #232733}
.metrics th{background:#1d212b;color:#cdd5e0;font-weight:600}
.metrics td.win{color:#5ad17f;font-weight:600}.metrics td.loss{color:#e8825a;font-weight:600}
.pair{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:0 0 18px}
.col{background:#171a21;border-radius:8px;padding:14px 16px;border:1px solid #232733}
.col h3{margin:0 0 8px;font-size:13px;letter-spacing:.04em;text-transform:uppercase;color:#9aa4b2}
.col.base h3{color:#e8825a}.col.ftpo h3{color:#5ad17f}
.lbl{font-size:12px;color:#6f7888;margin:22px 0 6px;border-top:1px solid #232733;padding-top:14px}
mark{background:#5c1d10;color:#ffb59a;border-radius:3px;padding:0 2px}
.cnt{font-size:12px;color:#9aa4b2;margin-top:8px}
.copy{font-size:14px;line-height:1.5}
.copy h1,.copy h2,.copy h3,.copy h4{font-size:15px;margin:12px 0 4px;color:#dfe6ef;text-transform:none;letter-spacing:0}
.copy p{margin:6px 0}.copy ul,.copy ol{margin:6px 0;padding-left:20px}.copy li{margin:3px 0}
.copy strong{color:#fff}
"""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--compare", type=Path, default=DEFAULT_COMPARE)
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "eval_demo.html")
    args = ap.parse_args()

    data = json.loads(args.compare.read_text(encoding="utf-8"))
    phrases = _load_banphrases(BANLIST)
    pattern = _build_pattern(phrases)
    ref_lively = json.loads(REF_PATH.read_text(encoding="utf-8"))[REF_LIVELY]
    cap = json.loads(CAPABILITY.read_text(encoding="utf-8")) if CAPABILITY.exists() else None

    base = _side([d["baseline"] for d in data], phrases, ref_lively)
    ftpo = _side([d["ftpo"] for d in data], phrases, ref_lively)

    body = [f"<div class='wrap'><h1>Anti-Slop DE — Baseline gemma-3-12b-it vs. FTPO</h1>"
            f"<p class='sub'>{len(data)} Raven-Holdout-Prompts (nie im Training) · "
            f"{args.compare.name} · Slop-Phrasen der emergenten Banlist <mark>markiert</mark></p>"]
    body.append(_metric_panel(base, ftpo, cap))

    for d in data:
        b_html, b_hits = _highlight(d["baseline"], pattern)
        f_html, f_hits = _highlight(d["ftpo"], pattern)
        lbl = f"{d.get('copy_type','?')} · {d.get('tone','?')}/{d.get('length','?')}"
        body.append(f"<div class='lbl'>{html.escape(lbl)}</div>")
        body.append(
            "<div class='pair'>"
            f"<div class='col base'><h3>Baseline</h3><div class='copy'>{b_html}</div>"
            f"<div class='cnt'>{b_hits} Slop-Treffer</div></div>"
            f"<div class='col ftpo'><h3>FTPO antislop-DE</h3><div class='copy'>{f_html}</div>"
            f"<div class='cnt'>{f_hits} Slop-Treffer</div></div>"
            "</div>"
        )
    body.append("</div>")

    doc = f"<!doctype html><html lang='de'><head><meta charset='utf-8'>" \
          f"<title>Anti-Slop DE Demo</title><style>{CSS}</style></head><body>" \
          + "".join(body) + "</body></html>"
    args.out.write_text(doc, encoding="utf-8")
    print(f"Demo -> {args.out}  ({len(data)} Paare, "
          f"Slop/1k {base['banlist_hits_per_1k_tokens']}→{ftpo['banlist_hits_per_1k_tokens']}, "
          f"capability={'ja' if cap else 'nein'})")


if __name__ == "__main__":
    main()
