"""Schritt-2 Banlist-Bau: emergente Slop-Kandidaten aus dem vollen Lauf, nach
Branchen-Spread vor-sortiert für Phils Hand-Review.

Der eigentliche Slop-Diskriminator ist nicht „fehlt in der Baseline" (das
flaggt auch korrekte Fachbegriffe), sondern **Branchen-Spread**: eine Floskel
taucht in VIELEN der 15 Branchen auf, ein Fachbegriff/Fakt nur in einer. Liest
die gecachten Generierungen (data/samples_full.jsonl) — keine API nötig.

Output data/banlist_candidates.tsv mit Vor-Markierung (Spalte `keep`):
    slop?   cross-cutting (>=5 Branchen, baseline selten) -> wahrscheinlich Slop
    strike  single-domain (<=2 Branchen)                  -> Fachbegriff/Fakt
    review  Mittelfeld                                     -> Augenschein

    uv run python scripts/build_banlist.py
"""

from __future__ import annotations

import json
import logging
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from baseline import content_tokens  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("build_banlist")

SAMPLES = ROOT / "data" / "samples_full.jsonl"
PROFILE = ROOT / "data" / "baseline" / "human_writing_profile_de.json"
OUT = ROOT / "data" / "banlist_candidates.tsv"

MIN_COUNT = 20  # selteneres ignorieren (Rauschen)
MAX_BASELINE = 300  # darüber ist es natürliches Deutsch, kein Slop

# Copy-Typ-Vokabular: steht in jedem Prompt des Typs -> spreadet künstlich über
# alle Branchen (Template-Echo), ist aber kein Slop. Raus aus dem Diff.
COPY_TYPE_ECHO = {"faq", "taglines", "tagline", "slogans", "slogan"}


def main() -> None:
    if not SAMPLES.is_file():
        sys.exit(f"{SAMPLES} fehlt — erst `generate_samples.py --full` laufen lassen.")

    prof = json.loads(PROFILE.read_text(encoding="utf-8"))["human-authored"]
    base = {x["ngram"]: x["frequency"] for x in prof["top_bigrams"]}
    base.update({x["ngram"]: x["frequency"] for x in prof["top_trigrams"]})

    subjects = json.loads((ROOT / "configs/copy_prompts/subjects_de.json").read_text(encoding="utf-8"))["subjects"]
    stop = set(COPY_TYPE_ECHO)
    for s in subjects:
        stop.update(content_tokens(s["name"]))

    rows = [json.loads(l) for l in SAMPLES.read_text(encoding="utf-8").splitlines()]
    count: Counter[str] = Counter()
    spread: defaultdict[str, set] = defaultdict(set)
    for r in rows:
        toks = content_tokens(r["output"])
        sid = r["subject_id"]
        grams = [(toks[i], toks[i + 1]) for i in range(len(toks) - 1)]
        grams += [(toks[i], toks[i + 1], toks[i + 2]) for i in range(len(toks) - 2)]
        for g in grams:
            if set(g) & stop:
                continue
            k = " ".join(g)
            count[k] += 1
            spread[k].add(sid)

    cands = [
        (k, count[k], len(spread[k]), base.get(k, 0))
        for k in count
        if count[k] >= MIN_COUNT and base.get(k, 0) < MAX_BASELINE
    ]
    # sortiere: Spread zuerst (cross-cutting = echter Slop), dann Häufigkeit
    cands.sort(key=lambda x: (-x[2], -x[1]))

    def suggest(spread_n: int) -> str:
        if spread_n >= 5:
            return "slop?"
        if spread_n <= 2:
            return "strike"
        return "review"

    with OUT.open("w", encoding="utf-8") as fh:
        fh.write("keep\tngram\tcount\tbranchen\tbaseline\n")
        for k, c, ns, bf in cands:
            fh.write(f"{suggest(ns)}\t{k}\t{c}\t{ns}\t{bf}\n")

    n_slop = sum(1 for _, _, ns, _ in cands if ns >= 5)
    n_strike = sum(1 for _, _, ns, _ in cands if ns <= 2)
    log.info(
        "%d Kandidaten -> %s  (vor-markiert: %d slop?, %d strike, %d review)",
        len(cands), OUT, n_slop, n_strike, len(cands) - n_slop - n_strike,
    )
    print(f"\nTop cross-cutting Slop-Kandidaten (>=5 Branchen):")
    print(f"  {'n-gram':<34}{'count':>6}{'branchen':>9}{'baseline':>10}")
    for k, c, ns, bf in [c for c in cands if c[2] >= 5][:30]:
        print(f"  {k:<34}{c:>6}{ns:>9}{bf:>10}")


if __name__ == "__main__":
    main()
