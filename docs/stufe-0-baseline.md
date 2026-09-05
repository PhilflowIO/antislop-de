# Stufe 0 — Deutsche Anti-Slop-Baseline (Abnahme-Dokument)

**Issue:** #1 · **Stand:** 2026-06-07 · **Status:** Redesign nach 3-Gutachter-Review, wartet auf Phils Augenschein-Abnahme.

Die Baseline definiert, was „natürlich deutsch" heißt — die kritische Grundlage, die Paech
für Deutsch nicht löst. Sie ersetzt sein englisches Fiction-Profil durch ein register-passendes,
pre-2022-deutsches Profil im exakt selben auto-antislop-Schema.

## Geschichte: warum dieses Profil ein Redesign ist

Die erste Baseline (40 % OpenSubtitles / dialogisch-dominant) wurde von **drei unabhängigen,
orthogonal geframten Gutachtern** (CLAUDE.md §9) einstimmig als fehlerhaft befunden (je `fail`,
confidence 86–88). Konvergenter Kerndefekt: **das Sachtext-Register fehlte komplett** und die
40 % OpenSubtitles waren statistisch nicht tragfähig (2350 Sätze ×22 skaliert → monopolisierten
97–99 % des Top-1000). Folge: neutrales Sachdeutsch (`ökonomische perspektive`) war von KI-Slop
(`ganzheitlicher ansatz`) ununterscheidbar — beide Frequenz 0. Entscheidung Phil: **Sachtext-fähig,
Baseline neu bauen.**

## Was gebaut wurde

`data/baseline/human_writing_profile_de.json` (gitignored) — schema-kompatibel zu auto-antislop
(`{"human-authored": {model_name, total_chars, top_bigrams, top_trigrams}}`, je 500k n-grams).

| Kennzahl | Wert |
|---|---|
| Gesamt-Zeichen | ~860 M |
| Unique Bigramme / Trigramme | ~33 M / ~50 M |
| **Register-Anteil (final, daten-geerdet)** | **cultural 35,1 % · web 23,3 % · political 18,8 % · expository 16,0 % · OpenSubtitles 6,8 %** |

Die finale Gewichtung (`GC_WEIGHTS = {cultural 32, web 23, political 18, expository 16}`) ist
**strukturell begründet** (`eval/structural_reference.json`): lebendige Register dominieren, weil
`cultural/dibilit` mit Nominalisierungsrate 1,05 das lebendigste *und* diverseste Register ist;
expository wurde von 28 → 16 % geschnitten, weil Wikipedia (Nomen/Verb 3,27, Passiv 0,21) die
Baseline strukturell ins Behördlich-Dröge zieht (Doc-Falle). Sachtext-Konnektoren bleiben bei
16 % geschützt; der bewusste Preis sind seltenere akademische Kollokationen (expository-Controls 5/12).

## Register & Quellen (alle pre-2022-sicher, legal, ODC-BY/CC)

- **expository (28 %, NEU)** — German Commons `web/wikipedia` + `scientific/{wikibooks,wikiversity,openalex}`.
  Das Sachtext-/Assistant-Register, gegen das KI-Slop fair gemessen werden muss. War der fehlende
  Block, der den Gutachter-Befund ausgelöst hat.
- **cultural (23,6 %)** — `dibilit`, `blbooks`, `wikisource` (Literatur, Wortschatz-Breite).
- **web (21 %)** — `wikidiscussions`, `onemillionposts` (Forum-Dialog, perplexity-gebandet).
- **political (20,2 %)** — `germanpoliticalspeeches`, `btplenarprotokolle` (gesprochen-rhetorisch).
- **OpenSubtitles2018 (7,2 %)** — `orgtre/top-open-subtitles-sentences` (Dialog-Anker, pre-LLM).
  Bewusst NICHT mehr 40 %: scale hart bei 4× gedeckelt → liefert Dialog-*Abdeckung*, nicht
  Frequenz-*Dominanz*. youtubecommons bleibt ausgeschlossen (post-2022-LLM-Risiko).

## Adressierte Gutachter-Funde (Redesign-Changelog)

| Fund (Gutachter) | Fix |
|---|---|
| Sachtext-Register fehlt → Slop ununterscheidbar von Sachdeutsch (A, C) | `expository`-Register (28 %); Konnektoren jetzt präsent (`darüber hinaus` 123→6369, `somit` ~0→3882, `insbesondere`→5599, `zudem`→2763) |
| OpenSubtitles 40 % = 2350 Sätze ×22, monopolisiert Top (B) | Ziel 18 %, scale-Cap 4× → real 7,2 %; opensub-cap 5000→1000; Top nicht mehr dialog-monopolisiert |
| Synchron-Calques (`sir` 71 Bigramme/460k, `aye`) (B) | `CALQUE_TOKENS`-Filter → `sir`-Bigramme jetzt 0 |
| Parlaments-Sitzungs-Header im Top (`bundestag wahlperiode sitzung`) (B) | `_PLENARY_HEADER`-Regex-Strip (Ursache) statt Gewichts-Dämpfung (Symptom); Beifall/Zuruf-Regie raus |
| Archaik (`muß/seyn/thun`) zementiert (B) | `ARCHAIC_MAP` modernisiert pre-1996-Schreibung |
| Abnahme-Harness ohne Sachtext-Negativ-Kontrolle (A) | `expository_controls` in `eval/slop_candidates.json` ergänzt |
| ppl-Band als „Proxy" verkauft, unkalibriert (B) | im Code/Doc als **unkalibrierte Heuristik** deklariert |
| (neu im Redesign entdeckt) Wiki-Zeitstempel `jan cet`/`mär cet` im Top | `DATE_TOKENS`-Filter |

## Akzeptanz-Beleg (`uv run python eval/check_candidates.py`)

- **KI-Floskeln near-zero:** `ganzheitlicher ansatz` 0 · `nahtlose integration` 0 · `wertvolle einblicke` 0 ·
  `facettenreiche welt` 0 · `wahres meisterwerk` 0 · `pulsierende metropole` 0.
- **Alltagssprache präsent:** `tut leid` 61.927 · `mach schon` 15.280 · `gute idee` 13.286 — Controls 5/5 ✓.
- **Sachtext-Konnektoren jetzt geschützt:** `darüber hinaus` 6369 · `hierbei handelt` 267 · `grundsätzlich gilt` 82.

## Re-Verifikation: dieselben 3 Gutachter, alle `fail → pass`

Nach dem Redesign wurden die drei Gutachter (Kontext intakt) zur Gegenprüfung re-aktiviert
(§9 adversarial-verify). Alle drei haben ihren ursprünglichen `fail` zurückgezogen:

| Gutachter (Frame) | vorher | nachher | Kern |
|---|---|---|---|
| A (Register-Match) | fail 88 | **pass 84** | Sachtext-Register verankert, Konnektoren geschützt; Rest = harmloser Kollokations-Long-Tail |
| B (Datenqualität) | fail 88 | **pass 84** | alle 4 harten Funde root-cause-behoben (OS-Monopol 787k→62k, sir=0, Header weg, Archaik weg) |
| C (Downstream FP/FN) | fail 86 | **pass-with-residual 78** | systemische FP-Klasse weg; Rest nur bei gemma-Überproduktion (nodict-Top-N + soft-banning, aus ANTISLOP-Paper belegt) |

B fand dabei zwei neue Artefakte derselben Boilerplate-Klasse → ebenfalls gefixt:
**HTML-Markup** (`span style color` aus Wiki-Rohtext) via `_HTML_TAG`-Strip + `MARKUP_TOKENS`;
**Tabellen-Repetition** (`gang gang` aus wikibooks-Getriebetabelle) via `MAX_TOKEN_RUN`-Cap +
Single-Token-Dominanz-Guard (skip Docs wo ein Token >8 %). `gang gang` von Rang 9 → Rang 78.

## Dokumentiertes Restrisiko

- **Spezifische akademische Kollokationen** (`systematische analyse`, `historischer kontext`,
  `ökonomische perspektive`) bleiben als exakte Content-Bigramme bei 0 — ihre Anker-Wörter sind
  präsent (`systematische` 124, `historischer` 365, `ökonomische` 605), aber die exakte Adjazenz
  ist im variantenreichen Menschtext selten. Konsequenz mild: ein f_human=0-Bigramm wird nur
  gebannt, wenn gemma es *über*produziert (nodict-Bucket nach gemma-Frequenz) — normale Nutzung
  bleibt unter der Ban-Schwelle.
- **Funktionswort-Floskeln** (`lassen sie uns`, `in diesem sinne`) kollabieren nach Stopword-Removal
  zu einem Token → laufen über den Slop-PHRASE-Pfad, nicht den n-gram-Pfad. Methoden-Eigenschaft.
- **kein harter LLM-Filter** in German Commons → pre-2022 via Split-Whitelist + ppl-Band (unkalibriert) approximiert.
- **Rest-Artefakt** `gang gang` (jetzt Rang ~78, wikibooks-Getriebetabelle) — stark reduziert, harmlos,
  da gemma es nicht produziert. Threshold-Senkung würde legit fokussierte Fachprosa treffen → bewusst belassen.

## Reproduktion

```bash
uv run python scripts/baseline.py --gc-tokens 55000000 \
  --out data/baseline/human_writing_profile_de.json \
  --report data/baseline/baseline_report.json
uv run python eval/check_candidates.py
```

## Register-Stellschrauben (`scripts/baseline.py`)

`GC_WEIGHTS` (expository/cultural/web/political) + `OPENSUB_TARGET_PCT`/`OPENSUB_SCALE_CAP`.
Mehr Sachtext → expository hoch; mehr Dialog → scale-Cap hoch (Vorsicht: Inflations-Risiko).
