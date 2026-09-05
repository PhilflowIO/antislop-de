# Der Anti-Slop-Prompt — der eigentliche Deliverable

**Befund (2026-06-09):** Im blinden 3-Wege-Lesetest (n=36, LLM-Judge) schlug
`plain gemma-3-12b-it + dieser Prompt` sowohl den v1/v2-FTPO-Finetune als auch
die nackte Baseline — **bester in 30 von 36 Prompts**, der Finetune in **0/36**
bester und **32/36 schlechtester**. Kostenlos, kein Training, kein GPU.

Slop bei deutscher Website-Copy ist ein **Prompt-/Register-Problem**, kein
Gewichts-Problem. Nimm das, nicht das LoRA.

## System-Prompt

```
Du bist ein erfahrener deutscher Werbetexter. Gib ausschließlich den fertigen
Website-Text aus — keine Vorrede, keine Erklärung, keine Optionen. Schreibe knapp
und direkt in der Du-Form. Vermeide Marketing-Floskeln und leere Verstärker wie
'maximal', 'kristallklar', 'nahtlos', 'inklusive allem', 'souverän'. Keine
Doppelpunkt-Einleitungen, keine Adjektiv-Aufzählungen. Aktiv statt Passiv, kurze
Sätze, konkret sagen, was das Produkt tut.
```

## Inferenz

- Modell: `google/gemma-3-12b-it` (nackt, kein Finetune)
- `temperature=0.7`, Ton-/Register-Hinweis ("Duze die Leser durchgehend.") bei Bedarf anhängen.
- Produkt-Fakten faktentreu in den User-Prompt geben (siehe `configs/copy_prompts/subjects_de.json`) —
  sonst erfindet das Modell Positionierung (das war der „unsichtbare Bots"-Bug).

## Optionaler echter nächster Schritt (falls man die Decke knacken will)

Nicht weiter finetunen — **Multi-Amateur Contrastive Decoding**: gegen die Logits
eines absichtlich sloppy „Amateur"-Modells decodieren. Dynamisch, training-frei,
umgeht den Whac-a-Mole (inklusive→maximal), den eine feste Banlist nie einholt.
Belege + Begründung: JOURNEY.md Session 5, Issue #42.
