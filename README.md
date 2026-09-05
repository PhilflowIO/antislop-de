# antislop-de

**Bring einem Sprachmodell deutsche Sprache bei, die nach Mensch klingt.** Die vollständige Anti-Slop-Pipeline für Deutsch, von der Korpus-Destillation bis zum trainierten Modell.

Gebaut auf einem Lineal aus 860 Millionen Zeichen menschlichem Deutsch, einem Diskriminator, der Fachbegriff von Floskel trennt, und dem ersten deutschen FTPO-Finetune.

Dazu kommt das Instrument. Eine Vierfeld-Messung prüft Finetune und System-Prompt einzeln und zusammen. Sie macht den Unterschied sichtbar zwischen „die Zahl wird besser“ und „der Text wird besser“. Die meisten Veröffentlichungen melden eine Zahl gegen eine Baseline und können diesen Unterschied gar nicht sehen.

[![License: Apache 2.0](https://img.shields.io/badge/Code-Apache%202.0-blue.svg)](./LICENSE)
[![Model](https://img.shields.io/badge/%F0%9F%A4%97%20Modell-gemma--3--12b--it--antislop--de-yellow)](https://huggingface.co/PhilflowIO/gemma-3-12b-it-antislop-de)
[![Base](https://img.shields.io/badge/Basis-gemma--3--12b--it-lightgrey)](https://huggingface.co/google/gemma-3-12b-it)

---

## Schnellstart

Zwei Wege führen zu weniger Slop, und sie beantworten verschiedene Fragen. Der Prompt allein liefert den Text, den die Gutachter am häufigsten als besten wählen. Modell und Prompt zusammen liefern die stärkste Phrasenunterdrückung, brauchen aber eine Redaktionsrunde. Beide Zahlen stehen unter [Was die Messung zeigt](#was-die-messung-zeigt).

### Weg 1: der Prompt allein (kostenlos, keine GPU)

Nimm ein beliebiges Modell und häng diesen System-Prompt davor. Er senkt die Banlist-Treffer von 38,64 auf 21,04 je 1.000 Tokens und ist der Arm mit den besten Lesetest-Bewertungen.

```
Du bist ein erfahrener deutscher Werbetexter. Gib ausschließlich den fertigen
Website-Text aus, keine Vorrede, keine Erklärung, keine Optionen. Schreibe knapp
und direkt in der Du-Form. Vermeide Marketing-Floskeln und leere Verstärker wie
'maximal', 'kristallklar', 'nahtlos', 'inklusive allem', 'souverän'. Keine
Doppelpunkt-Einleitungen, keine Adjektiv-Aufzählungen. Aktiv statt Passiv, kurze
Sätze, konkret sagen, was das Produkt tut.
```

Volle Fassung samt Inferenz-Einstellungen: [`configs/antislop_prompt.md`](./configs/antislop_prompt.md)

### Weg 2: Modell und Prompt zusammen (stärkste Phrasenunterdrückung)

Denselben System-Prompt aus Weg 1 davorhängen. Ohne ihn produziert das Modell seine eigenen antrainierten Tics.

> **Lade das Modell mit `transformers==4.56.2`.** transformers 5.x benennt die Gemma-3-Parameter
> um, der Checkpoint greift dann nicht mehr. Du bekommst nur eine Warnung, zufällig
> initialisierte Gewichte und als Ausgabe zusammenhanglose Tokens aus fremden Schriftsystemen.
> Das sieht nach einem kaputten Modell aus und ist eine falsche Bibliotheksversion.

```bash
pip install "torch==2.8.*" "transformers==4.56.2"
```

```python
from transformers import AutoModelForImageTextToText, AutoTokenizer

tok = AutoTokenizer.from_pretrained("PhilflowIO/gemma-3-12b-it-antislop-de")
model = AutoModelForImageTextToText.from_pretrained(
    "PhilflowIO/gemma-3-12b-it-antislop-de",
    torch_dtype="bfloat16", device_map="cuda")
```

`temperature=0.7`. Produktfakten faktentreu in den User-Prompt geben, sonst erfindet das Modell Positionierung. Diese Kombination erreicht 6,27 Banlist-Treffer je 1.000 Tokens, den besten Wert der Messung, und braucht danach eine menschliche Redaktion für Satzbau und Grammatik.

### Weg 3: die Pipeline neu fahren

```bash
# 1. Upstream holen, er liegt nicht im Repo (Lizenzgrund, siehe unten)
git clone https://github.com/sam-paech/auto-antislop vendor/auto-antislop
git -C vendor/auto-antislop checkout 8fb98fdf019e6fcc20164f9bdec41f9008fcd632
# DE-Patches anwenden, Anleitung in vendor/PATCHES-DE.md

# 2. Abhängigkeiten und Lineal
uv sync
uv run python scripts/baseline.py --gc-tokens 55000000

# 3. Modal einrichten und prüfen
modal token new
modal run modal_app.py            # Preflight, gibt den Abnahme-Report aus
modal run modal_app.py::smoke     # kleiner End-to-End-Lauf zum Gegenprüfen

# 4. Messen
uv run python eval/run_holdout_eval.py
```

Voraussetzungen für den GPU-Lauf: Modal-Secret `huggingface` mit einem HF-Token, akzeptierte Gemma-Lizenz auf Hugging Face, Volume `antislop-de-vol` (legt der Preflight an). Ein voller Lauf dauert rund zwei Stunden und kostet acht bis neun Dollar.

---

## Was hier entstanden ist

Für Englisch gibt es eine Anti-Slop-Werkzeugkette. Für Deutsch gab es nichts. Das ist der Teil, der bleibt, unabhängig davon, wie das Training ausgegangen ist.

| | vorher für Deutsch | mit antislop-de |
|---|---|---|
| **Referenz für „natürliches Deutsch"** | nicht vorhanden | 860 Mio. Zeichen, register-gemischt, calque-gefiltert, pre-2022 |
| **Floskel gegen Fachbegriff trennen** | nicht gelöst | Branchen-Spread-Diskriminator über 15 Branchen |
| **Nominalstil und Passiv messen** | nicht vorhanden | sechs spaCy-Metriken gegen eine menschliche Referenz |
| **Deutsche Slop-Banlist** | nicht vorhanden | 2.302 N-Gramme + 1.838 Phrasen, generiert und handkuratiert |
| **Deutsches FTPO-Rezept** | nicht vorhanden | vollständige Modal-Pipeline, ein Lauf für neun Dollar |
| **Anti-Slop-Prompt für DE-Copy** | nicht vorhanden | acht Zeilen, in vier Armen gegengemessen |

---

## Die Werkzeuge im Einzelnen

### 1. Das Lineal: `scripts/baseline.py`

Slop ist nichts Absolutes. Ein Wort wird zu Slop, wenn es in einem Register viel häufiger auftaucht, als ein Mensch es dort benutzen würde. Der Detektor braucht also einen Referenzkorpus, und dessen Qualität entscheidet über alles Weitere.

Destilliert ein N-Gramm-Frequenzprofil aus German Commons und OpenSubtitles2018-DE. Registermischung: cultural 35,1 %, web 23,3 %, political 18,8 %, expository 16,0 %, Untertitel 6,8 %. Rund 33 Mio. Bigramme und 50 Mio. Trigramme. Alle Quellen pre-2022-sicher und lizenzsauber (ODC-BY, CC).

Enthält den **Calque-Filter**. Synchron-Deutsch aus englischen Filmen ist übersetztes Englisch mit deutschen Vokabeln; ohne Filter steht `sir` mit einer Frequenz von 460.755 im Korpus und gilt dem Detektor als Muttersprache. Der Filter zog die Frequenz-Spitze von 787k auf 62k. Abnahme-Dokumentation: [`docs/stufe-0-baseline.md`](./docs/stufe-0-baseline.md).

### 2. Der Diskriminator: `scripts/build_banlist.py`

Das Kernproblem jeder Slop-Erkennung: Ein korrekter Fachbegriff wie „Wärmepumpe" fehlt im Lineal genauso wie eine hohle Floskel. Beide sehen für den naiven Detektor gleich aus.

Die Lösung ist **Branchen-Spread**. Das Modell schreibt Copy über 15 Branchen. Streut ein N-Gramm über viele davon, ist es eine Floskel, denn „legen größten Wert" passt beim Dachdecker wie bei der Steuerkanzlei. Klebt es in einer Branche, ist es ein Fachbegriff und bleibt. Schwellwerte: Spread ≥ 5 markiert, ≤ 2 schützt.

Das ist die übertragbarste Idee des Projekts und funktioniert für jede Sprache.

### 3. Die Struktur-Messung: `eval/structural_slop.py`

N-Gramme fangen Phrasen-Slop. Sie fangen nicht das, was deutsche KI-Copy wirklich schwerfällig macht: Nominalstil, Schachtelsätze, Passiv-Überhang. Sechs spaCy-Metriken schließen die Lücke: Nominalisierungen je 100 Tokens, Nomen-Verb-Verhältnis, Satzlänge, Teilsätze je Satz, Parse-Tiefe, Passiv-Anteil, jeweils gegen eine menschliche Referenzverteilung.

Diese Messung deckte den wichtigsten Nebenbefund auf, siehe unten.

### 4. Die Banlist: `configs/de_extra_bans.json`

164 handkuratierte Einträge in vier Gruppen: 16 Floskeln, 22 Nominalstil-Marker, 116 branchenübergreifende N-Gramme, 10 emergente Tics. Dazu die zur Laufzeit generierte Liste aus 2.302 N-Grammen und 1.838 Phrasen.

Die Handkuratierung ist kein Beiwerk. Der automatische Teil bannt auch Wörter, die Inhalt tragen, und Eigennamen der Beispielfirmen.

### 5. Das Modell: FTPO-Training in `modal_app.py`

Serverlos auf einer H100. Ein voller Lauf, also Generierung, Banlist-Erzeugung, Training und Merge, dauert rund zwei Stunden und kostet acht bis neun Dollar.

FTPO statt DPO, weil DPO auf ganze Antworten optimiert und dabei Fähigkeiten mitverschiebt. FTPO greift auf einem einzelnen Token an einer einzelnen Position. Aus 1.380 Prompts entstehen über einen Backtracking-Sampler 3.778 Präferenzpaare.

### 6. Die Eval-Harness: `eval/run_holdout_eval.py`

Vergleicht beliebig viele Arme auf denselben Prompts mit demselben Seed. Misst Banlist-Treffer je 1.000 Tokens, Struktur-Slop, Tic-Frequenzen, Degenerationen und Lexik-Vielfalt. Der Holdout ist ein Prompt-Set, das im Trainings-Grid als `profiling: false` markiert war und nie im Trainingsmaterial lag.

---

## Was die Messung zeigt

Vier Arme aus zwei Faktoren, Finetune ja/nein mal System-Prompt ja/nein. Dieselben 36 Holdout-Prompts, dieselbe H100, `temperature=0.7`, Seed `1234+idx`.

| Arm | Banlist-Treffer /1k | Struktur-Slop (Median) | „maximal“ | „absolut“ | „eben alles“ | „revolutionier…“ |
|---|---|---|---|---|---|---|
| Basismodell, nackt | 38,64 | 56,1 | 1 | 5 | 0 | 13 |
| Basismodell + Prompt | 21,04 | **33,7** | 1 | 1 | 0 | 0 |
| FTPO-Finetune, nackt | 12,04 | 63,8 | 59 | 55 | 13 | 5 |
| FTPO-Finetune + Prompt | **6,27** | 60,6 | 15 | 17 | 0 | 0 |

**Die Methode wirkt, und sie stapelt sich mit Prompting.** Der Prompt allein drückt die Banlist-Treffer von 38,64 auf 21,04, der Finetune allein auf 12,04, beides zusammen auf 6,27. Der Finetune hat dabei auch eine echte Floskel entfernt, „revolutionier…“ fällt von 13 auf 5.

**Und genau der Arm mit dem besten Messwert wird im Lesetest schlecht bewertet.** Die Metrik verbessert sich, der Text verschlechtert sich, im selben Experiment. Beides steht nebeneinander, keines hebt das andere auf.

Zwei ältere Einschränkungen gelten weiter.

**Die Banlist-Zahl ist zirkulär.** Gemessen wird gegen dieselbe Liste, die ins Training ging. Das belegt, dass das Training sein Ziel getroffen hat. Über den Text sagt es nichts. Eine Nachrechnung heute ergibt statt der ursprünglich berichteten 92 Prozent rund 66.

**Ohne Prompt wandert der Slop, statt zu verschwinden.** Bannt man `inklusive`, fällt es von 558 auf 39 Treffer. An derselben Stelle springt `maximal` von 1 auf 59, `absolut` von 5 auf 55.

### Blinder Lesetest

36 Holdout-Prompts, verdeckte Zuordnung, bester und schlechtester Text je Aufgabe. Zwei Gutachter mit verschiedenen Maßstäben, beide sind LLMs, keine Menschen. Das schwächt den Test, ein Menschentest steht aus.

| Arm | Gutachter 1: bester / schlechtester | Gutachter 2: bester / schlechtester |
|---|---|---|
| Basismodell, nackt | 7 / 1 | 2 / 1 |
| Basismodell + Prompt | **25** / 1 | **31** / 0 |
| FTPO-Finetune, nackt | 0 / 20 | 0 / **34** |
| FTPO-Finetune + Prompt | 4 / **14** | 3 / 1 |

Kein Finetune-Arm kommt bei den besten Texten in die Nähe des Prompts allein. Beim schlechtesten Text sind sich die Gutachter uneinig, wie hart sie den kombinierten Arm treffen. Gutachter 1 setzt ihn in 14 von 36 Fällen ans Ende, Gutachter 2 nur einmal.

### Woher der Abstand kommt

Die Ursache lässt sich trennen, und zwar in zwei Teile.

**Den Wortschatz repariert der Prompt.** Die antrainierten Krücken verschwinden mit ihm. „eben alles“ fällt von 13 auf 0, „maximal“ von 59 auf 15, „absolut“ von 55 auf 17.

**Den Satzbau repariert er nicht.** Der Struktur-Slop des kombinierten Arms bleibt bei 60,6, gegen 33,7 beim Basismodell mit demselben Prompt. Dazu kommen Grammatikschäden. Von zehn Wendungen, die die Gutachter als kaputt markiert haben, stammen acht ausschließlich aus den Finetune-Armen, im Basismodell kommt keine davon vor. Das ist die Herkunftsprüfung der benannten Fehler, keine systematische Grammatikprüfung des Korpus.

### Was der Finetune trotzdem behoben hat

Der Weg von v1 zu v2 war kein Leerlauf. Eine erfundene Produktbehauptung fiel von 20 auf 0 von 36 Texten, sieben Textkollapse auf 0, sämtliche Phantasiewörter verschwanden. Das Rezept selbst ist tragfähig.

---

## Der Fehler im Upstream-Framework

Das ist der Befund, der über dieses Projekt hinaus gilt. Wer `auto-antislop` benutzt, ist betroffen, unabhängig von der Sprache.

Der Backtracking-Sampler wählt beim Zurückspringen eine Alternative aus den 20 wahrscheinlichsten Folgetokens. Bei deutscher Werbesprache ist diese Menge klein und immer dieselbe. Im Trainingsprotokoll steht, welches Wort wie oft als Alternative gewählt wurde. Ganz oben, 218 Mal: `inklusive`.

Der Tic ist also nicht emergent. Er wurde antrainiert.

Dagegen gibt es eine eingebaute Obergrenze. Sie wird berechnet und für `inklusive` auf 93 gesetzt, drei Zeilen später ins Protokoll geschrieben, und danach nie angewendet:

```
utils/dataset_helpers.py:127   tgt_chosen = {...}      # berechnet
utils/dataset_helpers.py:131   logger.info(...)        # geloggt
utils/dataset_helpers.py:136   logger.info(...)        # geloggt
                               # und das war es
```

`tgt_chosen` filtert keine einzige Zeile. Die Bremse ist verbaut, wird angezeigt, und war nie mit den Rädern verbunden.

---

## Was das für dich heißt

**Du musst Floskeln aus einer festen Liste zuverlässig loswerden.** Nimm Modell und Prompt zusammen. Das ist mit 6,27 Treffern je 1.000 Tokens der stärkste Arm der Messung. Plane eine Redaktionsrunde für Grammatik und Satzbau ein, der Arm liefert keinen fertigen Text.

**Du willst einen lesbaren Entwurf.** Nimm den Prompt allein. Er kostet nichts, braucht keine GPU, und beide Gutachter wählen seine Texte am häufigsten als beste.

**Du willst die Methode weitertreiben.** Nimm die Baseline, den Spread-Diskriminator und die Eval-Harness. Das sind die Teile, die tragen. Drei Ansatzpunkte in der Reihenfolge ihrer Wirkung:

1. **Die tote Bremse reparieren.** Die berechnete Chosen-Quota anwenden. Fünf Zeilen, trifft die Ursache direkt.
2. **Gegen eine Liste messen, die das Training nicht kannte.** Ein zweiter Profiling-Lauf liefert sie. Ohne das misst jede Zahl sich selbst.
3. **Den Prompt als Kontrollarm ernst nehmen.** Der billigste Arm gehört an den Anfang, nicht ans Ende. Reicht er, hat sich die Trainingsfrage erledigt.
4. **Alle Kombinationen messen, nicht nur die naheliegenden Paare.** Der Finetune hat den Anti-Slop-Prompt in der ersten Messung nie bekommen. Daraus wurde ein Fazit, das die Vierfeld-Messung nicht hält.

**Du willst es grundsätzlich anders lösen.** Eine feste Liste ist eine Aufzählung, Slop ist eine Häufungs-Eigenschaft. Zwei Richtungen bieten sich an: ein dynamisches Frequenz-Anomalie-Ziel, das sich bei jedem Schritt neu gegen die Baseline-Verteilung misst, oder Multi-Amateur Contrastive Decoding, das ganz ohne Training auskommt und gegen die Logits eines absichtlich schlecht schreibenden Zweitmodells dekodiert.

---

## Was im Repo liegt

```
scripts/baseline.py          Lineal destillieren (das Herzstück)
scripts/build_banlist.py     Branchen-Spread-Diskriminator
scripts/build_prompts.py     Prompt-Grid über 15 Branchen
modal_app.py                 Generierung, FTPO-Training, Merge, HF-Upload
eval/run_holdout_eval.py     Mehr-Arm-Vergleich mit allen Metriken
eval/structural_slop.py      Nominalstil, Passiv, Satzbau
configs/antislop_prompt.md   der System-Prompt, in allen Armen derselbe
configs/de_extra_bans.json   handkuratierte Banlist
docs/stufe-0-baseline.md     Abnahme-Dokumentation des Korpus
docs/SERVING.md              Deploy auf einem vLLM-Endpoint
JOURNEY.md                   Projekttagebuch, sechs Sessions, alle Sackgassen
```

`data/` ist bewusst nicht eingecheckt: Korpora, Frequenzprofil und Eval-Ausgaben sind groß und teils lizenzbehaftet. `scripts/baseline.py` baut das Profil neu.

Dieses Repo trägt einen einzelnen Veröffentlichungs-Commit. Die vollständige Entwicklungshistorie über 92 Commits liegt beim Autor; `JOURNEY.md` bildet sie inhaltlich ab. Grund für den Schnitt ist der Vendor-Code, siehe Lizenzen.

---

## Lizenzen

| Teil | Lizenz |
|---|---|
| Code in diesem Repo | Apache 2.0, siehe [`LICENSE`](./LICENSE) |
| Basismodell und der Merge | [Gemma Terms of Use](https://ai.google.dev/gemma/terms) und [Prohibited Use Policy](https://ai.google.dev/gemma/prohibited_use_policy), **nicht** Apache |
| `sam-paech/auto-antislop`, `antislop-vllm` | keine Lizenzdatei im Upstream, daher nicht mitveröffentlicht. Siehe [`vendor/README.md`](./vendor/README.md) |
| `sam-paech/slop-forensics` | MIT |

---

## Dank

Gebaut auf der Arbeit von **[Sam Paech](https://github.com/sam-paech)**: [`auto-antislop`](https://github.com/sam-paech/auto-antislop) für Pipeline und FTPO, [`antislop-sampler`](https://github.com/sam-paech/antislop-sampler) für das Backtracking, [`slop-forensics`](https://github.com/sam-paech/slop-forensics) für die register-relative Baseline-Logik. Die Methode ist seine, die deutsche Portierung und die Befunde hier sind meine.

Paper: **Antislop: A Comprehensive Framework for Identifying and Eliminating Repetitive Patterns in Language Models**, [arXiv:2510.15061](https://arxiv.org/abs/2510.15061).

Korpus: **German Commons** (`coral-nlp/german-commons`, ODC-BY) und **OpenSubtitles2018-DE** über [`orgtre/top-open-subtitles-sentences`](https://github.com/orgtre/top-open-subtitles-sentences).

---

**Fragen oder Befunde?** [GitHub-Issue aufmachen](https://github.com/PhilflowIO/antislop-de/issues)

Die vierteilige Serie über den Bau: [philflow.io/blog](https://philflow.io/blog/anti-slop-4-whac-a-mole)

---

*Gebaut, damit deutsche KI-Texte nicht klingen wie deutsche KI-Texte*
