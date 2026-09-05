"""Stufe-0 Baseline: deutsches Human-n-gram-Profil für auto-antislop.

Baut ein schema-kompatibles `human_writing_profile_de.json`:
    {"human-authored": {model_name, total_chars, top_bigrams, top_trigrams}}

Die n-gram-Extraktion ist 1:1 zu Paechs Generierungs-Seite
(core/analysis.py): normalise_keep_marks -> word_tokenize -> nur Letter/Mark
-> deutsche Stopwords + min_word_len 3 raus -> Bi/Trigramme über den
gefilterten Token-Strom je Dokument. Nur so ist der spätere Slop-Diff
(LLM-Generierung vs. Human-Baseline) apples-to-apples.

Register-Mischung (HANDOFF Default, dialogisch-dominant, pre-2022):
    40 % OpenSubtitles2018-DE (orgtre Frequenzliste, garantiert pre-LLM)
    25 % German Commons political (Reden + Plenarprotokolle)
    20 % German Commons cultural (Literatur)
    15 % German Commons web (Forum/Diskussion, perplexity-gefiltert)
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

# Xet-Streaming-Threads crashen beim Interpreter-Teardown (PyGILState_Release);
# klassisches HTTP-Streaming vermeidet das ohne Funktionsverlust.
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")

import nltk
from nltk.corpus import stopwords

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("baseline")

# --- NLTK-Ressourcen sicherstellen ---
for _res, _path in [("punkt", "tokenizers/punkt"),
                    ("punkt_tab", "tokenizers/punkt_tab"),
                    ("stopwords", "corpora/stopwords")]:
    try:
        nltk.data.find(_path)
    except LookupError:
        nltk.download(_res, quiet=True)

STOP_DE = set(stopwords.words("german"))
# URL-/Markup-Reste, die normalise_keep_marks zu Letter-Tokens macht (z.B. http://www -> "http www")
JUNK_TOKENS = {"http", "https", "www", "com", "org", "html", "php", "amp", "nbsp"}
# Wiki-Zeitstempel-Signaturen ("12. Mär 2015 (CET)" -> "mär cet") — Metadaten, kein Deutsch.
DATE_TOKENS = {"cet", "cest", "utc", "gmt", "jan", "feb", "mär", "mrz", "apr",
               "jun", "jul", "aug", "sep", "sept", "okt", "nov", "dez"}  # "mai" ist legitim, raus gelassen
# HTML/Wiki-Markup, das nach Tag-Strip noch als Letter-Token durchrutschen kann (Gutachter B).
MARKUP_TOKENS = {"span", "div", "style", "color", "href", "noinclude", "includeonly",
                 "colspan", "rowspan", "font", "src", "alt", "thumb", "px", "img"}
MAX_TOKEN_RUN = 3  # gegen Tabellen-Repetition ("gang gang gang..." aus Getriebe-Tabelle); Dialog-Triples (nein nein nein) bleiben
_HTML_TAG = re.compile(r"<[^>]+>")
# Synchron-/Dub-Calques aus englischen Filmen — KEIN natürliches Deutsch, nur
# stehengebliebene Übersetzungs-Artefakte (z.B. "Yes, sir" -> "ja, sir"). Gutachter B:
# `sir` allein = 71 Bigramme / 460k Freq im 40%-OpenSubtitles-Profil. Raus.
CALQUE_TOKENS = {"sir", "aye", "mister", "maam", "madam", "milady", "señor", "senor"}
# Parlaments-Bühnenanweisungen (keine Rede, sondern Protokoll-Regie): [Beifall bei der CDU] etc.
STAGE_TOKENS = {"beifall", "zuruf", "zurufe", "heiterkeit", "widerspruch",
                "zwischenruf", "zwischenrufe", "lachen", "unruhe"}
# Pre-1996-Rechtschreibung -> modern (sonst zementiert die Literatur-Säule Archaik als "natürlich")
ARCHAIC_MAP = {"daß": "dass", "muß": "muss", "müßte": "müsste", "müßten": "müssten",
               "läßt": "lässt", "gewiß": "gewiss", "faßt": "fasst", "schloß": "schloss",
               "paß": "pass", "biß": "biss", "haßt": "hasst", "wußte": "wusste",
               "seyn": "sein", "thun": "tun", "thut": "tut", "giebt": "gibt", "sey": "sei"}
DROP_TOKENS = JUNK_TOKENS | DATE_TOKENS | MARKUP_TOKENS | CALQUE_TOKENS | STAGE_TOKENS
MIN_WORD_LEN = 3  # = auto_antislop_config.yaml:min_word_len_for_analysis
_SPACES = re.compile(r"\s+")

# Untertitel-Boilerplate (Credits, Sub-Firmen, Plattform-Tags, URLs) — kein
# natürliches Deutsch, im Smoke als Trigramm-Müll aufgetaucht. Satz wird verworfen.
_SUBTITLE_NOISE = re.compile(
    r"untertitel|subtitle|\bsubs\b|sdi media|media group|board\.?user|"
    r"netflix|amazon|synchron|übersetzung von|korrektur|transcript|"
    r"www\.|https?:|\.com|\.de\b|\.org|opensubtitles|@",
    re.IGNORECASE,
)
# Plenarprotokoll-Sitzungs-Header (Boilerplate, kein Sprachregister) — Ursache statt Symptom.
_PLENARY_HEADER = re.compile(
    r"(deutscher\s+)?bundestag\b.{0,60}?wahlperiode.{0,80}?sitzung.{0,40}?"
    r"(bonn|berlin)?[\s,\.\d]*", re.IGNORECASE)

# --- German-Commons-Register: register -> [(config, split)] (split = source) ---
# pre-2022-sicher; youtubecommons bewusst raus (LLM-Risiko). expository NEU: das Sachtext-/
# Assistant-Register, gegen das KI-Slop fair gemessen werden muss (Gutachter A/C).
GC_REGISTERS = {
    "political":  [("political", "germanpoliticalspeeches"), ("political", "btplenarprotokolle")],
    "cultural":   [("cultural", "dibilit"), ("cultural", "blbooks"), ("cultural", "wikisource")],
    "web":        [("web", "wikidiscussions"), ("web", "onemillionposts")],
    "expository": [("web", "wikipedia"), ("scientific", "wikibooks"),
                   ("scientific", "wikiversity"), ("scientific", "openalex")],
}
# Register-Gewichte (Token-Budgets). Daten-geerdet (eval/structural_reference.json):
# lebendige Register dominieren (cultural/dibilit Nominal.1,05 = lebendigst + divers),
# expository schmal (Wikipedia Nomen/Verb 3,27 = Dröge-Verursacher → Doc-Falle), political
# = lebendig-formal (Register-Breite ohne Dröge-Tax). Mission: natürlich, nicht blechern.
GC_WEIGHTS = {"cultural": 32, "web": 23, "political": 18, "expository": 16}
OPENSUB_TARGET_PCT = 18  # statt 40 — OpenSubtitles dominiert sonst die Frequenz-Spitze
OPENSUB_SCALE_CAP = 4.0  # harte Obergrenze gegen die ×22-Aufblähung aus ~2350 Sätzen
# Perplexity-Band: LLM-Text klustert niedrig, OCR-Schrott hoch. UNKALIBRIERTE HEURISTIK
# (Provenienz des ppl-Felds ungeprüft, Bandgrenzen nicht empirisch gesetzt) — Gutachter B.
# Auf web + expository angewandt (Web-/Wiki-Register), Reden/Literatur sind zeitstabil.
PPL_MIN, PPL_MAX = 50.0, 1500.0


def normalise_keep_marks(text: str) -> str:
    """1:1 zu slop_forensics.utils._normalise_keep_marks, plus HTML-Tag-Strip vorab."""
    text = _HTML_TAG.sub(" ", text)  # <span style="color:red"> raus, bevor Attribute zu Tokens werden
    text = unicodedata.normalize("NFKC", text)
    buf = []
    for ch in text:
        buf.append(ch.lower() if unicodedata.category(ch)[0] in ("L", "M") else " ")
    return _SPACES.sub(" ", "".join(buf)).strip()


def content_tokens(text: str) -> list[str]:
    """Paech-treuer Token-Strom: normiert, letter-only, Stopwords + Junk/Calque/Archaik raus."""
    norm = normalise_keep_marks(text)
    out = []
    for t in nltk.word_tokenize(norm):  # consumer nutzt default (EN) -> nach Normierung identisch
        if not all(unicodedata.category(c)[0] in ("L", "M") for c in t):
            continue
        t = ARCHAIC_MAP.get(t, t)  # pre-1996-Schreibung modernisieren
        if t in STOP_DE or t in DROP_TOKENS or len(t) < MIN_WORD_LEN:
            continue
        # Tabellen-Repetition kappen: max MAX_TOKEN_RUN gleiche Tokens in Folge
        if len(out) >= MAX_TOKEN_RUN and all(out[-k] == t for k in range(1, MAX_TOKEN_RUN + 1)):
            continue
        out.append(t)
    return out


def add_ngrams(tokens: list[str], weight: int, bi: Counter, tri: Counter) -> None:
    for i in range(len(tokens) - 1):
        bi[(tokens[i], tokens[i + 1])] += weight
    for i in range(len(tokens) - 2):
        tri[(tokens[i], tokens[i + 1], tokens[i + 2])] += weight


# ---------------------------------------------------------------------------

def ingest_opensubtitles(path: Path, bi: Counter, tri: Counter, cap: int,
                         target_mass: float) -> tuple[int, int, int]:
    """OpenSubtitles-Sätze als Dialog-Anker.

    n-grams gewichtet nach Vorkommen (count, gekappt gegen Top-Floskel-Dominanz),
    danach skaliert Richtung target_mass — aber HART bei OPENSUB_SCALE_CAP gedeckelt,
    damit ~2350 Sätze nicht via ×22 die Frequenz-Spitze monopolisieren (Gutachter B).
    OpenSubtitles liefert Dialog-Abdeckung, nicht Frequenz-Dominanz. Calques (sir/aye)
    fallen bereits in content_tokens raus.
    """
    kept: list[tuple[list[str], int, int]] = []  # (tokens, weight, char_contrib)
    natural_mass = 0
    dropped = 0
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            sent, cnt = row["sentence"], int(row["count"])
            if _SUBTITLE_NOISE.search(sent):
                dropped += 1
                continue
            toks = content_tokens(sent)
            if len(toks) < 2:
                continue  # keine Bigramme nach Stopword-Removal -> überspringen
            w = min(cnt, cap)
            cc = len(sent) * w
            kept.append((toks, w, cc))
            natural_mass += cc
    scale = min((target_mass / natural_mass) if natural_mass else 1.0, OPENSUB_SCALE_CAP)
    chars = 0
    for toks, w, cc in kept:
        sw = max(1, round(w * scale))
        add_ngrams(toks, sw, bi, tri)
        chars += len(toks) and round(cc * scale)
    log.info("OpenSubtitles: %d Sätze (Boilerplate verworfen=%d), scale=%.3f, ~%d Zeichen",
             len(kept), dropped, scale, chars)
    return chars, len(kept), dropped


def ingest_gc_split(config: str, split: str, target_tokens: int,
                    bi: Counter, tri: Counter, ppl_filter: bool) -> tuple[int, int]:
    """Streamt eine German-Commons-Split bis target_tokens Content-Tokens erreicht."""
    from datasets import load_dataset
    ds = load_dataset("coral-nlp/german-commons", config, split=split, streaming=True)
    strip_header = (config == "political")
    tok_total = chars = docs = skipped_ppl = skipped_degenerate = 0
    for row in ds:
        if ppl_filter:
            ppl = row.get("perplexity")
            if ppl is not None and not (PPL_MIN <= ppl <= PPL_MAX):
                skipped_ppl += 1
                continue
        text = row.get("text") or ""
        if strip_header:
            text = _PLENARY_HEADER.sub(" ", text)  # Sitzungs-Header raus (Boilerplate-Ursache)
        toks = content_tokens(text)
        if len(toks) < 2:
            continue
        # Degenerierte Tabellen/Specs überspringen: ein Token dominiert (z.B. Getriebe-Tabelle
        # "gang km h gang km h..."). Normale Prosa hat kein Content-Token >8 % des Docs.
        if len(toks) >= 100 and Counter(toks).most_common(1)[0][1] / len(toks) > 0.08:
            skipped_degenerate += 1
            continue
        add_ngrams(toks, 1, bi, tri)
        tok_total += len(toks)
        chars += len(text)
        docs += 1
        if tok_total >= target_tokens:
            break
    log.info("GC %s/%s: %d docs, %d content-tokens, %d chars (ppl-skip=%d, degen-skip=%d)",
             config, split, docs, tok_total, chars, skipped_ppl, skipped_degenerate)
    return chars, tok_total


# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--opensub", default="data/raw/de_top_sentences.csv")
    ap.add_argument("--opensub-cap", type=int, default=1000,
                    help="Max Gewicht je OpenSubtitles-Satz (dämpft Top-Floskeln)")
    ap.add_argument("--gc-tokens", type=int, default=55_000_000,
                    help="Content-Token-Budget gesamt über alle GC-Register")
    ap.add_argument("--top-k", type=int, default=500_000,
                    help="Top-N Bi/Trigramme im Profil (Paech: 500k)")
    ap.add_argument("--out", default="data/baseline/human_writing_profile_de.json")
    ap.add_argument("--report", default="data/baseline/baseline_report.json")
    ap.add_argument("--smoke", action="store_true", help="Mini-Lauf: 300k tok/config")
    args = ap.parse_args()

    bi: Counter = Counter()
    tri: Counter = Counter()
    report: dict = {"register_chars": {}, "register_tokens": {}}

    # 1) German Commons register-gewichtet (zuerst, um die GC-Masse zu kennen)
    wsum = sum(GC_WEIGHTS.values())
    gc_budget = 300_000 * 4 if args.smoke else args.gc_tokens
    ppl_registers = {"web", "expository"}
    gc_chars_total = 0
    for register, sources in GC_REGISTERS.items():
        reg_budget = int(gc_budget * GC_WEIGHTS[register] / wsum)
        per_split = max(1, reg_budget // len(sources))
        reg_chars = reg_tok = 0
        for config, split in sources:
            try:
                c, t = ingest_gc_split(config, split, per_split, bi, tri,
                                       ppl_filter=(register in ppl_registers))
                reg_chars += c
                reg_tok += t
            except Exception as e:  # noqa: BLE001
                log.error("GC %s/%s fehlgeschlagen: %s", config, split, e)
        report["register_chars"][register] = reg_chars
        report["register_tokens"][register] = reg_tok
        gc_chars_total += reg_chars

    # 2) OpenSubtitles (Dialog-Abdeckung) auf OPENSUB_TARGET_PCT skaliert, scale-gedeckelt
    target_os_mass = gc_chars_total * OPENSUB_TARGET_PCT / (100 - OPENSUB_TARGET_PCT)
    os_chars, os_rows, os_dropped = ingest_opensubtitles(
        Path(args.opensub), bi, tri, args.opensub_cap, target_os_mass)
    report["register_chars"]["opensubtitles"] = os_chars
    report["opensubtitles_sentences"] = os_rows
    report["opensubtitles_boilerplate_dropped"] = os_dropped
    total_chars = gc_chars_total + os_chars

    # 3) Profil schreiben (schema-kompatibel)
    def topk(counter: Counter, k: int) -> list[dict]:
        return [{"ngram": " ".join(ng), "frequency": int(c)}
                for ng, c in counter.most_common(k)]

    profile = {"human-authored": {
        "model_name": "human-authored-de",
        "total_chars": int(total_chars),
        "top_bigrams": topk(bi, args.top_k),
        "top_trigrams": topk(tri, args.top_k),
    }}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(profile, ensure_ascii=False), encoding="utf-8")

    report.update({
        "total_chars": int(total_chars),
        "unique_bigrams": len(bi),
        "unique_trigrams": len(tri),
        "register_char_pct": {k: round(100 * v / total_chars, 1)
                              for k, v in report["register_chars"].items()},
    })
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
    log.info("Profil: %s (%d bi / %d tri unique, %.1fM chars)",
             out, len(bi), len(tri), total_chars / 1e6)
    log.info("Register-Anteil (chars): %s", report["register_char_pct"])


if __name__ == "__main__":
    sys.exit(main())
