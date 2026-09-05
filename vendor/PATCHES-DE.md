# vendor/auto-antislop — DE-Patches

`sam-paech/auto-antislop` ist hart auf Englisch verdrahtet. Diese vendored Kopie
ist der **deutsche** Umbau (Issue #16). Vendored statt geforkt: ein eingefrorener,
reproduzierbarer Stand für die teuren Modal-GPU-Läufe, alle Patches im selben
PR-Strom sichtbar (Entscheidung: Phil 2026-06-07).

## Upstream-Stand (eingefroren)

| Repo | Commit |
|---|---|
| `auto-antislop` | `8fb98fdf019e6fcc20164f9bdec41f9008fcd632` |
| `antislop-vllm` (submodule → flach) | `9204efc348b936c4995994586c063f6ed3282219` |
| `slop-forensics` (submodule → flach) | `fa5465881033c9196af35bd281bb391666c3b26f` |

Geklont 2026-06-07. Submodule sind als normale Verzeichnisse eingebettet (kein
`.gitmodules`). Beim Vendoren ausgeschlossen: alle `.git/`, `*.ipynb`, die zwei
englischen Beispiel-`data/human_writing_profile.json` (74 MB + 29 MB — wir nutzen
unser DE-Profil) sowie `slop-forensics/results/`. Footprint dadurch 108 MB → 1,1 MB.

## Gesetzte Patches (`# DE-PATCH`-Marker im Code)

| Datei | Stelle | Vorher → Nachher |
|---|---|---|
| `auto_antislop_config.yaml` | `:9` | `human_profile_path` `data/human_writing_profile.json` → `/cache/human_writing_profile_de.json` (Modal-Volume) |
| `auto_antislop_config.yaml` | `:15` | `model_id` `unsloth/gemma-3-4b-it` → `google/gemma-3-12b-it` |
| `auto_antislop_config.yaml` | `:90` | `generation_ngram_language` `english` → `german` |
| `auto_antislop_config.yaml` | `extra_ngrams_to_ban` | leer → 116 hand-kuratierte DE-Slop-Ngrams (full-run, Branchen-Spread, #13) |
| `auto_antislop_config.yaml` | `extra_slop_phrases_to_ban` | leer → 38 DE-Surface-Seeds (16 Floskeln + 22 Nominalstil-Marker) |
| `core/orchestration.py` | `:290` | `stopwords.words('english')` → `'german'` (+ Log-/Error-Texte) |
| `slop-forensics/slop_forensics/analysis.py` | `:132` | `word_frequency(word, 'en')` → `'de'` |
| `core/finetuning.py` | `:54` | Compat (kein DE): `trl>=0.20` entfernte `ORPOTrainer/ORPOConfig` aus dem Top-Level — Sammelimport riss `DPOTrainer` mit runter und brach FTPO. ORPO/KTO jetzt best-effort, DPO bleibt hart importiert. |
| `main.py` | `:182` | Tooling-Ehrlichkeit (kein DE, #20): neuer `--finetune-max-train-examples`-Flag. `merge_config_with_cli_args` greift ihn über den `_FINETUNE`-Key-Loop automatisch ab, kein Merge-Patch nötig. Macht den vorher vestigialen `max_train_examples`-Parameter in `modal_app.py::run_pipeline` echt — Trainings-Menge wird per CLI gesteuert statt per stiller config-Mutation. |

Quelle der Banlist: `configs/de_extra_bans.json` (dieses Repo). Die **Kern**-Banlist
ist laufzeit-generiert aus dem Profil-Diff (`config:88`) — durch DE-Profil +
`ngram_language: german` wird sie automatisch deutsch; nur die statischen
`extra_*`-Listen mussten getauscht werden.

FTPO-Hyperparameter standen upstream bereits auf Soll und blieben unverändert:
`finetune_mode: ftpo`, `finetune_lora_r: 128`, `finetune_beta: 0.1`,
`ftpo_lambda_mse: 0.4`, `generation_max_prompts: 1000`.

## Offen — Integrations-Punkte für die Modal-Run-Session (kosten Geld/Auth)

1. **Prompts-Brücke** (`config:52 generation_hf_dataset_name`): zeigt noch auf das
   englische Reddit-Dataset (mit TODO markiert). antislop-vllm liest Prompts via
   `--input-hf-dataset` (HF-Dataset-Name). Zwei saubere Wege: unsere
   `data/prompts_de.jsonl` als privates HF-Dataset pushen, **oder** antislop-vllm
   patchen, sodass `--input-hf-dataset` einen lokalen jsonl-Pfad akzeptiert.
2. **Generierungs-Register-DE** (`config:74/75`): `generation_prompt_template` und
   `generation_system_prompt` sind englisch. Für DE-Copy-Generierung an unser
   Prompt-Format + den text-only-System-Prompt aus `scripts/generate_samples.py`
   angleichen.
3. **GPU-Image + Lauf**: `modal_app.py` — CUDA-devel-Basis (entschieden) mit
   gepinntem `torch==2.8.*`/vllm/flash-attn-Stack; `generate_and_profile` /
   `train_ftpo` an die vendored `main.py`-Pipeline verdrahten; DE-Profil +
   Prompts ins Volume `antislop-de-vol` hochladen. Iterativ, baukosten-/auth-
   behaftet → eigener Schritt.

Nichts unter „Offen" ist ungetestet als „fertig" deklariert.
