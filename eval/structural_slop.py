"""Struktureller Slop-Score für Deutsch (Punkt 4b).

Der n-gram-Ratio fängt Phrasen-Slop ("ganzheitlicher ansatz"), aber NICHT den
strukturellen Teil des deutschen KI-/Behördendeutsch: Nominalstil, Schachtelsätze,
Passiv-Überhang. Zwei Texte mit identischer Wortfrequenz können strukturell dröge
vs. lebendig sein. Dieses Modul misst genau das — als Ergänzung zum n-gram-Score.

Verwendung:
  analyze(texts) -> dict mit Struktur-Metriken (höher = nominaler/dröger)
  CLI:  structural_slop.py <corpus.jsonl|.txt> [--field text]
        structural_slop.py compare <human.jsonl> <modell.jsonl>

Metriken (alle pro Satz/100 Tokens normalisiert, registerstabil):
  nominalization_per_100   Nominalisierungen (-ung/-heit/-keit/-ion/-ität/...) je 100 Tokens
  noun_verb_ratio          Nomen / Verben (Nominalstil-Kernindikator)
  mean_sentence_len        Tokens je Satz (Schachtelsatz-Proxy)
  clauses_per_sentence     finite Verben je Satz (Klausel-Schachtelung)
  mean_parse_depth         mittlere Dependenz-Baumtiefe (Verschachtelung)
  passive_ratio            Passiv-Klauseln / Sätze
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import spacy

_NOMINAL_SUFFIX = re.compile(r"(ung|heit|keit|ion|ierung|ität|ismus|nis|tum|schaft|barkeit|losigkeit)$",
                             re.IGNORECASE)
_NLP = None


def nlp():
    global _NLP
    if _NLP is None:
        _NLP = spacy.load("de_core_news_sm", disable=["ner", "lemmatizer"])
        _NLP.max_length = 2_000_000
    return _NLP


def _tree_depth(token) -> int:
    d = 0
    while token.head != token:
        token = token.head
        d += 1
        if d > 100:
            break
    return d


def analyze(texts: list[str]) -> dict:
    """Aggregiert Struktur-Metriken über eine Liste von Texten."""
    n_tok = n_sent = n_noun = n_verb = n_nominal = n_passive = 0
    n_finite = depth_sum = depth_n = 0
    for doc in nlp().pipe((t for t in texts if t and t.strip()), batch_size=64):
        for sent in doc.sents:
            toks = [t for t in sent if not t.is_space and not t.is_punct]
            if len(toks) < 3:
                continue
            n_sent += 1
            n_tok += len(toks)
            sent_finite = 0
            has_werden_pass = False
            for t in toks:
                if t.pos_ in ("NOUN", "PROPN"):
                    n_noun += 1
                    if t.pos_ == "NOUN" and _NOMINAL_SUFFIX.search(t.text):
                        n_nominal += 1
                elif t.pos_ in ("VERB", "AUX"):
                    n_verb += 1
                    if "Fin" in t.morph.get("VerbForm"):
                        sent_finite += 1
                    # Passiv: werden-AUX + Partizip im selben Satz
                    if t.pos_ == "AUX" and t.text.lower().startswith(("werd", "wird", "wurd", "worden")):
                        has_werden_pass = True
                depth_sum += _tree_depth(t)
                depth_n += 1
            n_finite += sent_finite
            if has_werden_pass and any("Part" in t.morph.get("VerbForm") for t in toks):
                n_passive += 1

    if n_sent == 0 or n_tok == 0:
        return {}
    return {
        "n_sentences": n_sent,
        "n_tokens": n_tok,
        "nominalization_per_100": round(100 * n_nominal / n_tok, 2),
        "noun_verb_ratio": round(n_noun / max(n_verb, 1), 2),
        "mean_sentence_len": round(n_tok / n_sent, 1),
        "clauses_per_sentence": round(n_finite / n_sent, 2),
        "mean_parse_depth": round(depth_sum / max(depth_n, 1), 2),
        "passive_ratio": round(n_passive / n_sent, 3),
    }


def structural_slop_score(m: dict, ref: dict) -> float:
    """Ein zusammengesetzter Score: wie weit liegt m ÜBER der menschlichen Referenz ref?
    >0 = nominaler/dröger als Mensch (= struktureller Slop). Mittel der relativen Aufschläge."""
    keys = ["nominalization_per_100", "noun_verb_ratio", "mean_sentence_len",
            "mean_parse_depth", "passive_ratio"]
    deltas = [(m[k] - ref[k]) / ref[k] for k in keys if k in m and ref.get(k)]
    return round(100 * sum(deltas) / len(deltas), 1) if deltas else float("nan")


def _load(path: Path, field: str) -> list[str]:
    if path.suffix == ".jsonl":
        out = []
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                o = json.loads(line)
                out.append(o.get(field) or o.get("output") or o.get("text") or "")
            except json.JSONDecodeError:
                continue
        return out
    return [b for b in path.read_text(encoding="utf-8").split("\n\n") if b.strip()]


def _print(label: str, m: dict) -> None:
    print(f"\n── {label} ({m.get('n_sentences', 0)} Sätze, {m.get('n_tokens', 0)} Tokens) ──")
    for k in ["nominalization_per_100", "noun_verb_ratio", "mean_sentence_len",
              "clauses_per_sentence", "mean_parse_depth", "passive_ratio"]:
        print(f"  {k:<24} {m.get(k, '—')}")


def main() -> None:
    args = sys.argv[1:]
    if args and args[0] == "compare" and len(args) >= 3:
        field = "text"
        a, b = analyze(_load(Path(args[1]), field)), analyze(_load(Path(args[2]), field))
        _print(f"HUMAN  {Path(args[1]).name}", a)
        _print(f"MODELL {Path(args[2]).name}", b)
        print(f"\n  >>> struktureller Slop-Score (Modell vs Human): {structural_slop_score(b, a)} "
              "(>0 = nominaler/dröger als Mensch)")
        return
    field = args[args.index("--field") + 1] if "--field" in args else "text"
    paths = [a for a in args if not a.startswith("--") and a != field]
    for p in paths:
        _print(Path(p).name, analyze(_load(Path(p), field)))


if __name__ == "__main__":
    main()
