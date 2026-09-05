"""Lexikalische Diversität für Deutsch (Eval-Rung 1).

Slop ist oft auch *arm* — dieselben Floskeln, dieselben Füllwörter. Diversität
misst das Gegenstück zum n-gram-/Struktur-Slop: wie viele *verschiedene* Wörter
nutzt der Text.

  TTR   = Types / Tokens               (klassisch, ABER längen-sensitiv:
                                         längerer Text → mechanisch niedrigere TTR)
  RTTR  = Types / sqrt(Tokens)         (Guiraud, teil-korrigiert)
  MATTR = Mittel der TTR über ein gleitendes Fenster (W Tokens)
                                         längen-ROBUST → der faire Vergleichswert,
                                         wenn zwei Korpora unterschiedlich lang sind

Tokenisierung konsistent mit structural_slop: spaCy-Tokens, nur alphabetische,
kleingeschrieben (Markdown-Markup/Satzzeichen fallen raus). Pooling über alle
Texte einer Seite (Baseline bzw. FTPO).
"""

from __future__ import annotations

import math

from structural_slop import nlp


def _tokens(texts: list[str]) -> list[str]:
    out: list[str] = []
    for doc in nlp().pipe((t for t in texts if t and t.strip()), batch_size=64):
        out.extend(t.text.lower() for t in doc if t.is_alpha)
    return out


def _mattr(tokens: list[str], window: int = 50) -> float:
    """Moving-Average Type-Token-Ratio — längen-robust."""
    if len(tokens) < window:
        return len(set(tokens)) / len(tokens) if tokens else 0.0
    ratios = [
        len(set(tokens[i : i + window])) / window
        for i in range(len(tokens) - window + 1)
    ]
    return sum(ratios) / len(ratios)


def diversity(texts: list[str], mattr_window: int = 50) -> dict:
    """Aggregiert TTR/RTTR/MATTR über eine Liste von Texten (gepoolt)."""
    toks = _tokens(texts)
    n = len(toks)
    if n == 0:
        return {}
    types = len(set(toks))
    return {
        "n_tokens": n,
        "n_types": types,
        "ttr": round(types / n, 4),
        "rttr": round(types / math.sqrt(n), 2),
        "mattr": round(_mattr(toks, mattr_window), 4),
        "mattr_window": mattr_window,
    }
