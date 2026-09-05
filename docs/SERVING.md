# Serving & Aufruf — antislop-de v2

Wie das trainierte v2-Modell gehostet und aufgerufen wird. Für das *Training* siehe
[`JOURNEY.md`](../JOURNEY.md) + [`modal_app.py`](../modal_app.py).

## Was läuft

- **Modell:** `PhilflowIO/gemma-3-12b-it-antislop-de` (privat, FTPO-Merge auf `gemma-3-12b-it`, 16bit).
  Nicht slopfrei, aber spürbar menschlicher — **Entwurf + Human-Edit**, so auch in der Model-Card.
- **Host:** Verda (ex-DataCrunch) Serverless-Container, **L40S 48 GB**, offizielles Image
  `vllm/vllm-openai:v0.11.0`, OpenAI-kompatibel.
- **Deployment-Name:** `antislop-de-v2` · **Endpoint:** `<VERDA_ENDPOINT>`
  Die Endpoint-URL ist deployment-spezifisch: sie entsteht beim Anlegen des Containers und
  steht in der Verda-Console. Sie gehört zusammen mit dem Inference API Key in eine lokale
  Env-Datei, nicht ins Repo.

## Aufrufen (der Normalfall)

```bash
source ~/.config/verda-antislop.env          # setzt VERDA_ENDPOINT + VERDA_API_KEY (chmod 600)
cd ~/Dokumente/coding/antislop-de

# Subjekt aus configs/copy_prompts/subjects_de.json:
python scripts/generate_verda.py --subject dachdeckerei --tone emotional --length kurz --out drafts.md

# Ad-hoc für echten Kunden:
python scripts/generate_verda.py --name "Cafe Krut" --branche Gastronomie \
    --fakt "Rösterei seit 2011" --fakt "nur Direkthandel-Bohnen" --tone modern

# Ausgewählte Typen + min-p gegen Rest-Tics:
python scripts/generate_verda.py --subject raven --types hero,cta --min-p 0.02
```

Töne: `sachlich | emotional | modern | premium` · Längen: `kurz | ausfuehrlich`.
Der Harness setzt einen System-Prompt, der Meta-Geplauder unterdrückt und eine
einzige fertige Version erzwingt (keine „Hier sind ein paar Optionen…").

### Roher OpenAI-Aufruf (ohne Harness)

```bash
source ~/.config/verda-antislop.env
curl -s "$VERDA_ENDPOINT/v1/chat/completions" \
  -H "Authorization: Bearer $VERDA_API_KEY" -H 'Content-Type: application/json' -d '{
    "model":"PhilflowIO/gemma-3-12b-it-antislop-de",
    "messages":[{"role":"user","content":"Schreib eine Hero-Section für …"}],
    "temperature":0.7, "top_p":0.9, "max_tokens":400
  }'
```

Inferenz-Default: **temp 0,7** (temp 1,0 ist die *Trainings*-Temperatur, zu heiß für Inferenz).

## Deployen (from scratch / neu aufsetzen)

```bash
export VERDA_CLIENT_ID=...  VERDA_CLIENT_SECRET=...   # Verda Console -> Keys
export HF_TOKEN=hf_...                                # read auf das Modell-Repo (write nur falls Processor-Fix nötig)

python scripts/deploy_verda.py            # legt Deployment an (L40S, min_replica=1)
python scripts/deploy_verda.py --status   # Status + Replicas
```

Danach **einmalig** in der Verda-Console einen **Inference API Key** erzeugen
(Credentials → Inference API Keys → Create) und in `~/.config/verda-antislop.env`
eintragen. Der Key ist **console-only**, nicht per API erzeugbar. Die Cloud-Credentials
(client_id/secret) gelten nur für `api.verda.com`, **nicht** für das Container-Gateway.

## Ops

```bash
python scripts/deploy_verda.py --scale-to-zero   # idle = 0 Kosten (nächster Aufruf ~Cold-Start paar Min)
python scripts/deploy_verda.py --status
```

Bei aktivem Generieren `min_replica=1` lassen (kein Cold-Start). Fertig → scale-to-zero.

## Bringup-Fallen (am 2026-07-07 real getroffen)

1. **Image-Tag `>= v0.11.0`.** Ältere vLLM (z.B. das Tutorial-`v0.7.1`) crashen an gemma-3s
   `rope_scaling`. Das offizielle 0.11.0-Image bringt das passende `transformers` mit.
2. **GPU `>= 40 GB`.** 12b bf16 ≈ 24 GB Gewichte → 24-GB-Karten OOMen. L40S 48 GB = billigster
   Sweet-Spot. Fallback auf 24 GB nur mit `--quantization fp8`.
3. **`preprocessor_config.json` muss im Modell-Repo liegen.** Der Merge deklariert die
   multimodale `Gemma3ForConditionalGeneration` (Vision-Tower ist drin), aber der v2-Upload
   enthielt nur Gewichte + config + tokenizer. vLLM lädt beim Start den Image-Processor →
   ohne `preprocessor_config.json` = leere Liste = IndexError = EngineCore-Crash
   (Status UNHEALTHY, System-Log „Startup probe failed: connection refused").
   `deploy_verda.py::ensure_processor_files()` legt `preprocessor_config.json` +
   `processor_config.json` idempotent aus dem Base-Modell nach.
   **TODO:** den Merge-Step in `modal_app.py` so patchen, dass v3+ diese Dateien direkt
   mit hochlädt — dann entfällt der Nachlege-Schritt.

## Bekannte Modell-Schwächen (v2, nicht Infra)

- **du/Sie kippt** innerhalb eines Laufs (auffälligster Defekt).
- **Rest-Slop** bleibt (Whac-a-Mole: v2 bändigt Tic N, züchtet Tic N+1 wie „maximal").
- Gelegentlich **Denglisch** („Flat-Roof-Konstruktion").
- Deshalb: Output = Entwurf, Human-Edit ist der letzte Schliff.
