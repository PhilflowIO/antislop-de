"""Schritt-2 Smoke: gemma-Website-Copy generieren (DeepInfra) + Slop messen.

Generiert über die DeepInfra-OpenAI-API deutsche Website-Copy auf den
Smoke-Prompts (scripts.build_prompts) und prüft zwei Dinge, bevor wir Geld in
den vollen Lauf stecken:

  1. Seed-Floskel-Scan — wie oft produziert gemma die bekannten DE-Slop-Phrasen
     (configs/de_extra_bans.json + eval/slop_candidates.json)?
  2. Emergent-Check (das echte Verfahren in klein) — gemmas häufigste
     Content-n-grams gegen die Human-Baseline: was bei gemma oft kommt, aber in
     der Baseline fehlt (freq 0), ist Emergent-Slop-Kandidat.

Augenschein-Frage: ist das geflaggte echter Marketing-Slop — oder nur normale
Copy-Struktur, die der dialogischen Baseline fehlt (= Register-Mismatch-Risiko)?

    DEEPINFRA_TOKEN=... uv run python scripts/generate_samples.py --n 20

Token NUR aus der Env (DEEPINFRA_TOKEN) — nie ins Repo.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from baseline import content_tokens  # noqa: E402
from build_prompts import build_grid, stratified_smoke  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("generate_samples")

API_URL = "https://api.deepinfra.com/v1/openai/chat/completions"
PROFILE = ROOT / "data" / "baseline" / "human_writing_profile_de.json"

# Ohne System-Prompt stellt gemma jeder Antwort eine Vorrede voran ("Absolut!
# Hier ist ein Entwurf …") + Meta-Kommentar ("Warum es funktioniert") — das ist
# Boilerplate, das das Slop-Profil verseucht (vgl. Untertitel-Credits in Stufe 0).
# Wurzel-Fix: nur den fertigen Text verlangen.
SYSTEM_PROMPT = (
    "Du bist ein erfahrener deutscher Werbetexter. Gib ausschließlich den "
    "fertigen Website-Text aus — ohne Vorrede, ohne Begrüßung, ohne mehrere "
    "Optionen zur Auswahl, ohne Erklärungen oder Meta-Kommentare. Beginne direkt "
    "mit dem Text."
)


def call_gemma(prompt: str, token: str, model: str, max_tokens: int, temperature: float) -> str:
    req = urllib.request.Request(
        API_URL,
        data=json.dumps({
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        r = json.load(urllib.request.urlopen(req, timeout=120))
        return r["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        log.warning("HTTP %s: %s", e.code, e.read().decode()[:200])
        return ""


def load_seed_phrases() -> list[str]:
    bans = json.loads((ROOT / "configs" / "de_extra_bans.json").read_text(encoding="utf-8"))
    cands = json.loads((ROOT / "eval" / "slop_candidates.json").read_text(encoding="utf-8"))
    phrases = (
        bans.get("extra_slop_phrases_to_ban", [])
        + bans.get("extra_nominalstil_phrases_to_ban", [])
        + cands.get("slop_phrases", [])
    )
    return sorted(set(phrases))


def seed_scan(texts: list[str], phrases: list[str]) -> list[tuple[str, int]]:
    blob = " ".join(" ".join(t.lower().split()) for t in texts)
    hits = [(p, blob.count(p)) for p in phrases]
    return sorted((h for h in hits if h[1] > 0), key=lambda x: -x[1])


def emergent_ngrams(texts: list[str], stop_tokens: set[str], top: int = 25) -> list[tuple[str, int, int]]:
    """Häufigste Content-Bi/Trigramme bei gemma + ihre Baseline-Frequenz.

    stop_tokens (Subjekt-Eigennamen) raus, sonst dominieren Themenwörter wie
    'lingua online' / 'kanzlei vogt' den Diff und werden als Slop fehlgeflaggt —
    das ist kein Slop, sondern Subjekt-Vokabular (und auto-antislop würde es
    sonst bannen).
    """
    if not PROFILE.is_file():
        return []
    prof = json.loads(PROFILE.read_text(encoding="utf-8"))["human-authored"]
    base = {x["ngram"]: x["frequency"] for x in prof["top_bigrams"]}
    base.update({x["ngram"]: x["frequency"] for x in prof["top_trigrams"]})

    counts: Counter[str] = Counter()
    for t in texts:
        toks = content_tokens(t)
        for i in range(len(toks) - 1):
            ng = (toks[i], toks[i + 1])
            if not (set(ng) & stop_tokens):
                counts[" ".join(ng)] += 1
        for i in range(len(toks) - 2):
            ng = (toks[i], toks[i + 1], toks[i + 2])
            if not (set(ng) & stop_tokens):
                counts[" ".join(ng)] += 1
    rows = [(ng, c, base.get(ng, 0)) for ng, c in counts.most_common(top)]
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=20, help="Sample-Größe (stratifiziert), ignoriert bei --full")
    ap.add_argument("--full", action="store_true", help="ganzes Prompt-Set generieren (1380), nicht samplen")
    ap.add_argument("--top", type=int, default=25, help="Länge der emergenten Kandidatenliste")
    ap.add_argument("--model", default="google/gemma-3-12b-it")
    ap.add_argument("--max-tokens", type=int, default=512)
    ap.add_argument("--temperature", type=float, default=0.9)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--workers", type=int, default=5)
    args = ap.parse_args()

    token = os.environ.get("DEEPINFRA_TOKEN")
    if not token:
        sys.exit("DEEPINFRA_TOKEN nicht gesetzt (Env-Var).")

    import random
    subjects = json.loads((ROOT / "configs/copy_prompts/subjects_de.json").read_text(encoding="utf-8"))["subjects"]
    copy_cfg = json.loads((ROOT / "configs/copy_prompts/copy_types_de.json").read_text(encoding="utf-8"))
    grid = build_grid(subjects, copy_cfg)
    sample = grid if args.full else stratified_smoke(grid, args.n, random.Random(args.seed))
    log.info("Generiere %d Samples über %s (workers=%d) …", len(sample), args.model, args.workers)

    def gen(p: dict) -> dict:
        out = call_gemma(p["prompt"], token, args.model, args.max_tokens, args.temperature)
        return {**p, "output": out}

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        results = list(ex.map(gen, sample))

    out_path = ROOT / "data" / ("samples_full.jsonl" if args.full else "samples_smoke.jsonl")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        for r in results:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    log.info("Samples -> %s", out_path)

    texts = [r["output"] for r in results if r["output"].strip()]

    # Einzel-Samples nur bei kleinen Läufen ausgeben (sonst flutet's die Konsole).
    if len(results) <= 30:
        print("\n" + "=" * 78)
        print(f"GENERIERTE SAMPLES ({len(texts)}/{len(results)} erfolgreich)")
        print("=" * 78)
        for r in results:
            print(f"\n[{r['subject_id']} · {r['copy_type']} · {r['tone']}/{r['length']}]")
            print((r["output"].strip() or "(leer)")[:600])
    else:
        log.info("%d/%d Generierungen erfolgreich", len(texts), len(results))

    print("\n" + "=" * 78)
    print("1) SEED-FLOSKEL-SCAN — bekannte DE-Slop-Phrasen in gemmas Copy")
    print("=" * 78)
    seed_hits = seed_scan(texts, load_seed_phrases())
    if seed_hits:
        for ph, c in seed_hits:
            print(f"  {c:>4}×  {ph}")
    else:
        print("  (keine Seed-Floskel getroffen)")

    print("\n" + "=" * 78)
    print("2) EMERGENT-CHECK — gemmas häufigste n-grams vs. Baseline (freq 0 = Slop-Kandidat)")
    print("=" * 78)
    stop_tokens: set[str] = set()
    for s in subjects:
        stop_tokens.update(content_tokens(s["name"]))
    rows = emergent_ngrams(texts, stop_tokens, top=args.top)
    if rows:
        print(f"  {'n-gram':<34}{'gemma':>7}{'baseline':>11}  Flag")
        for ng, c, bf in rows:
            flag = "✓ SLOP-Kandidat (fehlt in Baseline)" if bf == 0 else ("~ selten" if bf < 1000 else "natürlich")
            print(f"  {ng:<34}{c:>7}{bf:>11,}  {flag}")
    else:
        print("  (Baseline-Profil fehlt lokal — übersprungen)")

    # Curatables Banlist-Artefakt für Phils Hand-Review (Paech-Disziplin).
    cand_path = ROOT / "data" / "banlist_candidates.tsv"
    with cand_path.open("w", encoding="utf-8") as fh:
        fh.write("keep\tngram\tgemma_count\tbaseline_freq\tquelle\n")
        for ph, c in seed_hits:
            fh.write(f"?\t{ph}\t{c}\t-\tseed\n")
        for ng, c, bf in rows:
            fh.write(f"?\t{ng}\t{c}\t{bf}\temergent\n")
    log.info("Banlist-Kandidaten (zum Hand-Review) -> %s", cand_path)


if __name__ == "__main__":
    main()
