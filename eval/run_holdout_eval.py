"""Eval-Rung 1: objektive Slop-/Diversitäts-Metriken auf dem Raven-Holdout.

Baseline-gemma vs. FTPO-Modell, gemessen an den Achsen, die n-grams NICHT sehen:
  - struktureller Slop (Nominalstil/Passiv/Satzlänge) vs. lebendiger Mensch
  - lexikalische Diversität (TTR/RTTR/MATTR)
  - Treffer der emergenten Slop-Banlist (Phrasen), pro 1000 Tokens normalisiert

Liest die schon erzeugten Side-by-side-Generate (`data/eval_raven_compare*.json`),
braucht keine GPU. Schreibt `data/eval_holdout_report.json` + druckt eine Tabelle.

    uv run python eval/run_holdout_eval.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))

from diversity import diversity  # noqa: E402
from structural_slop import analyze, structural_slop_score  # noqa: E402

# Menschliche Struktur-Referenz: dialog/literary = lebendiges, natürliches Deutsch
# — das Register, dem gute Web-Copy nahekommen soll. academic/encyclopedic dienen
# als „dröge" Gegenpole zur Einordnung (nur Anzeige, nicht im Score).
REF_PATH = ROOT / "eval" / "structural_reference.json"
REF_LIVELY = "dialog/literary (cultural/dibilit)"
REF_POLES = ["encyclopedic (web/wikipedia)", "academic (scientific/openalex)"]

COMPARE_FILES = {
    "temp1.0": ROOT / "data" / "eval_raven_compare.json",
    "temp0.7": ROOT / "data" / "eval_raven_compare_t0.7.json",
    # Breiter Holdout (n=36): rep_penalty AUS vs. AN (#38) — der Run-on-Test.
    "broad temp0.7": ROOT / "data" / "eval_raven_compare_broad_t0.7.json",
    "broad temp0.7 rep1.2": ROOT / "data" / "eval_raven_compare_broad_t0.7_rp1.2.json",
}
BANLIST = ROOT / "data" / "eval_banlists" / "banned_slop_phrases.json"


def _load_banphrases(path: Path) -> list[str]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        out = list(raw.keys())
    else:
        out = []
        for x in raw:
            if isinstance(x, str):
                out.append(x)
            elif isinstance(x, (list, tuple)) and x:  # [phrase, count]-Paare
                out.append(x[0])
            elif isinstance(x, dict):
                out.append(x.get("phrase") or x.get("ngram") or next(iter(x.values())))
    return [p for p in out if isinstance(p, str) and p]


def _strip_md(t: str) -> str:
    """Markdown-Markup raus, bevor spaCy die Struktur misst — Header/Bold-Labels
    sind verblose Nominalphrasen und würden Nominalstil/Passiv künstlich aufblähen.
    (Geprüft: die Struktur-Regression bleibt auch ohne Markup bestehen, ist also
    echt — Stripping macht den Wert nur sauber.)"""
    t = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", t)          # Links
    t = re.sub(r"^\s*[-•\d]+[.\)]?\s+", "", t, flags=re.M)  # Listen-Marker
    t = re.sub(r"[#*_`>]+", " ", t)                    # Markup-Zeichen
    return t


def _banhits(text: str, phrases: list[str]) -> int:
    t = text.lower()
    return sum(t.count(p.lower()) for p in phrases)


# Emergente Tics (#42): Marker, die erst durchs FTPO-Training hochkamen und die die
# STATISCHE Banlist nicht sah — die slop/1k-Metrik war blind dafür und täuschte „grün"
# (Spezialisten-Review 2026-06-09: inklusive 14→78, kristallklar 2→13, smart 17→55).
# Hier per Substring getrackt (NICHT zwingend gebannt) — Tracking ≠ Ban, der Sinn ist,
# Slop-Umverteilung sichtbar zu machen. Vergleich FTPO vs Baseline pro 1k Tokens.
# Phil-Review 2026-06-09: kristallklar/souverän/absolut/nahtlos/ruckzuck/kinderleicht
# sind GUTE Wörter (kein Slop) → raus aus dem Tracking. Bleibt: echte Überuse-Crutches.
TICS = [
    "inklusive", "smart", "blitz", "easy peasy", "basta", "kein ding",
]


def _tic_hits(text: str) -> dict[str, int]:
    t = text.lower()
    return {tic: t.count(tic) for tic in TICS}


# Degenerate-Output-Schwellen: ein echter Satz hat selten >50 Tokens; n/v>8 ohne
# finite Verben ist ein nominaler Run-on (FTPO-Failure-Mode „inklusive … inklusive").
DEGEN_SENT_LEN = 50.0
DEGEN_NV = 8.0
# Token-Schleifen-Schwellen (#40): der nominale Check oben verpasst Verb-Spam-
# Kollapse („gilt gilt gilt", „gilt heißt gilt heißt"), weil die n/v-Ratio dabei
# NIEDRIG ist. Diese zwei fangen wörtliche Wiederholung direkt am Token-Strom.
DEGEN_CONSEC = 5   # gleiches Token ≥5× hintereinander
DEGEN_BIGRAM = 6   # dasselbe Bigramm ≥6× im Text (alternierende „A B A B"-Schleife)


def _median(xs: list[float]) -> float | None:
    s = sorted(x for x in xs if x is not None)
    if not s:
        return None
    n = len(s)
    return round(s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2, 2)


def _token_loops(text: str) -> tuple[int, int]:
    """(max gleiche Tokens hintereinander, max Wiederholung eines Bigramms).
    Fängt die Kollaps-Klasse, die der nominale Degeneracy-Check nicht sieht."""
    from collections import Counter

    toks = re.findall(r"\w+", text.lower())
    if not toks:
        return 0, 0
    consec = best = 1
    for i in range(1, len(toks)):
        best = best + 1 if toks[i] == toks[i - 1] else 1
        consec = max(consec, best)
    bg = Counter(tuple(toks[i:i + 2]) for i in range(len(toks) - 1))
    bigram = bg.most_common(1)[0][1] if bg else 0
    return consec, bigram


def _is_degenerate(m: dict, text: str = "") -> bool:
    if m and (
        m.get("mean_sentence_len", 0) > DEGEN_SENT_LEN
        or m.get("noun_verb_ratio", 0) > DEGEN_NV
    ):
        return True
    consec, bigram = _token_loops(text)
    return consec >= DEGEN_CONSEC or bigram >= DEGEN_BIGRAM


def _side(texts: list[str], phrases: list[str], ref_lively: dict) -> dict:
    # Pro Text rechnen → Median ist robust gegen einzelne degenerierte Ausreißer
    # (Korpus-Pooling lässt einen 200-Token-Run-on den Schnitt dominieren).
    per_text = []
    degen = 0
    for t in texts:
        clean = _strip_md(t)
        m = analyze([clean])
        if not m:
            continue
        deg = _is_degenerate(m, clean)
        degen += int(deg)
        per_text.append(
            {
                "score": structural_slop_score(m, ref_lively),
                "nominalization_per_100": m.get("nominalization_per_100"),
                "passive_ratio": m.get("passive_ratio"),
                "mattr": diversity([clean]).get("mattr"),
                "degenerate": deg,
            }
        )
    pooled = analyze([_strip_md(t) for t in texts])
    hits = sum(_banhits(t, phrases) for t in texts)
    per_1k = round(1000 * hits / pooled["n_tokens"], 2) if pooled.get("n_tokens") else None
    # Emergente Tics separat (#42) — die Banlist-Metrik oben sieht sie nicht.
    tic_total: dict[str, int] = {tic: 0 for tic in TICS}
    for t in texts:
        for tic, c in _tic_hits(t).items():
            tic_total[tic] += c
    tic_sum = sum(tic_total.values())
    tic_per_1k = round(1000 * tic_sum / pooled["n_tokens"], 2) if pooled.get("n_tokens") else None
    top_tics = sorted(tic_total.items(), key=lambda kv: -kv[1])[:5]
    return {
        "n_texts": len(per_text),
        "n_degenerate": degen,
        "tic_per_1k_tokens": tic_per_1k,
        "top_tics": top_tics,
        "median_slop_score": _median([p["score"] for p in per_text]),
        "median_nominalization_per_100": _median([p["nominalization_per_100"] for p in per_text]),
        "median_passive_ratio": _median([p["passive_ratio"] for p in per_text]),
        "median_mattr": _median([p["mattr"] for p in per_text]),
        "pooled_slop_score": structural_slop_score(pooled, ref_lively),
        "banlist_hits": hits,
        "banlist_hits_per_1k_tokens": per_1k,
    }


def _fmt(v) -> str:
    return "—" if v is None else str(v)


def main() -> None:
    ref = json.loads(REF_PATH.read_text(encoding="utf-8"))
    ref_lively = ref[REF_LIVELY]
    phrases = _load_banphrases(BANLIST)
    print(f"Banlist-Phrasen: {len(phrases)} · Struktur-Referenz (lebendig): {REF_LIVELY}\n")

    report: dict = {"reference_lively": REF_LIVELY, "results": {}}
    for tag, path in COMPARE_FILES.items():
        if not path.exists():
            print(f"[skip] {path.name} fehlt")
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        base = _side([d["baseline"] for d in data], phrases, ref_lively)
        ftpo = _side([d["ftpo"] for d in data], phrases, ref_lively)
        report["results"][tag] = {"baseline": base, "ftpo": ftpo, "n_pairs": len(data)}

        print(f"══════════ {tag} ({len(data)} Prompts) ══════════")
        rows = [
            ("struktureller Slop-Score MEDIAN (↓ besser)", "median_slop_score"),
            ("  median nominalization/100 (↓)", "median_nominalization_per_100"),
            ("  median passive_ratio (↓)", "median_passive_ratio"),
            ("  pooled slop-score (ausreißer-anfällig)", "pooled_slop_score"),
            ("degenerierte Outputs (run-on)", "n_degenerate"),
            ("Slop-Treffer / 1000 Tok (↓ besser)", "banlist_hits_per_1k_tokens"),
            ("emergente Tics / 1000 Tok (↓ besser)", "tic_per_1k_tokens"),
            ("MATTR Diversität MEDIAN (↑ besser)", "median_mattr"),
        ]
        print(f"{'Metrik':<44} {'Baseline':>10} {'FTPO':>10}")
        for label, k in rows:
            print(f"{label:<44} {_fmt(base[k]):>10} {_fmt(ftpo[k]):>10}")
        # Top-Tics (#42): macht Slop-Umverteilung sichtbar, die die Banlist-Metrik verschweigt.
        bt = {t: c for t, c in base["top_tics"]}
        print("  Top-Tics (FTPO, base→ftpo):  " + " · ".join(
            f"{t} {bt.get(t, 0)}→{c}" for t, c in ftpo["top_tics"] if c))
        print(f"\n  Referenz Slop-Score: Mensch lebendig = 0; "
              f"encyclopedic={structural_slop_score(ref[REF_POLES[0]], ref_lively)}, "
              f"academic={structural_slop_score(ref[REF_POLES[1]], ref_lively)}")
        print()

    REPORT_OUT = ROOT / "data" / "eval_holdout_report.json"
    REPORT_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"-> {REPORT_OUT}")


if __name__ == "__main__":
    main()
