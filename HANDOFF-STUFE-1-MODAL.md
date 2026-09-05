# Handoff: Stufe 1 — Modal-Setup & erster FTPO-Lauf

**Erstellt:** 2026-06-07 (Ende Bau-Session 1) · **Dieser Brief ist selbsttragend** — du brauchst die vorige Session nicht.
**Tiefe bei Bedarf:** `JOURNEY.md` (kompletter Verlauf Stufe 0), `docs/stufe-0-baseline.md` (Abnahme), `HANDOFF.md` (Forschungs-Grundlagen), `research/anti-slop-modal-trainingsplan-2026-06.md` (Modal-Skelett, GPU-Preise, FTPO-Hyperparameter).

---

## Wo wir stehen

**Mission:** ein `gemma-3-12b-it`-LoRA, das **natürlich deutsch** schreibt statt blechern — Root-Cause via FTPO (Sam Paech, `auto-antislop`), nicht Humanizer.

**Stufe 0 (Baseline) ✓ fertig, gemerged (`main`, PR #2, Issue #1 closed).** Das menschliche DE-n-gram-Referenzprofil steht — die kritische Grundlage, die Paech für Deutsch nicht löst. 3 unabhängige Gutachter (orthogonale Frames, §9) haben es validiert: fail → pass. Phil hat abgenommen.

**Was das Profil ist:** `data/baseline/human_writing_profile_de.json` (gitignored, ~49 MB, reproduzierbar). Schema-kompatibel zu `auto-antislop` (`{"human-authored": {model_name, total_chars, top_bigrams, top_trigrams}}`, je 500k). n-gram-Extraktion ist **1:1** zu Paechs Generierungs-Seite (`normalise_keep_marks` → NLTK → deutsche Stopwords → min_word_len 3), damit der Slop-Diff apples-to-apples ist.

**Register (final, daten-geerdet):** cultural 35 / web 23 / political 19 / expository 16 / OpenSubtitles 7 — lebendig-dominant, expository bewusst schlank gegen die „Doc-Falle".

---

## Entscheidungen — stehen, nicht neu aufrollen

| Was | Entscheidung |
|---|---|
| Base-Modell | `google/gemma-3-12b-it` (gated) |
| Lizenz | **Gemma 3 bleibt** — freie Weiterverbreitung nicht nötig (geklärt) |
| Methode | **FTPO** (nicht DPO) via `sam-paech/auto-antislop` |
| Infra | Modal.com, H100 (~12–32 $/Lauf); vLLM-Generierung ggf. DeepInfra |
| Detektor-Messlatte | Pangram — **Schluss-Kontrolle, NICHT Trainings-Loss** (Goodhart) |
| Baseline | gebaut (s. o.), `reproduce: scripts/baseline.py --gc-tokens 55000000` |

---

## Stufe 1 — was zu tun ist (Reihenfolge)

### 1. Modal-Konto-Setup
- Secret `huggingface` (HF_TOKEN read+write) in Modal anlegen/prüfen.
- Volume `antislop-de-vol` (`create_if_missing`).
- `google/gemma-3-12b-it` gated-Lizenz auf HF akzeptieren (sonst 401 beim Download).

### 2. auto-antislop forken + auf Deutsch umstellen
`auto-antislop` ist **hart auf Englisch verdrahtet** — das ist der Kern-Umbau. Konkrete Patch-Punkte (in dieser Session verifiziert):
- `auto_antislop_config.yaml:90` `generation_ngram_language: "english"` → `"german"` (wird via `core/orchestration.py:147` als `--ngram-language` durchgereicht).
- `core/orchestration.py` ~Zeile 290: lädt `stopwords.words('english')` → **deutsche** Stopwords. NLTK-DE ist verfügbar (`punkt`, `punkt_tab`, `stopwords` werden in `scripts/baseline.py` schon gezogen).
- `slop-forensics` Wort-Rarity nutzt `wordfreq` — Sprache auf `de` setzen (sonst misst es DE-Wörter gegen EN-Frequenzen). Prüfen in `slop_forensics/analysis.py` `analyze_word_rarity`.
- `human_profile_path` (`auto_antislop_config.yaml:9`) auf **unser** Profil zeigen lassen: `data/baseline/human_writing_profile_de.json` (ins Modal-Volume hochladen).
- **Englische Banlist leeren:** das mitgelieferte englische Profil/Slop-Listen raus. Unsere Seed-Bans rein: `configs/de_extra_bans.json` → `extra_slop_phrases_to_ban` + `extra_nominalstil_phrases_to_ban` (Achtung: **Hand-Review ausstehend**, vor Produktiv-Lauf durchgehen — Paech-Disziplin).
- `generation_hf_dataset_name` (Config :52, aktuell `Nitral-AI/Reddit-SFW-Writing_Prompts_ShareGPT`) → **deutsche Prompts**. Themen breit: Erzählung, Essay, Dialog, Erklärung, E-Mail (sonst kippt das Slop-Profil auf eine Domäne). Quelle muss noch gewählt/gebaut werden — offener Punkt.
- **Modal-SDK-Syntax gegen aktuelle Doku verifizieren** (`@app.function`, `modal.Image`, `modal.Volume`, `modal.Secret`, `gpu=`, `timeout`, `vol.commit()`). Skelett in `research/anti-slop-modal-trainingsplan-2026-06.md` ist illustrativ, nicht verifiziert.

### 3. De-Risking-Leiter — nie blind skalieren
| Stufe | Umfang | Kosten | Kill-Kriterium |
|---|---|---|---|
| Smoke | 50 Prompts, 200 Pairs | ~$1–2 | Läuft die Pipeline end-to-end? |
| Kalibrierung | 500 Prompts | ~$5–10 | **Senkt FTPO den DE-Slop messbar?** |
| Voll | 2000 Prompts, 8–12k Pairs | ~$12–32 | nur wenn Kalibrierung grün |

FTPO-Hyperparameter: `research/anti-slop-modal-trainingsplan-2026-06.md` (lora_r 128–256, ftpo_beta 0.1, lambda_mse 0.4, …).

### 4. Messen (alle Metriken, vorher/nachher auf Holdout)
- **DE-Slop-Score** (primär, eigene Liste) — `eval/check_candidates.py` als Basis, gegen Holdout-Generierungen.
- **Lexikalische Diversität** (Degradations-Gegenprobe — FTPO soll sie *halten*).
- **Struktureller Slop-Score** — `eval/structural_slop.py` (gemma-vorher vs. -nachher vs. `eval/structural_reference.json`). **Wichtig:** deutscher Slop ist zur Hälfte strukturell (Nominalstil/Schachtelsatz); n-grams sehen das nicht. FTPO greift Struktur nur teilweise — diese Metrik macht sichtbar, *ob* das Modell strukturell entblecht. Wenn Struktur das dominante Signal ist → ggf. ergänzende Methode (Präferenz-Set entnominalisiert vs. nominal) als spätere Phase.
- **GSM8K/MMLU-Spotcheck** (Capability-Schutz).
- **Pangram** vorher/nachher (Detektor-Kontrolle, ~$0,05/Scan, DE-validiert) — Schluss-Validierung der Gewinner-Konfig, NICHT Trainings-Loss.
- **Phils Augenschein** an 10 Beispielen — letzte Instanz.

### 5. Merge + Export
LoRA in `gemma-3-12b-it` mergen, safetensors, optional GGUF, privater HF-Upload.

---

## Was diese Session gelernt hat (für Modal relevant)

- **Die Baseline IST die Definition von „natürlich"** (Paechs tiefster Punkt) — sie ist an unser gewünschtes Output-Register gekoppelt (lebendig, sachtext-fähig). Nicht durch ein dröges Register „korrigieren".
- **n-grams ≠ Struktur.** Der `eval/structural_slop.py`-Layer ist die Antwort auf die n-gram-Lücke — in der Mess-Phase ernst nehmen.
- **Smoke-first.** Jede Datenquelle schleppt Boilerplate ein. Bei der Generierung dasselbe erwarten und früh prüfen.
- **HF-Fakten via roher `curl`** (401≠404). **Forgejo via `mcp__forgejo_mcp__*`.** Git nach CLAUDE.md §7 (Issue→Branch→PR→Merge→Cleanup).
- **Audit-Subagents:** Evidence-Required (`file:line` + Quote), orthogonale Frames, read-only (§9). Hat hier einen echten Defekt gefunden, den grüne Zahlen verdeckten.

## Offene Risiken / Entscheidungen

- **Deutsche Profiling-Prompts** noch nicht gewählt/gebaut (Schritt 2) — bestimmt, welcher Slop überhaupt erfasst wird.
- **Seed-Banlist Hand-Review** ausstehend (`configs/de_extra_bans.json`).
- **„FTPO senkt Pangram-Score" ungetestet** (Oberflächen- vs. Tiefen-Signatur).
- **Struktureller Slop nur teilweise FTPO-greifbar** — Befund erst nach erstem Lauf bewertbar.
- **Modal-SDK-Syntax** unverifiziert.

## Erste Aktion in der neuen Session

`README.md` + `JOURNEY.md` lesen (holt dich in 2 Min ab), dann **Schritt 1** (Modal-Konto-Setup) — Issue anlegen, Branch `feat/modal-setup`, los. Frag Phil nur, wenn die Prompt-Quellen-Wahl (Schritt 2) eine echte Registerentscheidung erzwingt.
