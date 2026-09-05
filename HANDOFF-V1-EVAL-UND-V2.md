# Handoff: v1 voll evaluiert → Demo steht, v2 als nächstes

**Erstellt:** 2026-06-08 (Ende Eval-Session) · **Selbsttragend** — du brauchst die vorige Session nicht.
**Tiefe bei Bedarf:** `JOURNEY.md` (Session 3+4), `HANDOFF-STUFE-3-VOLLER-LAUF.md` (wie das Modell entstand),
`eval/`-Skripte, Memory `eval-verdict-and-v2-targets` + `project-status`.

---

## Mission (unverändert)

Ein `gemma-3-12b-it`-LoRA, das **natürliches deutsches Schreiben** liefert statt blechern — Root-Cause via
**FTPO** (Sam Paech, `auto-antislop`), Use-Case **deutsche Website-Copy** (Raven). Ziel ist eine
**wissenschaftlich belegte Side-by-side-Demo** (gemma vs. unser Modell, Slop sichtbar), iterativ gehärtet
bis die Beweise tragen.

## Was steht (alles in `main`, sauber, gemerged)

**v1-Modell fertig trainiert** (`run_20260608_061845`, Volume `antislop-de-vol`): voller FTPO-Lauf,
`chosen_win` 0,69→0,86, Artefakt `…/finetuned_model_ftpo_exp01/merged_16bit` (5 fp16-Shards) + `lora_adapters/`.

**Eval-Leiter komplett** (alle Rungs gemerged, PRs #28/#30/#32/#34/#36):
- `eval/run_holdout_eval.py` — struktureller Slop (spaCy, median, markdown-gestrippt) + TTR/RTTR/MATTR + Banlist-Treffer
- `eval/diversity.py` — TTR/RTTR/MATTR (MATTR längen-robust)
- `modal_app.py::capability_eval`/`capability_compare` — GSM8K/MMLU Baseline vs FTPO
- `modal_app.py::eval_generate`/`eval_compare` — Baseline-vs-FTPO-Generierung, `--temperature`, `--broad`, `--register`
- `scripts/build_eval_prompts.py` — Raven-Holdout-Prompts (`--broad` = ~36)
- `eval/build_demo.py` — **die Side-by-side-Demo** → `data/eval_demo.html` (gitignored, `uv run python eval/build_demo.py`),
  Slop markiert + Markdown gerendert + Metrik-Panel

### Ergebnis v1 (Raven-Holdout n=36, temp 0.7, du-gepinnt) — ehrlich gemischt

| Achse | Baseline | FTPO | |
|---|---|---|---|
| Phrasen-Slop /1k Tokens | 45,3 | **3,75** | ✓✓ −92 % |
| Capability GSM8K / MMLU | 87 / 68 | 86 / 68 | ✓ erhalten (FTPO-Kernbeweis) |
| Diversität MATTR | 0,87 | 0,89 | ✓ |
| Nominalisierung /100 | 3,1 | 2,4 | ✓ |
| Struktur-Slop-Score (Median) | 41 | 86 | ✗ schlechter |
| Passiv-Quote | 0,0 | 0,09 | ✗ |
| Degenerierte Run-ons | 0 | 3/36 (~8 %) | ✗ |

**Phils Verdikt (Augenschein = Goldstandard):** FTPO **klar „menschlicher", bevorzugt**. Der Struktur-Slop-Score
ist der **unzuverlässigste** Messwert (gegen Romane gemessen; nominal ≠ schlecht für Copy) — wo er Phils Auge
widerspricht, gewinnt das Auge. Echte Defekte, die er korrekt trifft: die Run-ons + Passiv/Listen-Struktur.

**Pangram = Sackgasse, gestrichen.** Key getestet (8 Scans), Konto hat Credits, API async (`POST /task`→`task_id`,
`GET /task/{id}`, `dashboard_link` zeigt Marking visuell). **Aber Pangram diskriminiert Baseline vs FTPO nicht** —
beide längeren Texte = „AI" (erwartbar: Pangram misst *KI-Herkunft*, nicht *Slop*). **Kein weiteres Pangram-Budget.**
Unser harter Beleg bleibt: Phrasen-Slop −92 % + Augenschein + Capability-Erhalt + das erklärbare Banlist-Marking.

---

## Dein nächster Schritt — v2 (Phils Go: „lass uns weitermachen")

Die offene Flanke ist **Struktur/Stil**, nicht Inhalt. Reihenfolge billig→teuer:

### 1. Billiger Inferenz-Fix gegen die Run-ons (~$2, ZUERST, evtl. kein Retraining nötig)
Die ~8 % degenerierten „inklusive…inklusive"-Run-ons sind teils ein Inferenz-Problem. Test:
`eval_generate` um `repetition_penalty` (≈1,15–1,3) + niedrigeren `max_new_tokens`-Cap erweitern, breiten
Lauf @ temp 0.7 wiederholen, `eval/run_holdout_eval.py` drauf → verschwinden die Run-ons / sinkt Passiv?
Wenn ja: v1 ist gut genug, nur Inferenz-Config dokumentieren.

### 2. v2-Training gegen die DREI Slop-Muster, die Phil beim Demo-Lesen fand
(Falls der Inferenz-Fix nicht reicht.) Die Banlist/Trainingssignal um diese erweitern:
- **Doppelpunkt-Einleitungen** raus: nicht „Unser Ansatz: Meetings vom Konzept zum Ergebnis" → direkt die Aussage.
  Auch „**Label:**"-Bullet-Struktur ist Slop.
- **Intensifier „wirklich/echt"** härter targeten („Deine Daten bleiben sicher, wirklich") — stand schon als
  keep=slop in der kuratierten Banlist, kommt trotzdem durch.
- **Run-on-Drehschleifen** (inklusive…inklusive).
Hebel: diese Muster als zusätzliche Ban-Regeln/FTPO-Paare; ggf. FTPO-Stärke justieren. **Aber §8-Disziplin**:
keine neue RAG-/Modell-Komponente ohne DE-Eignungsprüfung (gilt hier kaum, da reines Banlist-Tuning).

### 3. Wenn Demo überzeugt → Schluss (Pangram NICHT, Upload optional)
v1 (oder v2) als Phrasen-Slop-Modell akzeptieren. HF-Upload privat `PhilflowIO/gemma-3-12b-it-antislop-de`
(nur Gewichte+config+README, kein Business-Text) — erst nach Phils explizitem Go. Inferenz-temp **~0,7** als Default.

---

## Voraussetzungen (Phil-seitig)

Modal authentifiziert (`modal token new` falls abgelaufen), Secret `huggingface` (HF_TOKEN, gemma gated akzeptiert),
Volume `antislop-de-vol` (gemma + run_20260608_061845 gecacht). Inferenz/Eval brauchen **kein** lokales `data/`-Symlink
mehr (build_eval_prompts liest git-getrackte `configs/`, Modell liegt im Volume, GSM8K/MMLU zieht Modal selbst).

## Gotchas / Lehren (damit sie nicht wiederkehren)

- **`returncode 0` lügt** — echter Beleg = Artefakt im Volume (`modal volume ls`), nicht Exit-Code.
- **Kein `data`-Symlink in Worktrees + `git add -A`** — `.gitignore data/` fängt einen Symlink namens `data` NICHT
  (jetzt zusätzlich `/data` gepinnt). Hat einmal lokale Daten zerstört (Issue #24). Eval-Inputs in Worktrees **kopieren**.
- **Worktree-venv** hat das spaCy-Modell nur, weil `de_core_news_sm` jetzt echte Dependency ist (URL-Wheel in pyproject).
- **temp 1.0 = Trainings-temp, zu heiß für Inferenz** — Defaults ~0,7.
- **Struktur-Slop-Score ist der schwächste Messwert**; Phrasen-Slop + Augenschein + Capability sind die belastbaren.
- **Markdown-Demo**: Slop-Marking via alnum-Sentinels (Control-Chars werden vom markdown-Prozessor verschluckt).
- **Git:** Issue→Branch/Worktree→PR→Merge(`merge`,no-ff)→Cleanup (CLAUDE.md §7). Forgejo via `mcp__forgejo_mcp__*`, Repo `Phil/antislop-de`.

## Erste Aktion in der neuen Session

`JOURNEY.md` Session 4 + dieses File lesen (3 Min). Demo ansehen: `uv run python eval/build_demo.py` →
`data/eval_demo.html`. Dann Schritt 1 (Inferenz-Fix gegen Run-ons) bauen + testen. Bei Register-/Qualitäts-
Entscheidungen Phil fragen — sonst durchziehen.
