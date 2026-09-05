# Handoff: Stufe 3 — Voller FTPO-Lauf & Eval

**Erstellt:** 2026-06-08 (Ende Bau-Session 3) · **Selbsttragend** — du brauchst die vorige Session nicht.
**Tiefe bei Bedarf:** `JOURNEY.md` (Session 3 = der ganze Weg zum grünen Smoke), `project-status`-Memory,
`research/anti-slop-modal-trainingsplan-2026-06.md` (FTPO-Hyperparameter, GPU-Preise).

---

## Mission (unverändert)

Ein `gemma-3-12b-it`-LoRA, das **natürliches deutsches Schreiben** liefert statt blechern — Root-Cause via
**FTPO** (Sam Paech, `auto-antislop`), Use-Case **deutsche Website-Copy**. Es gibt keinen deutschen
Anti-Slop-Fork da draußen; wir bauen ihn.

## Was steht (alles in `main`, sauber, verifiziert grün)

Der **komplette FTPO-Pfad lief end-to-end auf Modal-H100** (Smoke, 20 Prompts). Das ist der
De-Risking-Beweis — jetzt fehlt nur noch das Hochskalieren auf den vollen Lauf.

- `vendor/auto-antislop/` — DE-gepatchter, eingefrorener auto-antislop (Patches in `vendor/PATCHES-DE.md`).
- `configs/de_extra_bans.json` — 116 kuratierte DE-Slop-Ngrams + 38 Surface-Seeds.
- `modal_app.py` — GPU-Image (CUDA-12.6-devel, **gepinnt:** torch 2.8 / vllm 0.11.0 / transformers 4.56.2 /
  flash-attn 2.8.3-Prebuilt-Wheel / trl 0.29.1 mit cross-version-Patches) + `run_pipeline` + `smoke`-Entrypoint.
- Grüner Smoke-Run im Volume: `antislop-de-vol/auto_antislop_runs/run_20260608_002001/` — Trainings-Evidenz
  `chosen_win` 0,12→0,54, `pref_loss` 7,43→3,23; `merged_16bit/` (5 fp16-Shards) + `lora_adapters/`.

**Voraussetzungen (Phil-seitig):** Modal authentifiziert (`modal token new` falls „Token not found"),
Secret `huggingface` (HF_TOKEN, gemma gated-Lizenz akzeptiert), Volume `antislop-de-vol` (gemma-Download
schon gecacht → der teure 24-GB-Pull entfällt beim vollen Lauf).

---

## Dein nächster Schritt: der volle Lauf

**Ein** Lauf, **ein** Treiber (Lehre aus Session 3: mehrere parallele Läufe = Log-Chaos). Aus dem Worktree
oder dem Haupt-Checkout, über `uv run`:

```bash
uv run modal run modal_app.py::smoke --max-prompts 1380
```

- `--max-prompts 1380` cappt die Generierung auf das volle Prompt-Set hoch (Smoke nutzte 20). Erst damit
  ist die **emergente** Banlist branchen-breit statt Dachdecker-lastig (bei 20 Prompts ist die n-gram-
  Statistik Müll, siehe JOURNEY Phase 18).
- `num_iterations` bleibt 2 (Config-Default, reicht laut auto-antislop für den meisten Slop).

### ⚠️ Trainings-Menge: ein Mechanik-Wart

`run_pipeline` reicht `--generation-max-prompts` an `main.py` durch, aber der `max_train_examples`-Parameter
des `smoke`-Entrypoints ist **noch nicht** in die main.py-CLI verdrahtet (vestigial). Die Zahl der
FTPO-Trainingsbeispiele steuert daher **`finetune_max_train_examples` im Config**
(`vendor/auto-antislop/auto_antislop_config.yaml:409`, aktuell `1000`). Für den vollen Lauf laut
Trainingsplan auf **8000–12000** hochsetzen — ein eigener kleiner Commit, bevor du zündest. (Saubere
Alternative: `--finetune-max-train-examples` als CLI-Override in `run_pipeline` ergänzen und durchreichen —
2-Zeilen-Fix in `modal_app.py`, dann ist der Parameter wieder ehrlich.)

### FTPO-Hyperparameter (stehen schon auf Soll, nicht neu aufrollen)

`finetune_mode: ftpo`, `finetune_lora_r: 128`, `finetune_beta: 0.1`, `ftpo_lambda_mse: 0.4`
(Config; Quelle `research/anti-slop-modal-trainingsplan-2026-06.md`).

### Kosten/Zeit

H100 ~3,95 $/h. Smoke (20 Prompts, 2 Iter): vLLM-Start ~3,5 min + Pipeline ~6,5 min ≈ 10 min GPU. Voll
skaliert v.a. die Generierung (Iter-1-Backtracking ist der Treiber) → grob **12–32 $**, Timeout steht auf 8h.
Der CPU-Merge des 12B-Modells dauert mehrere Minuten und ist RAM-intensiv (H100-Container reicht).

---

## Was bewusst NICHT neu aufrollen

- **Die Image-Pins.** torch 2.8 / vllm 0.11.0 / transformers 4.56.2 / flash-attn 2.8.3-Wheel / trl 0.29.1
  sind ein mühsam erkämpftes kohärentes Tripel (8 Versions-Drifts gefixt, siehe JOURNEY Phase 16-17). Nicht
  „aktualisieren". trl-Downgrade ist KEINE Option (verlangt transformers <4.50 → sprengt vLLM).
- **Die Architektur-Entscheidungen:** Vendoren statt Fork, CUDA-devel-Basis, eine End-to-End-Function (kein
  Zwei-Image-Split — wurde erwogen, war unnötig).

## Abnahme / Eval-Leiter (nach dem vollen Lauf)

Holdout-Stichprobe (200–500 DE-Outputs), Baseline-`gemma-3-12b-it` **vs.** das FTPO-Modell, vorher/nachher:
- **DE-Slop-Score** — die emergente Banlist + `eval/check_candidates.py` gegen die Holdout-Outputs.
- **Lexikalische Diversität** — TTR/RTTR (die Pipeline rechnet das schon pro Iteration; auf Holdout wiederholen).
- **Struktureller Slop** — `eval/structural_slop.py` (spaCy: Nominalisierungsrate, Nomen/Verb, Satzlänge,
  Passiv). n-grams fangen Phrasen, nicht Satzstruktur — das ist die offene Lücke aus Stufe 0.
- **Capability-Spotcheck** — GSM8K/MMLU-Stichprobe Baseline vs. FTPO (FTPO soll Slop entfernen ohne
  Capability-Verlust — das ist der ganze Punkt gegenüber DPO).
- **Pangram** (DE-validiert, ~0,05 $/Scan) — „AI-Wahrscheinlichkeit" vorher/nachher, ~10–25 $/Durchlauf.
  **Nur Schluss-Kontrolle, nie Trainings-Loss.**
- **Phils Augenschein** — der schlägt den Score (zweimal in Stufe 0 bewiesen). Inklusive **echter
  Raven-Copy** (Brief in `configs/copy_prompts/subjects_de.json`, `profiling:false`).

## HF-Upload (nach grüner Eval)

`merged_16bit/` aus dem Run-Verzeichnis → **privat** nach `PhilflowIO/gemma-3-12b-it-antislop-de`
(Token aus dem Modal-Secret). **Nur Gewichte + config + README** — Prompts/generierte Texte NICHT
enthalten (kein Business-Leak). Public + Gemma-Pflichten („Built with Gemma", Terms beilegen) erst nach
bewusster Entscheidung.

## Gotchas / Lehren (Session 3, damit sie nicht wiederkehren)

- **`returncode 0` lügt:** `main.py` schluckt Finetune-Exceptions und exitet 0. Echter Beleg = ein
  gespeicherter Adapter/Merge im Volume (`modal volume ls antislop-de-vol /auto_antislop_runs/<run>/...`),
  NICHT der Exit-Code.
- **Ein Lauf, ein Treiber.** Parallele Smokes aus mehreren Sessions auf einem Branch verseuchen die Logs
  (ein `EXIT=0` aus einem fremden Lauf täuschte kurz Erfolg vor) und konkurrieren um denselben Build.
- **Smoke-first bleibt Pflicht.** Jeder der 8 Versions-Blocker zeigte sich erst zur Laufzeit.
- **Modal-Token** kann serverseitig ablaufen → `modal token new`. HF-Token im Secret `huggingface`.
- **Git:** Issue → Branch → PR → Merge (`merge`, no-ff) → Cleanup (CLAUDE.md §7). Forgejo via
  `mcp__forgejo_mcp__*`, Repo `Phil/antislop-de`.

## Erste Aktion in der neuen Session

`JOURNEY.md` Session 3 + dieses File lesen (3 Min). Dann: `finetune_max_train_examples` hochsetzen (oder den
CLI-Override einbauen), den vollen Lauf zünden, das Volume-Artefakt verifizieren, Eval-Leiter fahren. Bei
echten Register-/Qualitäts-Entscheidungen Phil fragen — sonst durchziehen.
