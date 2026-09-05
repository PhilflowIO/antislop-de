# KICKOFF — Bau-Session antislop-de

Du baust ein **deutsches Anti-Slop-FTPO-LoRA**. Lies **zuerst `HANDOFF.md` komplett** — dort stehen Mission, alle finalen Entscheidungen, die Baseline-Strategie und die Risiken. Dieser KICKOFF ist nur die Marschroute.

## Was zu tun ist (Reihenfolge)

1. **Stufe 0 — Baseline bauen + abnehmen lassen (BEVOR irgendwas trainiert wird).**
   Die Baseline definiert, was „natürlich" heißt — das ist der kritischste Schritt, Paech löst ihn nicht.
   - OpenSubtitles2018-DE-Frequenzlisten via `orgtre/top-open-subtitles-sentences` ziehen (fertiges pre-LLM-Profil).
   - German Commons (`coral-nlp/german-commons`) Subsets sampeln nach der Default-Mischung in HANDOFF (40/25/20/15, dialogisch-dominant), pre-2022 via source-Whitelist + Perplexity-Band approximieren.
   - n-gram-Slop-Profil rechnen → **Phil 10–20 Beispiel-Slop-Phrasen vorlegen und abnehmen lassen.** Sein Augenschein steht über dem Score.

2. **Modal-Setup** — Secret `huggingface`, Volume `antislop-de-vol`, `gemma-3-12b-it` gated-Lizenz akzeptieren. `auto-antislop` forken, englische Banlist leeren, Modal-SDK-Syntax gegen aktuelle Doku prüfen.

3. **De-Risking-Leiter** — Smoke ($1–2) → Kalibrierung ($5–10, misst Slop-Delta) → Voll ($12–32). Jede Stufe Kill-Kriterium prüfen, nie blind skalieren.

4. **Messen** — DE-Slop-Score, Diversität, GSM8K/MMLU, Pangram (Schluss-Kontrolle, NICHT Trainings-Loss), Phil-Augenschein.

## Entscheidungen stehen — nicht neu aufrollen
gemma-3-12b-it · FTPO (nicht DPO) · Modal/H100 · Baseline-Mischung wie oben · Pangram als Messlatte.

## Die EINE Stelle zum Innehalten
**Lizenz:** Soll der LoRA-Merge frei weiterverbreitbar sein? Dann `EuroLLM-9B-Instruct` (Apache) statt Gemma 3 (Custom-Lizenz). Sonst Default = Gemma 3. Kurz bei Phil rückfragen, falls relevant — sonst durchziehen.

## Arbeitsstil
Autonom, Momentum, kurz berichten. HF-Fakten via rohe `curl`-API (HF gibt 401≠404). Forgejo via `mcp__forgejo_mcp__*`. Git nach CLAUDE.md §7 (Issue→Branch→PR). Research-Reports unter `~/Dokumente/coding/research/anti-slop-*.md` + `antislop-baseline-data-selection-2026-06.md`.
