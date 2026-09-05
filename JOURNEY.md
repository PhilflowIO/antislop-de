# JOURNEY — antislop-de

**Was das hier ist:** das ehrliche Entwicklungstagebuch. Jeder Schritt, jede Sackgasse, jede
Korrektur — nicht der geglättete Rückblick. Bei einem Anti-Slop-Projekt wäre alles andere peinlich.

**Stand:** 2026-09-04, sechs Sessions, abgeschlossen. Das Projekt ist gescheitert und veröffentlicht,
weil das negative Ergebnis brauchbar ist. Session 6 trägt die Fehlerkorrektur nach. Die Einordnung für
Nachnutzer steht in der [README](./README.md).

---

## Phase 0 — Aufsetzen, eine Entscheidung, dann los

Gestartet mit vier Dokumenten im Rücken: `HANDOFF.md`, `KICKOFF.md` und zwei Research-Reports.
Die großen Entscheidungen standen schon: `gemma-3-12b-it` als Basis, FTPO statt DPO, Modal/H100,
Pangram als Schluss-Messlatte. Nicht neu aufgerollt.

Eine Frage war offen — die Lizenz. Soll der fertige Merge frei weiterverbreitbar sein? Dann
EuroLLM (Apache) statt Gemma. **Phil: Gemma 3 bleibt.** Kein Modellwechsel, Plan unverändert.

Repo eingerichtet: `uv`-Env, Forgejo-Issue [#1], Branch `feat/stufe-0-baseline`. Substrate: Forgejo
übers MCP, Git nativ.

---

## Phase 1 — Erst das Schema verstehen, dann bauen

Versuchung war, sofort ein n-gram-Profil zu rechnen. Stattdessen erst `auto-antislop` +
`slop-forensics` geklont und nachgesehen, was die Pipeline **exakt** als Human-Profil erwartet —
sonst baut man ein hübsches, inkompatibles Artefakt.

Befund: `data/human_writing_profile.json`, Top-Key `human-authored`, Felder `total_chars`,
`top_bigrams`/`top_trigrams` als `[{ngram, frequency}]`, je 500k. Und — der wichtigere Teil — die
n-gram-Extraktion muss **1:1** zur Generierungs-Seite laufen: `normalise_keep_marks` → NLTK-Tokenize
→ deutsche Stopwords + `min_word_len 3` raus → Bi/Trigramme über den gefilterten Strom. Nur so ist
der spätere Diff (gemma vs. Human) sauber vergleichbar. Also Paechs eigene Normalisierungs-Logik
nachgebaut und nur EN→DE-Stopwords getauscht (`scripts/baseline.py`).

Quellen: OpenSubtitles2018-DE als fertige Frequenzliste (`orgtre`, garantiert pre-LLM) + German
Commons register-selektiv gestreamt. Gelernt nebenbei: bei German Commons sind die *Splits* die
Quellen — man selektiert das Register direkt, kein Feld-Filter nötig.

---

## Phase 2 — Smoke zuerst. Gut, dass wir das taten.

Vor dem 45M-Token-Lauf ein Mini-Smoke. Die Bigramme waren sofort schön — „tut leid", „komm schon",
„guten tag", „moment mal", genau der gesprochene Ton. Aber die Trigramme verrieten Müll: „deutsche
untertitel the shield", „sdi media group", „netflix original serie". Untertitel-Credits, kein
Deutsch.

Gefixt: `_SUBTITLE_NOISE`-Filter, OpenSubtitles auf 40 %-Masse skaliert, ein Xet-Teardown-Crash
umschifft, Junk-Tokens raus. **Lehre, die sich durchzieht: jede Datenquelle schleppt ihren eigenen
Boilerplate ein, und man sieht ihn erst im Output.** Smoke-first hat in dieser Session jede einzelne
Kontaminationsklasse gefangen, bevor sie teuer wurde.

---

## Phase 3 — Erste Baseline, erste Abnahme

Voller Lauf, Mischung 40/25/20/15. Dazu ein Abnahme-Harness (`eval/check_candidates.py`): es prüft
dokumentierte deutsche KI-Floskeln gegen die Baseline. Ergebnis sah stark aus — „ganzheitlicher
ansatz" 0, „nahtlose integration" 0, während „tut leid" bei 742k lag. Controls 5/5.

Phil schaute drauf und stutzte: **„political so viel? cultural oder web noch 2 Prozent hoch?"** Recht
hatte er — die Bundestags-Protokolle sind extrem zeichendicht und blähten den Anteil auf. Rebalanciert
(political 25→17, cultural→23, web→19), committet [`7f53e65`]. Sah jetzt aufgeräumter aus.

Hätte man hier abnehmen können. Phil wollte mehr.

---

## Phase 4 — Die Sackgasse: drei Gutachter zerlegen die Gewichtung

**Phil: „hol mir drei MoE, die unbiased und kritisch die Gewichtung hinterfragen."**

Wichtig nach unserer eigenen Reviewer-Disziplin: drei Agenten mit *gleichem* Prompt sind kein
Triangulieren, das ist Echo. Also drei **orthogonale** Frames, Evidence-Pflicht, read-only:
- A — Register-Match: liegt der Slop überhaupt im Register, das die Baseline dominiert?
- B — Datenqualität: trägt jede Gewichtung saubere Daten?
- C — Downstream: welche konkreten Fehler erzeugt *diese* Gewichtung im fertigen Modell?

Alle drei: **fail**, Konfidenz 86–88. Und sie fanden — über verschiedene Beweispfade — denselben
Kerndefekt:

- Das **Sachtext-Register fehlte komplett.** Folge (A, am Profil gemessen): `ökonomische perspektive`
  hatte denselben Score 0 wie `ganzheitlicher ansatz`. Neutrales Sachdeutsch war von KI-Slop nicht zu
  unterscheiden.
- Die **40 % OpenSubtitles waren eine Illusion** (B): 2350 Sätze, ×22 hochskaliert, besetzten 97–99 %
  des Top-1000. Breit aussehend, dünn in echt.
- Dazu: **Synchron-Calques** (`sir` = 71 Bigramme / 460k Freq), Parlaments-Header im Top, Archaik,
  ein Abnahme-Harness ohne Sachtext-Gegenprobe, ein als „Proxy" verkauftes unkalibriertes ppl-Band.

Das war der Moment, in dem die Session ehrlich wurde. Die Gewichtung, auf die Phil und ich uns gerade
geeinigt hatten, war kaputt — und zwar tiefer als „zu viel political".

**Phil: „sir und fahr hölle ist kein deutsch wtf."** Genau. Synchron-Artefakte aus englischen Filmen,
die sich als natürliches Deutsch tarnten. Seine Reaktion war der Beweis, dass der Fix nötig war.

Entscheidung: **Sachtext-fähig, Baseline neu bauen.**

---

## Phase 5 — Redesign

Alle konvergenten Funde adressiert (`80a1c82`):
- **Neu: expository-Register** (Wikipedia-DE + scientific), gegen das Sachtext überhaupt erst fair
  gemessen werden kann. Konnektoren sprangen von ~0 hoch: „darüber hinaus" 123 → 6369.
- OpenSubtitles 40 → 7 % (scale hart bei 4× gedeckelt) — Abdeckung statt Frequenz-Monopol.
- Calque-Filter (`sir`-Bigramme → 0), Plenar-Header per Regex gestrippt (Ursache, nicht Symptom),
  Archaik modernisiert (`muß`→`muss`), expository-Negativ-Kontrolle ins Harness.
- Beim Bauen ein neuer Müll sichtbar: Wiki-Zeitstempel „jan cet", „mär cet" → Datums-Filter.

Dann — und das war die eigentliche Qualitätssicherung — **dieselben drei Gutachter zur Gegenprüfung
reaktiviert** (Kontext intakt). Alle drei zogen ihr fail zurück: **fail → pass.** A: Register
verankert. B: alle vier harten Funde root-cause-behoben, Frequenz-Spitze von 787k auf 62k entmonopolisiert.
C: systemische FP-Klasse weg, Rest nur bei Überproduktion (belegt aus dem ANTISLOP-Paper selbst).

B fand beim Gegenlesen noch zwei neue Artefakte derselben Klasse — und lokalisierte `gang gang`
sauber: eine **Getriebe-Tabelle in einem wikibooks-Traktor-Artikel** („gang km h" × viele Zeilen).
Plus HTML-Markup (`span style color`) aus Wiki-Rohtext. Beide gefixt (`bf272c5`): HTML-Tag-Strip,
Run-Cap gegen Tabellen-Repetition, ein Degen-Doc-Guard (skip, wenn ein Token > 8 %). `gang gang`
fiel von Rang 9 auf 78.

---

## Phase 6 — Paechs Kopf, und die Lücke die n-grams nicht sehen

**Phil: „wenn wir Sachtext so hoch machen, verhält es sich dann nicht wie ein Doc?"** Scharfe Frage,
und sie traf den Kern-Trade-off des ganzen Problems.

Ein Research-Agent ging Sam Paechs Denkweise nach (`research/anti-slop-sam-paech-perspektive-2026-06.md`).
Die zwei Sätze, die alles rahmen:
- *„The kinds of prompts you use determines the slop that will be removed."* Slop ist bei Paech
  **register-relativ**, und die Baseline **ist** die Definition von „natürlich".
- Die richtige Frage ist also nicht „Dialog vs. Literatur vs. Sachtext, was stimmt?", sondern
  **„in welchem Register soll das Modell schreiben?"** Danach richtet sich die Baseline 1:1.

Damit war Phils Einwand bestätigt: „Sachtext-fähig" heißt *lebendiges Deutsch, das Sachthemen kann* —
nicht „Sachtext-dominante Baseline". 27 % Wikipedia hätten das Doc-Register zur Norm gemacht.

Und ein Befund, der über Stufe 0 hinausreicht: **deutscher KI-Slop ist zur Hälfte strukturell** —
Nominalstil, Schachtelsätze, Passiv. Der n-gram-Ratio fängt Phrasen, aber keine Satzstruktur. Zwei
Sätze mit identischer Wortfrequenz können dröge oder lebendig sein.

Plan für die Lücke (Phil: beides ja):
- **(a)** Der *lexikalische* Teil des Nominalstils ist fangbar — „im rahmen der", „unter
  berücksichtigung", „die durchführung der", „erfolgt die". Als Seed-Banlist gesetzt
  (`configs/de_extra_bans.json`). Phil: „das ist behörden/sachlich deutsch." Genau.
- **(b)** Eine **strukturelle Mess-Schicht** (`eval/structural_slop.py`, spaCy): Nominalisierungsrate,
  Nomen/Verb-Ratio, Satzlänge, Klausel-Schachtelung, Passiv-Quote. Validiert — Behördendeutsch
  scort 311 gegen lebendiges Deutsch.

Die Mess-Schicht lieferte gleich das entscheidende Argument: pro Register gerechnet
(`eval/structural_reference.json`) ist **dialog/literarisch am lebendigsten** (Nominal. 1,05, Passiv
0,03) und **Wikipedia am drögsten** (Nomen/Verb 3,27, Passiv 0,21). Phils Doc-Sorge, schwarz auf weiß.

---

## Phase 7 — Finale Gewichtung, geerdet in Zahlen

Damit war die Entscheidung keine Geschmacksfrage mehr. Lebendige Register dominieren, expository
schmal, Dialog-Lebendigkeit über das diverse `cultural/dibilit` statt über inflationierte Untertitel:

**cultural 35,1 % · web 23,3 % · political 18,8 % · expository 16,0 % · OpenSubtitles 6,8 %**

Top sauber (Dialog + lebendig-formal), KI-Floskeln 0, Controls 5/5. Der bewusste Preis: seltenere
akademische Kollokationen (expository-Controls 5/12) — vertretbar, weil die Hochfrequenz-Konnektoren
geschützt bleiben und wir dafür die Doc-Falle vermeiden.

---

## Was wir gelernt haben

- **Prozent ≠ Substanz.** 40 % OpenSubtitles waren 2350 Sätze. Miss das Ding, nicht das Etikett.
- **Drei Reviewer mit gleichem Prompt = Echo.** Orthogonale Frames trennen Realität von kollektiver
  Halluzination. Hier haben sie denselben Defekt über drei verschiedene Beweispfade gefunden — das
  ist Triangulation, und sie hat funktioniert.
- **Die Baseline ist die Definition von „natürlich".** Paechs tiefster Punkt. Sie an das gewünschte
  Output-Register koppeln, nicht an ein abstraktes „richtig".
- **n-grams sehen Phrasen, nicht Struktur.** Deutscher Slop ist halb strukturell. Dafür braucht es
  eine eigene Mess-Schicht — gebaut, aber FTPO kann Struktur nur teilweise greifen. Offener Punkt
  für die Eval-Phase.
- **Smoke-first.** Jede Quelle schleppt Boilerplate ein (Untertitel-Credits, Zeitstempel, Calques,
  Parlaments-Header, Getriebe-Tabellen, HTML). Man sieht ihn erst im Output, nie in der Annahme.
- **Phils Augenschein schlägt den Score.** Zweimal hat sein Bauchgefühl („political so viel?", „wie
  ein Doc?") einen echten Defekt aufgedeckt, den die grünen Zahlen verdeckten.

---

## Artefakte

- `scripts/baseline.py` — der Baseline-Builder (Streaming, Filter, Profil)
- `data/baseline/human_writing_profile_de.json` — das Profil (gitignored, reproduzierbar)
- `eval/check_candidates.py` + `eval/slop_candidates.json` — Floskel-/Control-Abnahme
- `eval/structural_slop.py` + `eval/structural_reference.json` + `eval/build_structural_reference.py`
  — strukturelle Mess-Schicht
- `configs/de_extra_bans.json` — Seed-Banlist (Floskeln + Nominalstil-Marker), hand-review ausstehend
- `docs/stufe-0-baseline.md` — Stufe-0-Abnahme-Dokument

## Commits (Stufe 0)

`b24fa69` Baseline gebaut · `7f53e65` Register rebalanciert · `80a1c82` Redesign nach 3-Gutachter-Audit
· `bf272c5` Markup-/Tabellen-Artefakte gefiltert · `79a1e0f` strukturelle Schicht + Seed-Banlist
· (final) Gewichtung daten-geerdet

---

# Session 2 — Modal-Infra & der Weg zur Banlist

**Stand:** 2026-06-07, zweite Bau-Session. Stufe 1 (Modal-Infra) steht, Schritt 2 (Profiling-Prompts
+ kuratierbare Banlist) auch. Als Nächstes: Banlist-Hand-Review + auto-antislop-DE-Fork.

## Phase 8 — Modal: das Konto wackelt, das Skelett steht

Zuerst die SDK-Syntax aus dem Plan gegen die installierte Modal 1.4.2 verifiziert — der eine offene
Risiko-Punkt aus dem Handoff. Alles aktuell (`@app.function`, `Image`, `Volume.from_name`,
`Secret.from_name`). Mitten im Aufsetzen kippte der Modal-Token serverseitig („Token not found") —
zu Session-Beginn lief er noch. Kein Drama, `modal token set`, weiter. HF-Account gab es noch nicht;
Phil hat ihn angelegt (`PhilflowIO`), gated-Lizenz für `gemma-3-12b-it` akzeptiert, Token gesetzt.

Wichtige Architektur-Lehre beim ersten echten `modal run`: das Skelett baute zuerst ein schweres
vLLM-Image — und **`modal run` baut die Images ALLER registrierten Functions**, nicht lazy pro Aufruf.
Dazu zog `auto-antislop` `flash-attn` (kompiliert gegen nvcc, `debian_slim` hat nur die CUDA-Runtime),
und ungepinntes torch floatete auf 2.11+cu130 ohne Prebuilt-Wheel → Build-Bruch. Wurzel-Fix statt
Pflaster: das `preflight` braucht weder vLLM noch CUDA, nur `huggingface_hub`. Also ein leichtes
CPU-Image fürs Skelett, der echte GPU-Stack als Spec-Kommentar zu Schritt 2 verschoben. Danach
`preflight` grün gegen Modal: HF-Token, gated-Zugang, Volume — alles bestätigt.

## Phase 9 — Der Use-Case wird scharf: deutsche Website-Copy

Bevor wir Prompts bauten, die eigentliche Frage geklärt: *in welchem Register soll das Modell
schreiben?* **Phil: Website-Texte.** Raven als Flaggschiff-Beispiel, Fakten aus dem Vault
(`app-arch-flow-raven-paper`). Er präzisierte den Raven-Agent zweimal, bis es stimmte: nicht nur
„kennt die Gespräche zur Person", sondern *erst alle Meetings finden, in denen die Person vorkam,
dann im Transkript die Stelle, dann mit Beleg zusammenfassen.* Genau so in den Brief.

Eine echte Sorge von ihm dazwischen: *„sehen die Leute beim HF-Upload meine 1000 Prompts?"* Nein —
ein Modell-Repo enthält Gewichte + config + README, nicht die Prompts. Und Website-Copy ist per
Definition öffentlich; echte Geschäftsdaten kommen nie in einen Prompt. Beruhigt, weiter.

Design-Entscheidung mit Begründung: Aufgabe konstant („schreib Website-Text"), **Subjekt breit
gestreut** — sonst würden die Themenwörter eines einzelnen Subjekts gegen die Baseline
über-repräsentiert. 15 Branchen × 12 Copy-Typen × 4 Töne = 1472 Prompts.

## Phase 10 — Smoke fängt drei Boilerplate-Klassen

Erst 20 Samples über DeepInfra-gemma, bevor wir skalieren. Smoke-first zahlte sich sofort aus:
- **Vorrede:** gemma stellte jeder Antwort „Absolut! Hier ist ein Entwurf…" + Selbstkommentar voran.
  Verseucht das Profil wie die Untertitel-Credits in Stufe 0. Fix: System-Prompt verlangt nur den Text.
- **Eigennamen-Flut:** der Emergent-Diff flaggte `kanzlei vogt`, `lingua online` als „Slop". Fix:
  Eigennamen-Stoplist.

## Phase 11 — „Wogegen messen wir?" — der Branchen-Spread-Trick

Nach den Fixes flaggte der Diff immer noch Raven-Fachvokabular (`meeting raum`, `crm sync`). Ich
rahmte das erst falsch als „gemma papageit Fakten". **Phils Korrektur traf den Kern: „das sind ja
Fachbegriffe die richtig sind und rein müssen — ich weiß bloß nicht wogegen wir messen."** Genau da
lag der Knoten. Wir messen gegen die Stufe-0-Baseline — ein dialogisch/literarisches Lineal, das
kein Marketing-/Produkt-Register kennt. Also sieht es korrekte Fachbegriffe *genauso* wie Slop. Das
Lineal kann die zwei nicht trennen; der Mensch kann es (Paechs Hand-Banlist-Disziplin).

Daraus der eigentliche Durchbruch: **der echte Slop-Diskriminator ist nicht „fehlt in der Baseline",
sondern Branchen-Spread.** Eine Floskel taucht in vielen der 15 Branchen auf, ein Fachbegriff nur in
einer. Das ist berechenbar. Plus: Raven aus dem Profiling genommen (es ist der Anwendungsfall, nicht
der Slop-Treibstoff) — Set 1472 → 1380.

## Phase 12 — Voller Lauf, kuratierbare Banlist

1380 Generierungen über DeepInfra. Spread-sortiert fielen 371 Kandidaten heraus, vor-markiert: 93
`slop?` / 250 `strike` / 28 `review`. Der cross-cutting Slop steht sauber oben — „legen größten
wert", „auf Bedürfnisse zugeschnitten", „freuen darauf kennenzulernen", „maßgeschneiderte lösungen",
„mit rat und tat zur seite". Die Domänenbegriffe (`bio baumwolle`, `manuelle therapie`) sind als
`strike` markiert. Phils Hand-Review schrumpft damit von 30 auf 5 Minuten.

Eine Lach-Pause am Rand: **Phil: „ER HAT EINEN DE FORK?"** — Missverständnis. Nein, Paech hat keinen
deutschen Fork. `auto-antislop` ist Englisch-only; *wir* bauen den deutschen. Genau dafür das Projekt.

## Was Session 2 gelernt hat

- **`modal run` baut alle Function-Images** (nicht lazy). Schweres GPU-Image gehört nicht an ein
  leichtes Control-Plane-`preflight`.
- **Smoke-first, schon wieder.** Vorrede-Boilerplate, Eigennamen-Flut, Domänen-Vokabular — alles erst
  im Output sichtbar, nie in der Annahme.
- **Das Lineal entscheidet, was als Slop zählt.** Die dialogische Baseline kann Marketing-Fachbegriffe
  nicht von Floskeln trennen — Branchen-Spread kann es, Hand-Review ist das Netz.
- **Phils Korrektur schlägt mein Framing.** „Wogegen messen wir?" hat den Spread-Trick erst ausgelöst.

## Artefakte (Stufe 1 + Schritt 2)

- `modal_app.py` — Modal-Skelett, `preflight` grün (Token/gated/Volume), GPU-Stack als Schritt-2-Spec
- `configs/copy_prompts/{subjects_de,copy_types_de}.json` — 15 Branchen (+ Raven `profiling:false`) × 12 Typen
- `scripts/build_prompts.py` — Prompt-Grid → `data/prompts_de.jsonl` (1380, gitignored)
- `scripts/generate_samples.py` — DeepInfra-Generierung + Seed-/Emergent-Messung (Token nur Env)
- `scripts/build_banlist.py` — Spread-sortierte `data/banlist_candidates.tsv` (vor-markiert)
- `HANDOFF-STUFE-1-MODAL.md`, `HANDOFF-STUFE-2-AUTOANTISLOP.md` — selbsttragende Übergaben

## Commits (Session 2)

PRs #5–#6 Modal-Infra · #8 Prompt-Generator · #9 Smoke-Runner · #10 Raven aus Profiling · #11 voller
Lauf + Spread-Banlist · #12 Stufe-2-Handoff.

## Als Nächstes (Stufe 2, neue Session)

Phils Hand-Review von `data/banlist_candidates.tsv` → kuratierte Banlist in die Config. Dann der
**auto-antislop-DE-Fork**: forken, auf Deutsch patchen (`ngram_language`, DE-Stopwords, `wordfreq de`,
`human_profile_path` auf unser Profil, englische Banlist leeren, unsere Prompts/Banlist rein), den
GPU-Image-Stack lösen (CUDA-devel oder gepinntes torch/vllm/flash-attn), dann FTPO-Training und die
De-Risking-Leiter Smoke → Kalibrierung → Voll. Details: `HANDOFF-STUFE-2-AUTOANTISLOP.md`.

---

# Session 3 — auto-antislop wird deutsch, und der erste grüne FTPO-Lauf

**Stand:** 2026-06-08, dritte Bau-Session (über die Nacht). Aus dem englisch-verdrahteten
`auto-antislop` wurde der deutsche, und der **komplette FTPO-Pfad lief zum ersten Mal end-to-end auf
Modal-H100 grün** — gemma-3-12b-it hat ein deutsches Anti-Slop-LoRA bekommen, das messbar gelernt hat.

## Phase 13 — Kuratierung: Phil entscheidet die Grenzfälle

`banlist_candidates.tsv` war nicht kuratiert — der rohe `build_banlist.py`-Output (93 `slop?` / 250
`strike` / 28 `review`). Also die 28 Grenzfälle vor-sortiert, je ein Vorschlag keep/strike mit
einer Zeile Begründung, und drei Wackelkandidaten markiert (`gesundheit wohlbefinden`, `persönliche
atmosphäre`, `hochwertige materialien`). Phils Urteil war knapp und richtig: **„wirklich funktionieren
ist definitiv slop. Die sagen immer wirklich und echt."** Genau — der leere Intensifier ist ein Tell.
Die drei Wackelkandidaten: alle raus. Fünf echte Behalter (`seit generationen`, `geschichte erzählen`,
`mittelständische unternehmen`, `gut aussieht`, `komm vorbei`) — baseline-belegt, lebendiges Deutsch.

Ergebnis: 116 kuratierte Slop-Ngrams als `extra_ngrams_to_ban` in `configs/de_extra_bans.json`,
getrennt von den 38 hand-gesetzten Surface-Seeds (Issue #13, PR #15).

## Phase 14 — Vendoren statt Forken

Erst die echte Architektur-Entscheidung: wo lebt der DE-Fork? **Phil fragte zurück: „was sind die
unterschiede?"** — und das war die richtige Frage. GitHub-Fork = Upstream-Sync per PR, aber zwei Repos
und Patches außerhalb. Vendoren = self-contained, ein teurer GPU-Lauf garantiert reproduzierbar, alle
Patches im selben `git log`. Für ein Projekt, dessen Daseinszweck ein nachvollziehbares Artefakt ist,
gewann Reproduzierbarkeit. **Vendoren.**

`auto-antislop` + die zwei Submodule (`antislop-vllm`, `slop-forensics`) flach reinkopiert, von 108 MB
auf 1,1 MB abgespeckt (die zwei englischen 51-/29-MB-Beispielprofile raus — wir nutzen unser DE-Profil).
Die Patch-Punkte gegen den echten HEAD verifiziert (alle Handoff-Zeilennummern stimmten): `ngram_language
→ german`, NLTK-Stopwords `→ german`, `wordfreq → de`, `human_profile_path → /cache`-Volume, `model_id →
gemma-3-12b-it`. Eine Vereinfachung fiel dabei auf: **die Kern-Banlist ist laufzeit-generiert aus dem
Profil-Diff** — durch DE-Profil + `german` wird sie automatisch deutsch, nur die statischen `extra_*`-
Listen mussten getauscht werden. Provenance in `vendor/PATCHES-DE.md` (Issue #16, PR #17).

## Phase 15 — Zwei Generierungs-Schritte, und warum Modal-GPU erzwungen ist

Eine Verwechslung aufgelöst, die im Handoff schlummerte: `auto-antislop` generiert **zweimal**. Schritt 1
(Banlist-Bau, plain Generierung → Diff) haben wir auf DeepInfra schon vorweggenommen. Schritt 2
(FTPO-Paare) braucht den **antislop-Sampler mit Backtracking** — Slop-Token rejected, Alternative chosen
— und das kann DeepInfra nicht. Also ist Modal-GPU für die FTPO-Paare methodisch erzwungen, keine Wahl.

Die Prompts-Brücke löste sich ohne HF-Push: `antislop-vllm` kann nativ `--input-json` (lokale String-
Liste), `orchestration.py` patcht `generation_input_json → --input-json`. Plus DE-Prompt-Template und
deutscher System-Prompt. GPU-Image: CUDA-12.6-devel (hat nvcc) — Phils Entscheidung.

## Phase 16 — Der Build-Drift: rope, vision-tower, flash-attn

Hier wurde es ehrlich. „Knallgas" hieß: den Smoke fahren. Der Smoke kam **nicht** auf Anhieb — er stieg
eine Leiter von Versions-Konflikten hinab, jeder nach einem ~Image-Build sichtbar:
- **rope_scaling-Crash:** ungepinntes `transformers` floatete auf 5.x, das gemma-3s globales
  `rope_scaling` durch per-Layer `rope_parameters` ersetzt — vLLM 0.10.2 kennt das nicht. Fix:
  `vllm==0.11.0 + transformers==4.56.2` (gemma-3 nativ).
- **Vision-Tower / flash-attn-Cap:** gemma-3 ist multimodal; vLLM lud den SigLIP-Tower über xformers,
  das flash-attn ≤2.8.2 verlangte. Erst 2.8.2 gepinnt — aber 2.8.2 hat **kein** torch2.8-Prebuilt-Wheel,
  also Source-Compile, der nach 45 Min (alle 73 nvcc-Objekte) am Link scheiterte: `clang++ not found`.
  Der saubere Fix kam über eine Einsicht: **vLLM 0.11.0 nutzt für den ViT-Pfad sein gebündeltes
  `vllm_flash_attn`** — der externe Cap entfällt, also das schnelle 2.8.3-Prebuilt-Wheel. Build von
  45 Min auf Sekunden.

## Phase 17 — Die trl-Kette: sechs Mal dasselbe

Hinter dem Build-Gate lief die **gesamte deutsche Generierungs-/Profiling-/Banlist-Strecke grün** —
und scheiterte dann an der FTPO-Trainings-Stufe. Nicht an einem Blocker, sondern an einer **Kette von
sechs gleichartigen trl-API-Drifts** (trl 0.20 → 0.29.1, erzwungen durch den vllm/transformers-Pin):
`ORPOTrainer`-Import weg → `DPOConfig.max_prompt_length` weg → pad-id-Feld umbenannt →
`null_ref_context` weg → `store_metrics` weg. Plus das **vorhergesagte** gemma-3-Modellklassen-Problem:
es ist `Gemma3ForConditionalGeneration`, nicht im CausalLM-Auto-Mapping → Loader auf
`AutoModelForImageTextToText` umgestellt.

Die Root-Cause-Frage war echt: trl downgraden oder den Code patchen? **Downgrade hätte transformers
< 4.50 verlangt und das vLLM-Triple gesprengt** — also Code-Patch, defensiv und cross-version. Der
zwischenzeitlich erwogene Zwei-Image-Split (Generierung vs. Training getrennt) war damit unnötig; die
In-One-Image-Anpassung trägt. Jeder Lauf kam einen Schritt weiter — das war Konvergenz, kein Stochern.

**Ehrlich zum Prozess:** Das lief zeitweise aus dem Ruder. Mehrere parallele Smoke-Läufe aus zwei
Claude-Sessions auf **einem** lokalen Branch, dazu Hintergrund-Agents, die nach Turn-Ende noch
weiter-narrierten — Log-Cross-Contamination (ein `EXIT=0` aus einem fremden Lauf täuschte kurz
Erfolg vor), konkurrierende Image-Builds, Doppelarbeit. Es führte zum Ziel, aber die Lehre steht:
für den teuren vollen Lauf **ein** Lauf, **ein** Treiber.

## Phase 18 — Grün: das LoRA lernt, deutsch zu schreiben

`run_20260608_002001`: das FTPO-Training lief durch und **lernte messbar** — `chosen_win` 0,12 → 0,54,
`pref_loss` 7,43 → 3,23, `mean_delta` −5,13 → +0,31 über 14 Steps. Im Volume liegen `lora_adapters/`,
`merged_16bit/` (5 fp16-Shards, gemma-3-Merge korrekt geshardet), `checkpoint-14/`, TensorBoard —
unabhängig per `modal volume ls` verifiziert. Der Antislop-Effekt schon in der Generierung sichtbar:
Diversität (TTR) 0,24 → 0,43, Wiederholung 3277 → 1868 /100k zwischen den Iterationen.

Und der eigentliche Beweis, dreifach bestätigt: **die generierte DE-Banlist ist sauberes Deutsch**,
0 von 1106 echte Englisch-Treffer, german-Tokenizer + `wordfreq de` nachweislich aktiv. Wörtlich:
`perfekte abdichtung`, `namhaften hersteller`, `sorgfältige ausführung`, `Als traditionsreiches
Familienunternehmen`, `Dach in besten Händen`. Genau der Werbetexter-Nominalstil, den wir jagen.

## Was Session 3 gelernt hat — auch über uns

- **Die Kern-These steht:** Die deutsche Anti-Slop-Maschinerie funktioniert end-to-end. gemma generiert
  dt. Copy, der Sampler bannt Slop live, unsere Banlist greift, das LoRA verlernt den Slop messbar.
- **Es war eine Versions-Kohärenz-Kette, kein Logik-Problem.** Acht Drifts (zwei Image, sechs trl) plus
  das Modellklassen-Problem. Code-Patch über Downgrade — sonst zerbricht das vLLM-Triple.
- **`returncode 0` lügt.** `main.py` schluckt Finetune-Exceptions und exitet 0; der echte Beleg ist der
  gespeicherte Adapter im Volume, nicht der Exit-Code. Wir haben uns davon fast täuschen lassen.
- **Smoke-first, ein drittes Mal.** Jeder Blocker zeigte sich erst zur Laufzeit, nie in der Annahme.
- **Agent-Orchestrierung braucht Disziplin.** Viele Hintergrund-Agents + zwei Sessions auf einem Branch
  ist Chaos. Konvergiert hat es trotzdem — aber teurer als nötig.

## Artefakte (Stufe 2)

- `vendor/auto-antislop/` — DE-gepatchter, eingefrorener auto-antislop-Stand (+ `vendor/PATCHES-DE.md`)
- `configs/de_extra_bans.json` — 116 kuratierte DE-Slop-Ngrams + 38 Surface-Seeds
- `modal_app.py` — GPU-Image (CUDA-12.6-devel, torch 2.8 / vllm 0.11 / flash-attn 2.8.3-Wheel),
  End-to-End `run_pipeline` + `smoke`-Entrypoint
- Modal-Volume `antislop-de-vol/auto_antislop_runs/run_20260608_002001/` — das erste DE-FTPO-LoRA

## Commits (Session 3)

PR #15 Banlist-Kuratierung (#13) · PR #17 Vendoring + DE-Patches (#16) · Branch `feat/modal-ftpo-run`
(12 Commits): Image-Pins (vllm/transformers/flash-attn) + 6× trl-cross-version + gemma-3-Loader → diese PR.

## Als Nächstes (der volle Lauf)

**Ein** voller Lauf (1380 Prompts, ~12-32 $, Phils Go) statt der 20-Prompt-Smoke — erst dann ist die
emergente Banlist branchen-breit statt Dachdecker-lastig. Dann Eval: DE-Slop-Score, lexikalische
Diversität, struktureller Slop (`eval/structural_slop.py`), GSM8K/MMLU-Spotcheck, Pangram, und Phils
Augenschein an echter Raven-Copy. Bei Bestehen: Merge + privater HF-Upload
`PhilflowIO/gemma-3-12b-it-antislop-de`.

---

# Session 4 — Der volle Lauf, die Eyeball-Eval, und ein selbstverschuldeter Datenverlust

**2026-06-08.** Vom selbsttragenden Handoff (`HANDOFF-STUFE-3-VOLLER-LAUF.md`) zum fertig
trainierten, am Augenschein bestätigten DE-Anti-Slop-Modell — plus eine Lektion über git, Symlinks
und Worktrees, die wir nicht freiwillig gelernt haben.

## Phase 19 — Der volle Lauf, und ein ehrlich gemachter Parameter

Vor dem Zünden ein Root-Cause-Detail aus dem Handoff aufgegriffen: `run_pipeline` nahm einen
`max_train_examples`-Parameter entgegen, reichte ihn aber nie an `main.py` durch — die Trainings-Menge
war nur über eine stille config-Mutation steuerbar. Statt die config zu kippen: `--finetune-max-train-examples`
als Flag in der vendored `main.py` ergänzt (ein Einzeiler — `merge_config_with_cli_args` greift jeden
`_FINETUNE`-Key über den dest-Namen automatisch ab) und in `run_pipeline` durchgereicht. Der vestigiale
Parameter ist jetzt ehrlich (PR #21, Issue #20).

Dann **ein** Lauf, **ein** Treiber (die Session-3-Lehre): `smoke --max-prompts 1380 --max-train-examples
10000`. Vorab alles grün geprüft — Modal-Auth lebt, gemma im Volume gecacht (der teure 24-GB-Pull
entfällt), 1380 Prompts lokal. ~2 h H100, **~8-9 $** (deutlich unter der 12-32-$-Schätzung, weil gemma
gecacht war). **Stark gelernt:** `chosen_win` 0,69 → 0,86 (Early-Stop bei ≥0,85, gegenüber 0,54 im Smoke),
`pref_loss` ~1,58 → 0,75. Artefakt im Volume verifiziert — nicht der Exit-Code: `run_20260608_061845/.../merged_16bit`
(5 fp16-Shards) + `lora_adapters/`. Fußnote: 10k war ein Cap, real genutzt wurden nach Quota-Sampling
**3778 FTPO-Rows** — die 1380 Prompts geben nicht mehr her; mehr Trainingsdaten hieße mehr Prompts, nicht
ein höheres Cap.

## Phase 20 — Eyeball zuerst: Phils Auge schlägt die grüne Zahl

Phil wählte bewusst „Augenschein zuerst, dann die Metrik-Leiter" (sein Gut-Check-Prinzip). Eval-Tooling
gebaut (PR #23, Issue #22): `build_eval_prompts.py` zieht 8 stratifizierte **Raven**-Prompts;
`eval_generate`/`eval_compare` laden Baseline + FTPO sequentiell (transformers, gleicher Seed je Prompt für
faire Sampling-Bedingung). Glücksfund: **Raven ist `profiling:false`** (`build_prompts.py:51-52`), war also
nie im Trainings-Grid — ein ungeleakter Holdout, der zugleich der Anwendungsfall ist.

Das automatische Maß war eindeutig: Slop-Phrasen-Treffer (emergente Banlist) **66 → 8 (88 % ↓)**, jede
Sektion runter, FAQ 20 → 0. Aber genau hier griff Phils Auge: die FTPO-Texte hatten Fluss-Patzer —
kaputter Kasus, du/Sie-Mix, die erfundene Vokabel „Künstlermodell" statt KI-Modell. Die grüne 66 → 8 hätte
das verschwiegen. **Das Prinzip „Gut-Check über grüne Metriken" hat sich konkret bestätigt.**

## Phase 21 — Der Trenn-Test: Sampling-Rauschen, kein Trainings-Schaden

War der Push zu hart (FTPO-Defekt) oder nur das heiße Sampling? `--temperature`-Schalter ergänzt, denselben
Holdout bei temp 0.7 gefahren (temp 1.0 ist die *Trainings*-Temperatur — zu heiß für Inferenz). Ergebnis:
Slop bleibt unten (**61 → 11, 82 % ↓** — robust über Temperaturen), und **alle vier Patzer verschwinden**.
Verdikt: das Modell ist fluent *und* entslopt bei Inferenz-temp ~0,7. Register du/Sie ist kein Defekt — das
Modell folgt dem Ton-Hint; für Raven pinnt man `du` im System-Prompt.

## Phase 22 — Der Datenverlust: ein Symlink, den git nicht ignorierte

Beim Aufräumen explodierte ein selbstverschuldeter Fehler. Um die gitignorten `data/`-Dateien in den
Eval-Worktree zu speisen, hatte ich einen Symlink `data` → Haupt-Checkout angelegt. `git add -A` **trackte
den Symlink**, weil `.gitignore`-`data/` Verzeichnis-*Inhalte* ignoriert, aber keinen *Symlink namens* `data`.
Committet, gemerged — und beim `pull` in den Haupt-Checkout überschrieb der ausgecheckte Symlink das echte
`data/` mit einer selbst-referenziellen Schleife. Lokale (nie-in-git) Arbeitsdaten weg.

Sauber behoben (Issue #24, PR #25): Symlink untracked, `.gitignore` um `/data` (ohne Slash) gehärtet.
Wiederhergestellt aus dem Modal-Volume: das 51-MB-Baseline-Profil, Prompts, beide Eval-JSONs, Banlists;
`prompts_de.jsonl` kam byte-identisch durch deterministische Regeneration zurück. Endgültig verloren — nur
Stufe-0-Roh-Intermediate ohne Zweitkopie (`samples_*.jsonl`, `raw/`, die `banlist_*.tsv`-Kandidaten); ihre
kuratierten Outputs (`configs/de_extra_bans.json`, das Profil) waren sicher.

## Was Session 4 gelernt hat

- **Die Kern-These ist jetzt validiert, nicht nur lauffähig:** Der volle Lauf entslopt echte deutsche Copy
  messbar (88 %) *und* — am Auge bestätigt — überzeugend, ohne den Inhalt zu verlieren.
- **Phils Augenschein > grüne Metrik, konkret belegt.** Die 66 → 8 sah perfekt aus; das Auge fand die
  Fluss-Defekte, die kein n-gram-Score misst. Die billige Diagnose (temp 0.7) trennte Ursache von Rauschen.
- **Trainings-temp ≠ Inferenz-temp.** temp 1.0 ist fürs Slop-Emergieren beim Training richtig, fürs
  Ausliefern zu heiß. Default ~0,7 mitgeben.
- **`data/` ≠ `/data` in gitignore.** Trailing-Slash ignoriert Verzeichnis-Inhalte, nicht einen
  gleichnamigen Symlink/File. Nie `git add -A` in einem Worktree mit Symlink in einen anderen Checkout;
  große Arbeitsdaten off-disk wiederherstellbar halten (das Volume hat uns gerettet).

## Artefakte (Stufe 3)

- Modal-Volume `antislop-de-vol/auto_antislop_runs/run_20260608_061845/` — das volle DE-FTPO-LoRA
  (`merged_16bit/` 5 Shards, `lora_adapters/`, emergente `banned_*.json`)
- `scripts/build_eval_prompts.py` — Raven-Holdout-Prompts
- `modal_app.py::eval_generate` / `eval_compare` — Baseline-vs-FTPO mit `--temperature`-Schalter
- `data/eval_raven_compare{,_t0.7}.json` + `.md` — die Side-by-side-Belege (lokal, gitignored)

## Commits (Session 4)

PR #21 ehrlicher `--finetune-max-train-examples`-CLI-Override (#20) · PR #23 Eval-Generierung + Temperatur-
Schalter (#22) · PR #25 Symlink-Datenverlust-Fix + gitignore-Härtung (#24).

## Als Nächstes (Eval-Leiter zu Ende, dann Upload)

Augenschein-Rung bestanden. Offen, alle ohne weitere GPU-Kosten außer Pangram: struktureller Slop
(`eval/structural_slop.py`, spaCy) auf dem Holdout, TTR/RTTR, Capability-Spotcheck (GSM8K/MMLU — der
FTPO-Witz: Slop weg *ohne* Fähigkeits-Verlust, noch ungemessen), dann Pangram (~10-25 $, nur Schluss-
Kontrolle) + Phils breiterer Augenschein. Bei Bestehen: HF-Upload privat `PhilflowIO/gemma-3-12b-it-antislop-de`
(nur Gewichte + config + README), Inferenz-temp ~0,7 als Default dokumentiert.

---

# Session 5 — v1 ehrlich zerlegt, v2 gebaut, die strukturelle Decke gefunden

**2026-06-08/09.** Diese Session begann mit „v1 ist evaluiert, mach den billigen Inferenz-Fix" und
endete mit einem voll neu trainierten v2, einem privaten HF-Upload — und der wichtigsten Lehre des
ganzen Projekts: Anti-Slop per fester Banlist hat eine strukturelle Decke. Der rote Faden war ein
einziger Fehler, viermal wiederholt: **der grünen Metrik geglaubt, statt zu lesen.**

## Phase 23 — Der Inferenz-Fix, der eine Scheinwahrheit verkaufte

Schritt 1 aus dem Handoff: `repetition_penalty` + `max_new_tokens`-Cap gegen die „inklusive…inklusive"-
Run-ons (PR #39, Issue #38, fair auf beide Modelle). Breiter Lauf @ temp 0.7, rep 1.2: die Metriken sahen
stark aus — Struktur-Slop 86→54, Run-ons 3→1. Ich meldete „Flanke geschlossen". **Phil las die Demo und
fand, was die Zahl verbarg:** „draufgenommen" statt „aufgenommen", „Meeting-Workflow", und — der grobe
Schnitzer — die erfundene Positionierung „heimliche Bots, die kaum jemand merkt". Erste Lektion: mein
„3→1 Run-ons" war falsch; der Degeneracy-Detektor (Satzlänge + Nomen/Verb) hatte eine katastrophale
„gilt gilt gilt"-Schleife komplett übersehen, weil die n/v-Ratio bei Verb-Spam *niedrig* ist.

## Phase 24 — „hast du die Demo mal durch Spezialisten prüfen lassen?"

Hatte ich nicht. Drei read-only Spezialisten mit orthogonalen Frames (Sprache, Faktentreue, Slop),
Evidence-Pflicht (id + Zitat). Zwei von drei: **FAIL.** Der entscheidende Befund kam vom Slop-Kritiker:
das v1-Modell hatte Slop nicht entfernt, sondern **umverteilt** — „inklusive" 14→558, „kristallklar"
2→21. (Korrektur vom 2026-09-04: in der Ursprungsfassung dieser Session standen hier 78 und 13. Das war
ein Messfehler. Nachgezählt über alle 36 Texte je Arm in `data/eval_raven_compare_broad_t0.7_v1.json`,
Substring ohne Groß-/Kleinschreibung, ergibt sich 558 bzw. 21.) Meine Banlist-Metrik (3,75/1k) war blind
dafür, weil sie nur die *Vor-Training*-Banlist zählte.
Und die Falsch-Positionierung steckte in unserem eigenen Eval-Brief (`subjects_de.json:16`) — das Modell
folgte ihr nur. Root-Cause des Kollapses dann lokalisiert: der Lauf nutzte den generischen Default-Config
statt Paechs gemma-Rezept — doppelte Lernrate (0,15 statt 0,08), alle 8 Module inkl. `lm_head`, Early-Stop
erst bei 0,86 (Autor: „>0,85 may be overtrained"). Das LoRA war überpresst; der Scale-down-Test (Adapter
bei 0,5/0,7 gemergt) bestätigte es: bei 0,7 war die Kohärenz zurück.

## Phase 25 — v2: das sanfte Rezept, vier Fixes

PR #43 (Issue #42): lr-scaling 0,15→0,08, Module nur `up/down/lm_head`, Early-Stop 0,78; die emergenten
Tics in die Banlist (Phil strich seine guten Wörter wieder raus — „kristallklar, ruckzuck, kinderleicht
sind doch gut"); der Raven-Brief auf die echte Passiv→Aktiv-Positionierung gefixt; die Eval-Metrik um eine
Tic-Frequenz-Messung gehärtet. v2-Lauf (`run_20260609_140022`): ThresholdStop bei **chosen_win 0,7874** —
sauber vor der Überpress-Linie, genau wie geplant.

## Phase 26 — v2 evaluiert: der Sprung, und die Decke

Diesmal zuerst gelesen, dann die drei Spezialisten (mit v1-Kontext für den Delta):
- **Positionierung PASS:** „unsichtbar"-Falschframe 20/36 → **0/36**, Passiv→Aktiv-Differentiator ~0 → **30/36**.
  Der Brief-Fix wirkte vollständig.
- **Worst-Case behoben:** 6 Kollapse + 1 Satzabbruch → **0**. Keine Phantasiewörter mehr.
- **Sprache mixed:** 19/36 streng sauber — Feinschliff nicht besser (neuer Kasus-Tic „plant deinen Meetings").
- **Slop mixed→fail:** „inklusive" gegenüber der eigenen Baseline 9→39 (Banlist wirkte; v1 lag bei 558),
  aber das Modell wich auf **„maximal" 1→59** aus. (Zahlen 2026-09-04 nachgerechnet, siehe Korrektur in Phase 24.)

Und da war sie, die Decke: **Whac-a-Mole ist strukturell.** FTPO + feste Banlist bändigt Tic N, das Modell
züchtet Tic N+1. inklusive→maximal. Die feste Tic-Metrik verpasste „maximal", weil es nicht auf der Liste
stand — **viertes Mal, dass die Metrik einen Schritt hinterher war.** Der einzige Weg, das zu durchbrechen,
wäre ein dynamisches Frequenz-Anomalie-Ziel statt einer Banlist — ein Redesign, kein weiterer Lauf.

## Phase 27 — Entscheidung: v2 einbanken

**Phil: „v2 als bestes Modell nehmen."** Richtig — v2 behebt die zwei v1-Killer (Positionierung, Kollapse),
ist der praktische Sieger, und Banlist-Iteration hätte nur Tic #3 gezüchtet. Privater HF-Upload
`PhilflowIO/gemma-3-12b-it-antislop-de` (PR #45, Issue #44): nur Gewichte+config+tokenizer + eine ehrliche
Model-Card, die die Limitierungen benennt. Default-Inferenz temp 0,7. Brauchbare Copy als Entwurf mit
Human-Edit — nicht slopfrei, aber spürbar menschlicher, mit korrekter Positionierung.

## Was Session 5 gelernt hat

- **Die grüne Metrik verbirgt, was sie nicht kennt.** Viermal: Phrasen-Slop-Score, Run-on-Detektor,
  Scale-Tic-Metrik, v2-Tic-Metrik — jedes Mal sah die Zahl gut aus, das Lesen fand den echten Defekt.
  Konsequenz fest verdrahtet: **Independent Review + Eigenlesung VOR dem Verdikt, nicht danach.**
- **Whac-a-Mole ist die strukturelle Grenze des Banlist-Ansatzes.** Ein ausweichendes Modell holt eine
  feste Liste nie ein. Echter Fix wäre ein dynamisches Anomalie-Ziel.
  **Nachtrag 2026-09-04:** diese Erklärung war zu bequem. Session 6 hat die banalere Ursache gefunden,
  einen Filter im Upstream-Framework, der berechnet und geloggt, aber nie angewendet wird. Siehe
  [Session 6](#session-6--was-wirklich-schiefging-und-der-nachgeholte-kontrollarm), Befund 1.
- **`returncode 0` lügt — schon wieder.** Der erste v2-Eval-Lauf „exit 0", aber ein `grep`-Filter hatte
  den echten Fehler (fehlende Broad-Prompts) verschluckt; der zweite scheiterte sichtbar daran.
- **Phils Augenschein hat den ganzen Kurs gedreht** — dreimal („wirkt komisch", „durch Spezialisten?",
  „die Wörter sind doch gut"). Sein Maßstab schlug jede Zahl, die ich ihm vorlegte.

## Commits (Session 5)

PR #39 rep_penalty/max_new_tokens (#38) · PR #41 LoRA-Scale-down + Token-Schleifen-Detektor (#40) ·
PR #43 v2-Prep: sanftes Rezept + Tic-Banlist + Brief-Fix + Tic-Metrik (#42) · PR #45 v2 final + privater
HF-Upload + Model-Card + diese JOURNEY-Session (#44). v2-Lauf: `run_20260609_140022` (chosen_win 0,7874).

---

# Session 6 — Was wirklich schiefging, und der nachgeholte Kontrollarm

**2026-09-04.** Diese Session hat nichts trainiert. Sie hat nachgesehen. Ergebnis: die Erklärung aus
Session 5 war falsch, die Hauptzahl des Projekts war zirkulär, und der billigste Vergleichsarm, den es
gebraucht hätte, existierte nur als Dateiname.

## Phase 28 — Der Anlass: drei Gutachter, drei Frames, dreimal fail

Beim Schreiben des vierten Blogteils wurden Methodik und Artefakte noch einmal geprüft. Drei Gutachter
in getrennten Frames: Trainingsrezept, Messdesign, Slop-Definition. Alle drei kamen auf **fail**, jeder
aus einem anderen Grund. Das ist der Unterschied zu Session 5, wo drei Spezialisten dasselbe Artefakt
mit ähnlichem Blick lasen.

## Phase 29 — Befund 1: die tote Bremse

Der Ausweich-Tic war nicht emergent. Er wurde antrainiert.

Im Trainingslog (`fullrun.log`, Eintrag `[ftpo-loader] ORIGINAL CHOSEN TOKENS`) steht `' inklusive':218`.
Das Wort war 218 Mal die bevorzugte Alternative im Trainingsmaterial. Das Framework berechnet dagegen
selbst eine Obergrenze und loggt sie als `CHOSEN TARGET QUOTAS` mit `' inklusive':93`. Angewendet wird
sie nie: `tgt_chosen` entsteht in `vendor/auto-antislop/utils/dataset_helpers.py:127` und taucht danach
nur noch in den Zeilen 131, 136 und 137 auf, alle drei Logging. Keine Zeile wird damit gefiltert.

Das ist ein Fehler im Upstream-Framework `auto-antislop`, nicht im eigenen Code. Wir haben ihn ein Jahr
lang nicht gesehen, weil wir ihn für eine Eigenschaft des Modells hielten.

## Phase 30 — Befund 2: die Messung war zirkulär und ist weg

Die 92 Prozent Reduktion wurden gegen dieselbe Banlist gemessen, gegen die trainiert wurde. Die Zahl
beweist damit nur, dass das Training angekommen ist. Eine Nachrechnung mit demselben Code auf denselben
Dateien ergibt heute rund 66 Prozent. `data/eval_holdout_report.json` ist nicht versioniert und
auseinandergedriftet, die ursprüngliche Zahl also nicht mehr nachprüfbar.

Dazu kein Validierungssplit: `vendor/auto-antislop/core/finetuning.py:829` übergibt nur `train_dataset`.
Gestoppt wurde auf dem Trainingssignal selbst.

## Phase 31 — Befund 3: die Konstruktlücke

Slop ist semantisch definiert, eine Eigenschaft von Aussagen. FTPO greift auf einem einzelnen Token. Von
den sechs Slop-Klassen, die wir unterschieden haben, erfasst das Verfahren zwei. Struktureller Slop wurde
zwar gemessen, aber nie als Trainingssignal verdrahtet, und er verschlechtert sich durch das Training:
Median 56,1 auf 63,8 im v2-Vergleich.

## Phase 32 — Befund 4: der Arm, den es nie gab

`data/eval_raven_compare_broad_t0.7_promptonly.json` enthielt nie einen Prompt-Durchlauf. Das Feld
`promptonly` ist in 36 von 36 Fällen byteidentisch mit dem Feld `baseline` derselben Datei. Die daraus
abgeleitete Behauptung in `configs/antislop_prompt.md` („bester in 30 von 36") war unbelegt.

## Phase 33 — Die Nachholung

Der Arm wurde neu generiert: nacktes `google/gemma-3-12b-it` über die DeepInfra-API, System-Prompt
wörtlich aus `configs/antislop_prompt.md`, dieselben 36 Prompts aus `data/eval_raven_prompts_broad.jsonl`,
temperature 0,7, seed 1234+idx. Ergebnis als
`data/eval_raven_compare_broad_t0.7_promptonly_rerun.json`, Gegenprobe 0 von 36 identisch mit der Baseline.

Objektive Messung der drei Arme:

| Arm | Banlist-Treffer /1k | Struktur-Slop, Median | „maximal" | „absolut" | „inklusive" |
|---|---|---|---|---|---|
| Baseline | 38,64 | 56,1 | 1 | 5 | 9 |
| Prompt-only | 19,20 | 57,3 | 0 | 1 | 7 |
| v2-Finetune | 12,04 | 63,8 | 59 | 55 | 39 |

Blinder Lesetest, zwei **LLM**-Gutachter, ausdrücklich keine Menschen, verdeckte Zuordnung, je bester und
schlechtester Text pro Prompt, n=36:

- Gutachter 1, Maßstab „liest sich das nach einem deutschen Werbetexter": Baseline 17 bester / 2
  schlechtester, Prompt-only 19 / 2, v2 **0 bester / 32 schlechtester**.
- Gutachter 2, Maßstab strikt die Slop-Definition: Baseline 1 / 1, Prompt-only **35 bester / 0
  schlechtester**, v2 **0 bester / 35 schlechtester**.
- Übereinstimmung beim schlechtesten Text: 31 von 36. Degeneration: Baseline 0/36, Prompt-only 0/36,
  v2 1/36.

Der Prompt schlägt den Finetune. Die Einordnung für Nachnutzer steht in der
[README](./README.md#das-hauptergebnis-der-prompt-schlägt-den-finetune), sie wird hier nicht wiederholt.

## Was Session 6 gelernt hat

- **Der billigste Kontrollarm gehört an den Anfang, nicht ans Ende.** Ein System-Prompt kostet nichts.
  Hätte er von Anfang an mitgelaufen, wäre das Projekt nach einer Woche beantwortet gewesen statt nach
  drei Monaten.
- **Eine Metrik, die aus dem Trainingsziel abgeleitet ist, beweist nur das Trainingsziel.** Trainings-
  und Eval-Banlist waren identisch. Alles, was wir gemessen haben, war die eigene Optimierung.
- **„Strukturelle Grenze" war eine bequeme Erklärung.** Sie klang tief genug, um das Nachsehen zu
  ersetzen. Darunter lag ein Filter, der berechnet und geloggt, aber nie angewendet wurde. Vier Zeilen
  Code.
- **Ein LLM-Judge ist ein schwacher Beweis.** Er wurde hier nur deshalb verwendet, weil ein Menschentest
  nicht stattgefunden hat. Das Ergebnis ist deutlich genug, um die Richtung zu tragen, aber es ersetzt
  keine menschliche Lesung.

## Commits (Session 6)

Branch `chore/public-release`: Serving-Pfad und Anti-Slop-Prompt aufgenommen, Apache-2.0 für den eigenen
Code, Upstream-Baum aus dem Index genommen, README auf das ehrliche Dreiwege-Ergebnis samt bekannter
Methodikfehler umgeschrieben, diese JOURNEY-Session.
