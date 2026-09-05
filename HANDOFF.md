# Handoff: Deutsches Anti-Slop-FTPO-LoRA — Bau-Phase

**Erstellt:** 2026-06-07 · **Status:** Recherche + Entscheidungen abgeschlossen, bereit für Implementierung.
**Dieser Brief ist selbsttragend** — du brauchst die vorige Session nicht.

---

## Mission

Ein eigenes LLM bauen, das **natürlich deutsch schreibt** statt blechern/generisch — als **Root-Cause-Fix**, nicht als nachträglicher Humanizer. Ursache belegt: Instruction-Tuning/RLHF glättet Natürlichkeit weg (Base-Modelle werden zu 96–99 % als menschlich erkannt, Instruct-Versionen nur 17–30 %). Lösung: das Modell selbst per **FTPO** entblechern. Rewrites/Humanizer sind explizit NUR Symptom-Pflaster.

---

## Finale Entscheidungen (stehen, nicht neu aufrollen)

| Was | Entscheidung | Warum |
|---|---|---|
| **Base-Modell** | `google/gemma-3-12b-it` | Einziges ~12B-Dense-Instruct mit **existierender FTPO-Referenz** `sam-paech/gemma-3-12b-it-antislop`. Dense, 140+ Sprachen Pretrain. |
| **Methode** | **FTPO** via `sam-paech/auto-antislop` | 90 % Slop-Reduktion ohne Capability-Verlust. **NICHT DPO** (degradiert Diversität). |
| **Infra** | **Modal.com**, H100 | ~12–32 $/Lauf. vLLM-Generierung ggf. auf DeepInfra auslagern. |
| **Detektor-Messlatte** | **Pangram** (DE-validiert 99 %, ~$0,05/Scan) | **Schluss-Kontrolle, NICHT Trainings-Loss** (Goodhart-Falle). |
| **Baseline-Korpus** | DE-Mischung, dialogisch-dominant + pre-2022 (→ Stufe 0) | **Die Baseline definiert, was „natürlich" heißt.** Paech löst das nicht — wir schon. |
| **Persönlicher Stil** | **Phase 2** (später) | Erst DE-Anti-Slop-Basismodell; Stil per Few-Shot oder zweitem LoRA danach. |

**Verworfen (geprüft):** Gemma 4 12B (multimodal/Thinking-Template, keine antislop-Vorlage), Qwen 3.5/3.6 (existieren, aber kein ~12B-Dense, kein DE-Beleg, keine Vorlage). EuroLLM-9B (Apache) nur falls **freie Weiterverbreitung** des Merges nötig (Gemma 3 = Custom-Lizenz).

---

## ⭐ Stufe 0 (VORGEZOGEN, kritisch): Baseline bauen + abnehmen — BEVOR trainiert wird

Phils zentraler Einwand, jetzt belegt: ein schlechtes Referenzkorpus trainiert von einem künstlichen Klang in den nächsten. Paech adressiert **weder** Register-Mismatch **noch** KI-Kontamination **noch** Nicht-Englisch — sein Profil ist englische Fiction, für Deutsch wertlos. Das müssen wir selbst lösen. Quelle: `research/antislop-baseline-data-selection-2026-06.md`.

**Default-Baseline-Mischung (dialogisch-dominant, pre-2022, legal):**
- **40 %** OpenSubtitles2018-DE — via [`orgtre/top-open-subtitles-sentences`](https://github.com/orgtre/top-open-subtitles-sentences): `de_top_words.csv` (218 M Tokens) + `de_top_sentences.csv` (40 M Sätze), **fertige Frequenzliste = halbes n-gram-Profil frei Haus, garantiert pre-LLM.**
- **25 %** German Commons `political` (`germanpoliticalspeeches` + `btplenarprotokolle`) + VoxPopuli-DE (CC0) — gesprochen-rhetorisch.
- **20 %** German Commons `cultural` (`dibilit`/`blbooks`/`wikisource`) — literarische Wortschatz-Breite.
- **15 %** German Commons `web` **perplexity-gefiltert** (`wikidiscussions` + `onemillionposts`) — Forum-Dialog.

**German Commons** = `coral-nlp/german-commons` (HF, **ODC-BY**, 154,56 Mrd. Tokens, Parquet). Jede Zeile trägt `source` + KenLM-`perplexity` + `ocr_score` → register-/qualitätssauberes Sampling. **Vorbehalt:** kein pre-2022-Schnitt (Snapshots bis Aug 2025) → pre-LLM-Cut selbst via source-Whitelist + Perplexity-Band approximieren. (`bigscience/open_subtitles_monolingual` ist tot/401 — nicht nutzen.)

**Register-Stellschraube** (ein Parameter, keine neuen Quellen): literarischer → `cultural` auf 35–40 % hoch, OpenSubtitles runter. Default ist dialogisch (= Phils Ziel: natürlich/gesprochen, nicht blechern).

**Abnahme:** Baseline bauen, n-gram-Profil rechnen, dann **Phil liest 10–20 Beispiel-Slop-Phrasen** und urteilt „ja, das sind echte deutsche KI-Floskeln" — der menschliche Augenschein steht ÜBER dem Score (Phil detektiert Slop mit ~93 % Trefferquote). Erst wenn die Baseline sitzt, wird trainiert.

---

## Mess- & De-Risking-Strategie (statt blind den vollen Lauf zu fahren)

**De-Risking-Leiter** — jede Stufe mit Kill-Kriterium, du zahlst nie mehr, als die nächste Unsicherheit kostet:

| Stufe | Umfang | Kosten/Zeit | Danach weißt du |
|---|---|---|---|
| 1. Smoke | 50 Prompts, 200 Pairs | ~$1–2, 20 Min | Läuft die Pipeline end-to-end? |
| 2. Kalibrierung | 500 Prompts, echte Pairs | ~$5–10, 1–2 h | **Senkt FTPO den Slop messbar?** → Kosten-pro-Qualitätspunkt-Kurve |
| 3. Voll | 2000 Prompts, 8–12k Pairs | ~$12–32, 3–8 h | nur wenn Stufe 2 grün — das Produktivmodell |

**Metriken pro Lauf:** (a) DE-Slop-Score vorher/nachher auf Holdout (primär, eigene Liste), (b) lexikalische Diversität (Degradations-Gegenprobe — FTPO soll sie *halten*), (c) GSM8K/MMLU-Spotcheck (Capability-Schutz), (d) Pangram vorher/nachher (Detektor-Kontrolle), (e) **Phils Augenschein an 10 Beispielen** (letzte Instanz).

**Phase 1.5 — autoresearch (Karpathy-Loop), erst NACH dem ersten manuellen Lauf:**
[`karpathy/autoresearch`](https://github.com/karpathy/autoresearch) iteriert autonom über Hyperparameter (lora_r, ftpo_beta, lambda_mse, Banlist-Aggressivität, Datensatz-Mix). **Zwei harte Regeln:** (1) **zusammengesetzte, hack-resistente Metrik** — Slop↓ UND Diversität gehalten UND Capability stabil als *ein* Score, sonst hackt der Agent die Lücke (verstummtes Modell hat niedrigsten Slop). (2) **NICHT gegen Pangram optimieren** (Goodhart) — Pangram nur Schluss-Validierung der Gewinner-Konfig. Plus hartes Kosten-Budget (Modal-Stunden × Läufe).

---

## Referenz-Dokumente (alle absolut)

**Hauptplan (zuerst):** `/home/philflow/Dokumente/coding/research/anti-slop-modal-trainingsplan-2026-06.md` — Modell-Begründung, Modal-App-Skelett, GPU-Preise, Daten-Schritte a–f, **FTPO-Hyperparameter**, Mess-Setup.
**Baseline-Datenwahl (kritisch für Stufe 0):** `/home/philflow/Dokumente/coding/research/antislop-baseline-data-selection-2026-06.md` — Paech-Lücke + German Commons + OpenSubtitles-Quellen + Mischung.
Vertiefung: `anti-slop-huggingface-sota-2026-06.md`, `anti-slop-github-community-sota-2026-06.md`, `llm-natuerliches-texten-2026-06.md` (alle unter `…/research/`).
Blog-Post (Draft, Vault): `/home/philflow/Dokumente/obsidian-knowledge-vault/marketing/headlines-von-hand-gemini-haelt-sie-fuer-ki-blog.md` (vor Publish: „Llama-3-8B"-Claim gegen arXiv:2605.19516 prüfen).
Memory: `project_anti_slop_finetune.md`, `feedback_hf_research_raw_api.md`, `feedback_no_fake_contrasts.md`.

---

## Tooling-Regeln (aus Fehlern gelernt)
- **HF-Recherche → rohe API per curl** (`https://huggingface.co/api/models?author=…&search=…`), nicht der flaky `huggingface-search`-MCP. **HF gibt 401≠404** → Existenz nie per ID-Raten, immer Listen-API.
- **Forgejo-Ops** → `mcp__forgejo_mcp__*`, nie curl gegen forgejo.philflow.me.
- **Audit-Subagents:** Evidence-Required (`file:line` + Quote), Negativ-Aussagen belegen (CLAUDE.md §9).
- **Rechtliches:** kommerzielle Filme rippen/transkribieren ist NICHT legal (Urheberrecht + §95a Kopierschutz). Für gesprochenes DE die offen lizenzierten Korpora oben nutzen.

---

## Nächste Schritte (Bau-Phase, Reihenfolge)
0. **Baseline bauen + von Phil abnehmen lassen** (Stufe 0 oben) — orgtre-Frequenzlisten ziehen, German-Commons-Subsets sampeln, Profil rechnen, Augenschein.
1. **Modal-Setup** — Secret `huggingface`, Volume `antislop-de-vol`, `gemma-3-12b-it` gated-Lizenz akzeptieren.
2. **auto-antislop forken**, `modal_app.py` (2 Functions), Modal-SDK-Syntax gegen aktuelle Doku prüfen, **englische Banlist leeren**.
3. **De-Risking-Leiter** Stufe 1 → 2 → 3 fahren, an jeder Stufe Kill-Kriterium prüfen.
4. **Messen** (alle Metriken oben), dokumentieren.
5. Optional **Phase 1.5** autoresearch.

## Offene Risiken
- „FTPO senkt Pangram-Score" ungetestet (Oberflächen-Slop vs. tiefere Signaturen).
- German Commons pre-2022-Approximation muss sauber gesetzt sein.
- Modal-SDK-Syntax verifizieren. Lizenz-Entscheidung (Gemma vs. EuroLLM) nur falls Weiterverbreitung relevant.

## Erste Aktion in der neuen Session
Lies den Hauptplan + den Baseline-Report, dann **Stufe 0** (Baseline). Frag Phil nur, falls die Lizenz-Frage (Weiterverbreitung) den Modell-Default kippt — sonst `gemma-3-12b-it`.
