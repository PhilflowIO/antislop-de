# antislop-de

**English summary.** The method does exactly what it was built to do, and the
text still does not get better. That gap is why this repo is public. Goal:
fine-tune `google/gemma-3-12b-it` with FTPO (Final Token Preference Optimization,
Sam Paech) so it writes natural German marketing copy instead of the flat,
formulaic "AI voice".

What worked: the fine-tune cuts banlist phrases harder than anything else in the
comparison, 12.04 hits per 1,000 tokens against 19.20 for a plain system prompt
and 38.64 for the untouched model. A fabricated product claim that showed up in
20 of 36 texts dropped to 0, and seven text collapses dropped to 0. The training
recipe is sound and cheap, roughly nine dollars per run on one H100.

What did not: that winning number is scored against the very list the model was
trained on, so it mostly proves the training hit its target. Off that list the
model swaps one crutch for another, `maximal` goes from 1 hit to 59 and `absolut`
from 5 to 55, while the same prompt-only arm produces 0 and 1. Structural slop
(nominal style, passive voice) gets worse, median 63.8 against 56.1 untouched. In
a blind three-way read test over 36 held-out prompts with two independent LLM
reviewers (no human raters), the fine-tune was picked best in 0 cases and worst
in 32 and 35 cases respectively. Plain gemma with a plain anti-slop system prompt
was the strongest arm for both reviewers.

So: suppressing a list of phrases is not the same as writing like a person. If you
came for a solution, take the prompt in
[`configs/antislop_prompt.md`](./configs/antislop_prompt.md) and skip the LoRA. If
you came to push the method further, the three places worth attacking are in
"Wo man ansetzen sollte" below.

Everything below is in German; the full project diary is
[`JOURNEY.md`](./JOURNEY.md).

---

## Worum es ging

Instruction-Tuning und RLHF glätten Sprache. Deutsche KI-Copy klingt danach
gleichförmig: Nominalstil, Floskeln, Adjektiv-Ketten, „nahtlos", „kristallklar",
„maximal". Die Idee war, das an der Wurzel zu lösen statt mit einem nachgelagerten
Humanizer: **FTPO** zieht den modell-eigenen Slop auf Gewichts-Ebene raus, ohne
die Fähigkeiten zu beschädigen, anders als DPO. Für Englisch gibt es das
(`sam-paech/auto-antislop`), für Deutsch nicht. Dieses Repo ist der deutsche Bau.

Basismodell `google/gemma-3-12b-it`, Training auf Modal (H100, rund 9 Dollar für
den vollen Lauf), Anwendungsfall deutsche Website-Copy, Holdout ein Prompt-Set,
das nie im Trainings-Grid war.

## Das Hauptergebnis: der Prompt schlägt den Finetune

Drei Arme, dieselben 36 Holdout-Prompts, temperature 0,7:

1. **Baseline**: nacktes `google/gemma-3-12b-it`, kein System-Prompt.
2. **Prompt-only**: dasselbe Modell plus dem Anti-Slop-System-Prompt aus
   [`configs/antislop_prompt.md`](./configs/antislop_prompt.md).
3. **v2-Finetune**: das FTPO-trainierte Modell.

### Blinder Lesetest

Zwei unabhängige Gutachter, verdeckte Zuordnung der Arme, pro Prompt je ein
bester und ein schlechtester Text. **Beide Gutachter sind LLMs, keine Menschen.**
Das schwächt den Test: ein Modell, das Slop beurteilt, trägt denselben
Trainingsdurchschnitt wie das Modell, das ihn erzeugt. Ein Menschentest über
dieselben 36 Gruppen wurde nicht durchgeführt. Die beiden Gutachter arbeiteten mit
verschiedenen Maßstäben: Gutachter 1 fragte, ob sich der Text nach einem
deutschen Werbetexter liest, Gutachter 2 prüfte strikt gegen die Slop-Definition
„Text, der die Gesten des Sagens macht, ohne etwas zu sagen".

| Arm | G1 bester | G1 schlechtester | G2 bester | G2 schlechtester |
|---|---|---|---|---|
| Baseline | 17 / 36 | 2 / 36 | 1 / 36 | 1 / 36 |
| Prompt-only | 19 / 36 | 2 / 36 | **35 / 36** | 0 / 36 |
| v2-Finetune | **0 / 36** | **32 / 36** | **0 / 36** | **35 / 36** |

Beim schlechtesten Text stimmten beide Gutachter in 31 von 36 Fällen überein.
Der Finetune ist der einzige Arm, den kein Gutachter je vorne sah.

### Objektive Messung

Gerechnet mit `eval/run_holdout_eval.py` und `eval/structural_slop.py` gegen
`data/eval_banlists/banned_slop_phrases.json`, Struktur-Referenz
`dialog/literary`.

| Arm | Banlist-Treffer / 1k Tokens | Struktur-Slop, Median | „maximal" | „absolut" | „inklusive" |
|---|---|---|---|---|---|
| Baseline | 38,64 | 56,1 | 1 | 5 | 9 |
| Prompt-only | 19,20 | 57,3 | 0 | 1 | 7 |
| v2-Finetune | **12,04** | **63,8** | **59** | **55** | **39** |

Beim Struktur-Slop ist niedriger besser. Der Finetune gewinnt nur auf der
Metrik, gegen die er trainiert wurde, und ist auf allen anderen der schlechteste
Arm. Die Wortzahlen sind Substring-Zählungen ohne Groß-/Kleinschreibung über
alle 36 Texte des jeweiligen Arms, nachrechenbar mit
`sum(t.lower().count("maximal") for t in texts)`.

### Die Tic-Verschiebung

Das Training drückt nicht Slop, es verschiebt ihn. Gemessen über dieselben 36
Texte, gleiche Zählmethode:

| Wort | v1: Baseline → Finetune | v2: Baseline → Finetune |
|---|---|---|
| „inklusive" | 14 → **558** | 9 → **39** |
| „maximal" | 5 → 4 | 1 → **59** |
| „absolut" | 6 → **19** | 5 → **55** |

v1 kollabierte auf „inklusive". v2 hat diesen Tic gedämpft und dafür „maximal"
und „absolut" hochgezogen. Das ist Whac-a-Mole, und es ist strukturell: eine
feste Liste holt ein ausweichendes Modell nie ein.

Der Prompt, der gewonnen hat, steht in
[`configs/antislop_prompt.md`](./configs/antislop_prompt.md). Er kostet nichts,
braucht keine GPU und kein Training.

## Empfehlung für Nachnutzer

**Nimm den Prompt, nicht das LoRA.** Slop in deutscher Website-Copy ist nach
diesen Messungen ein Register- und Prompt-Problem, kein Gewichts-Problem.

## Bekannte Methodikfehler

Diese Fehler stecken in den oben genannten Läufen. Wer die Ergebnisse
weiterverwendet, sollte sie kennen.

- **Die Chosen-Quota im Upstream-Framework ist toter Code.** `tgt_chosen` wird in
  `vendor/auto-antislop/utils/dataset_helpers.py:127` berechnet und danach nur
  noch geloggt (Zeilen 131, 136, 137), sie filtert nichts. Folge: „ inklusive"
  war laut Trainingslog 218 Mal Chosen-Token, obwohl das Framework selbst einen
  Deckel von 93 errechnet hatte. Der Tic wurde antrainiert, nicht emergent. Das
  ist ein Fehler im Upstream-Code von Sam Paech, nicht in diesem Repo. Der
  Vendor-Baum liegt nicht hier, siehe [`vendor/README.md`](./vendor/README.md).
- **Die früher berichtete 92-Prozent-Reduktion ist zirkulär und nicht
  reproduzierbar.** Gemessen wurde gegen dieselbe Banlist, gegen die trainiert
  wurde. Eine Nachrechnung mit demselben Code auf denselben Dateien ergibt rund
  66 Prozent (`data/eval_raven_compare_broad_t0.7.json`: 25,12 auf 8,43 Treffer
  je 1000 Tokens). Der Report `data/eval_holdout_report.json` ist nicht
  versioniert, die ursprüngliche Zahl also nicht nachprüfbar.
- **Kein Validierungssplit.** `vendor/auto-antislop/core/finetuning.py:829`
  übergibt nur `train_dataset`, gestoppt wurde per `ThresholdStop("chosen_win", …)`
  in Zeile 875, also auf dem Trainingssignal selbst. `chosen_win` schwankt
  zwischen aufeinanderfolgenden Log-Events stärker als der Unterschied zwischen
  der v1- und der v2-Einstellung (0,86 gegen 0,78). Der Schwellwert trennt damit
  weniger, als das Rauschen breit ist.
- **Der Capability-Beleg ist zu klein.** GSM8K 87 auf 86 Prozent bei n=100
  (`data/eval_capability.json`) ist ein einziger Fall Unterschied und liegt im
  Rauschen. Die Aussage „FTPO beschädigt die Fähigkeiten nicht" ist damit nicht
  belegt, nur nicht widerlegt.
- **Konstruktlücke.** Slop ist semantisch definiert, also eine Eigenschaft von
  Aussagen. FTPO greift auf einem einzelnen Token. Von den sechs Slop-Klassen,
  die wir unterschieden haben, erfasst das Verfahren zwei. Struktureller Slop
  wurde nur gemessen, nie als Trainingssignal verdrahtet, und er hat sich durch
  das Training verschlechtert (56,1 auf 63,8, siehe Tabelle oben).
- **Der ursprüngliche Prompt-only-Arm existierte nicht.** Die Datei
  `data/eval_raven_compare_broad_t0.7_promptonly.json` enthält in allen 36 Fällen
  byteidentische Kopien der Baseline-Texte, der Arm wurde nie generiert. Alle
  Prompt-only-Zahlen oben stammen aus dem Nachlauf vom 2026-09-04, siehe
  Reproduktion.

## Wo man ansetzen sollte

Drei konkrete Einstiegspunkte, in dieser Reihenfolge:

1. **Die tote Bremse reparieren.** Die Chosen-Quota tatsächlich anwenden, statt
   sie nur zu loggen. Ohne das trainiert man den Tic mit, den man wegtrainieren
   will.
2. **Gegen eine Held-out-Liste messen.** Die Trainings-Banlist und die
   Eval-Banlist trennen. Solange beide identisch sind, misst jede Zahl nur, ob
   das Training angekommen ist.
3. **Den Prompt als Kontrollarm ernst nehmen.** Ein Finetune muss den
   System-Prompt schlagen, sonst ist er die teurere Variante des Gleichen. In
   diesem Projekt hat er ihn nicht geschlagen.

Wenn du an der Trainings-Ebene weiterarbeiten willst: eine feste Banlist hat
eine Decke, die man nicht wegtrainiert. Zwei Richtungen, die diese Decke
angreifen, beide hier nicht getestet:

- **Dynamisches Frequenz-Anomalie-Ziel** statt eingefrorener Liste. Bestrafe,
  was gegenüber einem menschlichen Referenzkorpus zur Laufzeit
  überrepräsentiert ist. Dann wandert das Ziel mit, wenn das Modell ausweicht.
- **Multi-Amateur Contrastive Decoding.** Gegen die Logits eines absichtlich
  sloppy „Amateur"-Modells decodieren. Training-frei, wirkt zur Inferenzzeit.

## Was im Repo liegt

```
JOURNEY.md              Projekttagebuch, sechs Sessions, inklusive der Fehlerkorrektur
configs/antislop_prompt.md   der Prompt, der gewonnen hat
configs/de_extra_bans.json   116 kuratierte DE-Slop-Ngrams + 38 Surface-Seeds
configs/copy_prompts/        Subjekte, Copy-Typen, Töne für die Prompt-Generierung
scripts/baseline.py          baut das deutsche Human-n-gram-Profil (Stufe 0)
scripts/build_prompts.py     erzeugt das Prompt-Grid für die Profiling-Phase
scripts/build_banlist.py     Slop-Kandidaten aus den Generierungen, nach Branchen-Spread
scripts/deploy_verda.py      vLLM-Serverless-Deploy des Merges
scripts/generate_verda.py    Copy-Harness gegen den Endpoint
modal_app.py                 Modal-Pipeline: Generierung, FTPO-Training, Eval, Upload
eval/run_holdout_eval.py     die Metriken oben
eval/structural_slop.py      Struktur-Schicht (spaCy): Nominalstil, Passiv, Satzlänge
eval/build_3way_demo.py      der Dreiwege-Lesetest als HTML
docs/SERVING.md              Hosting des Merges, inklusive der Bringup-Fallen
vendor/PATCHES-DE.md         jede Änderung an Paechs Code, mit Datei und Zeile
```

`vendor/auto-antislop/` ist **nicht** Teil dieses Repos. Wie du es dir holst und
auf Deutsch patchst, steht in [`vendor/README.md`](./vendor/README.md).

Dieses Repo auf GitHub trägt einen einzelnen Veröffentlichungs-Commit. Die
vollständige Entwicklungshistorie über 92 Commits liegt beim Autor und ist hier
nicht enthalten, weil einzelne dieser Commits den Upstream-Code von Sam Paech
einbringen, der keine Lizenz trägt und deshalb nicht weitergegeben werden darf.
Inhaltlich bildet [`JOURNEY.md`](./JOURNEY.md) den gesamten Verlauf ab.

## Reproduktion

```bash
uv sync                                        # Python >= 3.12, spaCy-DE-Modell kommt mit
uv run python scripts/build_prompts.py         # -> data/prompts_de.jsonl (deterministisch)
uv run python scripts/build_eval_prompts.py    # -> data/eval_raven_prompts.jsonl
uv run python scripts/baseline.py              # -> data/baseline/human_writing_profile_de.json
uv run python eval/run_holdout_eval.py         # -> data/eval_holdout_report.json
uv run python eval/build_3way_demo.py          # -> data/eval_3way_demo.html
```

Training und Generierung laufen über `modal_app.py` (Modal-Account nötig,
Entrypoints `smoke`, `eval_compare`, `capability_compare`, `publish`).

`eval/run_holdout_eval.py` vergleicht in seiner ausgelieferten Form nur Baseline
gegen Finetune. Für die Dreiwege-Tabelle oben ruft man dieselbe Funktion
`_side(texts, phrases, ref_lively)` ein drittes Mal mit den Prompt-only-Texten
auf.

### Den Prompt-only-Arm selbst erzeugen

Der Arm liegt als `data/eval_raven_compare_broad_t0.7_promptonly_rerun.json` vor,
`data/` ist aber gitignored. So erzeugst du ihn:

- **Modell:** `google/gemma-3-12b-it`, ohne Adapter, ohne Merge.
- **Endpoint:** OpenAI-kompatible Chat-Completions-API eines beliebigen
  Hosters. Der Lauf vom 2026-09-04 nutzte DeepInfra.
- **System-Prompt:** wörtlich der Inhalt von
  [`configs/antislop_prompt.md`](./configs/antislop_prompt.md), unverändert.
- **User-Prompts:** das Feld `prompt` aus den 36 Zeilen von
  `data/eval_raven_prompts_broad.jsonl`, in Dateireihenfolge.
- **Sampling:** `temperature = 0.7`, `seed = 1234 + idx` mit `idx` als
  Zeilenindex ab 0.
- **Ausgabeformat:** JSON-Liste mit 36 Objekten, Schlüssel `id`, `copy_type`,
  `tone`, `length`, `promptonly`. Die `id` muss zu
  `data/eval_raven_compare_broad_t0.7_v2.json` passen, sonst lassen sich die Arme
  nicht paaren.

Gegenprobe, dass der Arm wirklich generiert wurde und nicht wieder die Baseline
enthält:

```python
import json
v2 = {e["id"]: e["baseline"] for e in json.load(open("data/eval_raven_compare_broad_t0.7_v2.json"))}
po = json.load(open("data/eval_raven_compare_broad_t0.7_promptonly_rerun.json"))
print(sum(1 for e in po if v2.get(e["id"]) == e["promptonly"]), "von", len(po), "identisch")
```

Erwartet wird `0 von 36 identisch`. Die alte Datei ohne `_rerun` liefert hier
`36 von 36` und ist der oben beschriebene Fehler.

## Was fehlt und wie du es dir baust

`data/` ist gitignored. Es enthält Korpora, das n-gram-Profil und die
Generierungs-Ergebnisse, teils groß, teils lizenzbehaftet. Was die Skripte
erwarten und woher es kommt:

| Datei | Gebraucht von | Woher |
|---|---|---|
| `data/raw/de_top_sentences.csv`, `de_top_words.csv` | `scripts/baseline.py`, `eval/check_candidates.py` | manuell laden von [orgtre/top-open-subtitles-sentences](https://github.com/orgtre/top-open-subtitles-sentences) |
| `data/baseline/human_writing_profile_de.json` | `modal_app.py`, `eval/check_candidates.py` | `scripts/baseline.py` baut es. German Commons (`coral-nlp/german-commons`) streamt automatisch von HF, die OpenSubtitles-CSV oben muss vorher liegen. Rund 50 MB, Laufzeit im Stunden-Bereich. |
| `data/prompts_de.jsonl` | `modal_app.py` | `scripts/build_prompts.py`, deterministisch reproduzierbar |
| `data/eval_raven_prompts.jsonl` | Eval-Generierung | `scripts/build_eval_prompts.py` |
| `data/samples_full.jsonl` | `scripts/build_banlist.py` | fällt beim Generierungs-Lauf an, GPU-Kosten. Das kuratierte Ergebnis liegt bereits getrackt in `configs/de_extra_bans.json`, du brauchst den Lauf also nur, wenn du die Banlist neu bauen willst. |
| `data/eval_raven_compare_broad_t0.7*.json` | `eval/run_holdout_eval.py`, `eval/build_3way_demo.py` | `modal_app.py eval_compare`, GPU-Kosten. Ohne diese Dateien laufen die beiden Eval-Skripte nicht, die Zahlen oben also nicht nachrechenbar. |
| `data/eval_raven_compare_broad_t0.7_promptonly_rerun.json` | `eval/build_3way_demo.py` | selbst erzeugen, siehe Reproduktion. Kein Training nötig, nur API-Kosten für 36 Generierungen. |

Das trainierte Modell selbst (`PhilflowIO/gemma-3-12b-it-antislop-de`) liegt in
einem privaten HF-Repo und ist nicht Teil dieser Veröffentlichung. Gemessen an
dem Ergebnis oben ist das kein Verlust.

## Lizenzen

Drei verschiedene Rechtslagen in einem Verzeichnis, sauber getrennt:

**Eigener Code: Apache-2.0.** Alles in `scripts/`, `eval/`, `configs/`,
`modal_app.py` und die Dokumentation. Siehe [`LICENSE`](./LICENSE),
Copyright 2026 Philipp Lutje.

**Basismodell und Merge: Gemma Terms of Use.** `google/gemma-3-12b-it` steht
unter den [Gemma Terms of Use](https://ai.google.dev/gemma/terms), nicht unter
Apache-2.0. Jedes davon abgeleitete Gewicht, also auch unser FTPO-Merge, erbt
diese Bedingungen samt der
[Prohibited Use Policy](https://ai.google.dev/gemma/prohibited_use_policy). Wer
das Modell weiterverwendet, ist an die Gemma-Bedingungen gebunden, nicht an
Apache-2.0.

**Upstream-Pipeline: Sam Paech.** `auto-antislop` samt Submodulen ist nicht
unser Code und liegt nicht in diesem Repo. Im eingefrorenen Stand vom 2026-06-07
trug nur `slop-forensics` eine Lizenzdatei: MIT, Copyright (c) 2025 Sam Paech.
Für `auto-antislop` und `antislop-vllm` lag keine Lizenzdatei im übernommenen
Baum, prüfe sie im Upstream-Repo. Details in
[`vendor/README.md`](./vendor/README.md).
