# Handoff: Stufe 2 — Banlist-Review & auto-antislop-DE-Fork

**Erstellt:** 2026-06-07 (Ende Bau-Session 2) · **Selbsttragend** — du brauchst die vorige Session nicht.
**Tiefe bei Bedarf:** `JOURNEY.md`, `HANDOFF-STUFE-1-MODAL.md` (Modal-Grundlagen), `docs/stufe-0-baseline.md`, `research/anti-slop-modal-trainingsplan-2026-06.md` (FTPO-Hyperparameter, GPU-Preise).

---

## Mission (unverändert)

Ein `gemma-3-12b-it`-LoRA, das **natürliches deutsches Schreiben** liefert statt blechern — Root-Cause via **FTPO** (Sam Paech, `auto-antislop`), nicht Humanizer. **Konkreter Use-Case (Phils Entscheidung): deutsche Website-Copy.** Es gibt **keinen** deutschen Anti-Slop-Fork da draußen — Paechs `auto-antislop` ist Englisch-only; wir bauen den deutschen. Das ist der Daseinszweck.

## Die Methode in einem Absatz (damit du sie hast)

Wir messen, **wie gemma schreibt**, gegen ein **Lineal** = die Stufe-0-Human-Baseline (n-gram-Profil von echtem deutschem Schreiben). Logik: *was gemma viel häufiger sagt als echte Menschen = Slop.* Ablauf: **Prompts** → gemma generiert dt. Copy → **n-gram-Diff** gegen Baseline → **Banlist** der Floskeln → **FTPO** baut Präferenzpaare (Slop-Token rejected, natürliche Alternative chosen) → LoRA verlernt den Slop. Pangram nur als Schluss-Kontrolle, nie als Trainings-Loss.

---

## Was steht (alles in `main`, sauber)

**Stufe 0 — Baseline ✓** (`data/baseline/human_writing_profile_de.json`, gitignored, ~51 MB, reproduzierbar via `scripts/baseline.py`). Das ist das Lineal.

**Stufe 1 — Modal-Infra ✓** (Issue #4). `modal_app.py` `preflight` grün: HF-Token, gated-gemma-Zugang, Volume. Angelegt: Modal-Volume `antislop-de-vol`, Secret `huggingface` (HF_TOKEN), gemma-Lizenz akzeptiert. Abnahme: `modal run modal_app.py`.

**Schritt 2 — Prompt-Pipeline + Banlist-Kandidaten ✓** (Issue #7, PRs #8–#11):
- `configs/copy_prompts/subjects_de.json` — 15 Branchen-Briefs + Raven (`profiling:false`, nur fürs Eval).
- `configs/copy_prompts/copy_types_de.json` — 12 Copy-Typen × 4 Töne × 2 Längen.
- `scripts/build_prompts.py` — Grid → `data/prompts_de.jsonl` (1380 Prompts, gitignored).
- `scripts/generate_samples.py` — generiert über **DeepInfra-gemma** (`--full` / `--n` / `--top`); Token aus Env `DEEPINFRA_TOKEN`. System-Prompt erzwingt nur-Text (killt Vorrede-Boilerplate).
- `scripts/build_banlist.py` — liest `data/samples_full.jsonl`, rankt Kandidaten nach **Branchen-Spread**, schreibt `data/banlist_candidates.tsv` (vor-markiert: `slop?`/`strike`/`review`).
- Voller Lauf gemacht: 1380 Generierungen → 371 Kandidaten (93 slop? / 250 strike / 28 review).

## Entscheidungen — stehen, nicht neu aufrollen

| Was | Entscheidung |
|---|---|
| Use-Case | deutsche Website-Copy (Raven = Anwendungsfall, nicht Profiling-Treibstoff) |
| Generierung | DeepInfra-API (`google/gemma-3-12b-it`), günstig; Token = Phils, nur Env |
| Slop-Diskriminator | **Branchen-Spread** (viele Branchen = Floskel, eine = Fachbegriff), nicht „fehlt in Baseline" |
| Banlist | wird **hand-kuratiert** (Paech-Disziplin), nie blind auf der Rohliste trainiert |
| Modell-Name | `PhilflowIO/gemma-3-12b-it-antislop-de`, **vorerst privat** |
| Modell-Upload | nur Gewichte+config+README — Prompts/Texte NICHT enthalten, kein Business-Leak |

---

## Dein nächster Schritt (Phil, ~5 Min)

`data/banlist_candidates.tsv` öffnen, Spalte `keep` durchgehen:
- `slop?` (93) → die Beute, bestätigen (`legen größten wert`, `auf Bedürfnisse zugeschnitten`, `freuen darauf kennenzulernen`, `maßgeschneiderte lösungen`, `individuelle betreuung`, `rat tat seite`, `termin vereinbaren`).
- `strike` (250) → Fachbegriffe/Fakten, pauschal raus (`bio baumwolle`, `manuelle therapie`, `rhein main gebiet`).
- `review` (28) → echte Grenzfälle, dein Auge.

Die kuratierte Liste wird zu `configs/de_extra_bans.json` (bzw. dem auto-antislop-`extra_slop_phrases_to_ban`) hinzugefügt. **`configs/de_extra_bans.json` Hand-Review steht ohnehin noch aus** (Seed-Liste markiert `_review_status: SEED`).

## Nächster großer Block: auto-antislop-DE-Fork (eigenes Issue)

`auto-antislop` ist hart auf Englisch verdrahtet. Patch-Punkte (aus Stufe-1-Handoff, verifiziert):
- `auto_antislop_config.yaml:90` `generation_ngram_language: "english"` → `"german"`.
- `core/orchestration.py` ~Z.290: `stopwords.words('english')` → deutsche (NLTK-DE liegt vor).
- `slop_forensics/analysis.py` `analyze_word_rarity`: `wordfreq` Sprache → `de`.
- `human_profile_path` (`config:9`) → **unser** `human_writing_profile_de.json` (ins Modal-Volume hochladen).
- **Englische Banlist leeren**, unsere kuratierte DE-Banlist rein.
- `generation_hf_dataset_name` → unsere `data/prompts_de.jsonl` (15 Branchen, kein Raven).
- FTPO-Hyperparameter: `research/anti-slop-modal-trainingsplan-2026-06.md` (lora_r 128–256, ftpo_beta 0.1, lambda_mse 0.4).

**Generierungs-/Trainings-Route — offene Architektur-Entscheidung:**
- Generierung der FTPO-Paare braucht gemma via vLLM (Backtracking) → entweder **Modal-GPU** (der aufgeschobene Image-Stack, s.u.) oder DeepInfra.
- FTPO-Training braucht GPU → Modal H100. **GPU-Image-Stack ist offen** (`modal_app.py` Spec-Kommentar): `auto-antislop` zieht `flash-attn` (kompiliert gegen nvcc; `debian_slim` hat nur CUDA-Runtime), ungepinntes torch floatet auf 2.11+cu130 ohne flash-attn-Prebuilt-Wheel → CUDA-devel-Basis ODER gepinntes torch/vllm/flash-attn-Tripel.

Dann De-Risking-Leiter: Smoke → Kalibrierung (500) → Voll (2000). Messen vorher/nachher auf Holdout: DE-Slop-Score, lexikalische Diversität, struktureller Slop (`eval/structural_slop.py`), GSM8K/MMLU-Spotcheck, Pangram, Phils Augenschein (inkl. echter Raven-Copy).

## Gotchas / Lehren

- **Smoke-first zahlt sich aus** — fing diese Session: Vorrede-Boilerplate, Eigennamen-Flut, Themenwort-Fehlflags. Jede Quelle/Generierung schleppt Boilerplate ein, sichtbar erst im Output.
- **Register-Mismatch:** die Baseline ist dialogisch/literarisch, kennt kein Marketing-Register → korrekte Fachbegriffe sehen GENAU WIE Slop aus. Branchen-Spread trennt sie; Hand-Review ist das Netz.
- **Modal-Token** kann ablaufen („Token not found") → `modal token new` / `modal token set`. HF-Token im Secret `huggingface`. DeepInfra-Token = Phils, nur Env `DEEPINFRA_TOKEN`, nie ins Repo.
- **Git:** Issue → Branch → PR → Merge (`merge`, no-ff) → Cleanup (CLAUDE.md §7). Forgejo via `mcp__forgejo_mcp__*`, Repo `Phil/antislop-de`.

## Erste Aktion in der neuen Session

`README.md` + `JOURNEY.md` lesen (2 Min), dann: hat Phil `data/banlist_candidates.tsv` kuratiert? Wenn ja → Banlist in Config übernehmen + Issue für den auto-antislop-DE-Fork anlegen. Wenn nein → die 28 `review`-Grenzfälle für ihn vor-sortieren (Vorschlag keep/strike). Frag Phil nur bei echten Register-Entscheidungen.
