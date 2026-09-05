#!/usr/bin/env python3
"""Generiere deutsche Website-Copy mit dem antislop-de v2-Modell über einen
Verda-Serverless-vLLM-Endpoint (OpenAI-kompatibel).

Setup (einmal, Werte aus der Verda-Console):
    export VERDA_ENDPOINT="https://containers.datacrunch.io/<deployment>"   # ohne /v1
    export VERDA_API_KEY="<Inference-API-Key>"

Nutzung:
    # Ein Subjekt aus subjects_de.json, alle Copy-Typen, ein Ton/Länge:
    python scripts/generate_verda.py --subject dachdeckerei --tone emotional --length kurz

    # Nur ausgewählte Typen:
    python scripts/generate_verda.py --subject raven --types hero,ueber_uns,cta --tone modern

    # Ad-hoc-Subjekt ohne Config-Eintrag:
    python scripts/generate_verda.py --name "Cafe Krut" --branche Gastronomie \
        --fakt "Rösterei seit 2011" --fakt "nur Direkthandel-Bohnen" --tone emotional

Das Modell liefert Entwürfe — spürbar menschlicher, aber Human-Edit bleibt der letzte Schritt.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parents[1]
PROMPTS_DIR = REPO / "configs" / "copy_prompts"
MODEL = os.environ.get("VERDA_MODEL", "PhilflowIO/gemma-3-12b-it-antislop-de")


def load(name: str) -> dict:
    return json.loads((PROMPTS_DIR / name).read_text(encoding="utf-8"))


def fakten_block(fakten: list[str]) -> str:
    if not fakten:
        return ""
    return "Fakten (faktentreu bleiben, nichts erfinden): " + "; ".join(fakten) + "."


def build_prompt(tmpl: str, *, name: str, branche: str, fakten: list[str],
                 tone_hint: str, length_hint: str) -> str:
    return tmpl.format(
        name=name, branche=branche,
        fakten_block=fakten_block(fakten),
        tone_hint=tone_hint, length_hint=length_hint,
    ).strip()


SYSTEM = (
    "Du bist ein deutscher Werbetexter. Gib AUSSCHLIESSLICH den fertigen "
    "Website-Text aus — keine Vorrede, keine Meta-Kommentare, keine Optionen "
    "zur Auswahl, keine Tipps, keine Wiederholung der Aufgabe. Genau EINE "
    "Version. Übernimm die Ansprache (du/Sie) exakt so, wie im Auftrag "
    "verlangt. Erfinde keine Fakten (Jahreszahlen, Zahlen, Namen), die nicht "
    "im Auftrag stehen."
)


def generate(prompt: str, *, temperature: float, min_p: float) -> str:
    url = os.environ["VERDA_ENDPOINT"].rstrip("/") + "/v1/chat/completions"
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "top_p": 0.9,
        "max_tokens": 700,
        "stream": False,
    }
    if min_p > 0:                    # vLLM akzeptiert min_p als extra body param
        payload["min_p"] = min_p
    r = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {os.environ['VERDA_API_KEY']}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=180,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--subject", help="id aus subjects_de.json")
    ap.add_argument("--name")
    ap.add_argument("--branche")
    ap.add_argument("--fakt", action="append", default=[], help="mehrfach nutzbar (ad-hoc)")
    ap.add_argument("--types", default="all", help="Copy-Typ-ids, komma-getrennt, oder 'all'")
    ap.add_argument("--tone", default="sachlich")
    ap.add_argument("--length", default="kurz")
    ap.add_argument("--temperature", type=float, default=0.7)
    ap.add_argument("--min-p", type=float, default=0.0, help="z.B. 0.02 gegen Tic-Ausweichen")
    ap.add_argument("--out", default=None, help="Zieldatei (.md); Default stdout")
    args = ap.parse_args()

    for var in ("VERDA_ENDPOINT", "VERDA_API_KEY"):
        if not os.environ.get(var):
            sys.exit(f"Fehlt: env {var} (aus der Verda-Console setzen).")

    types_cfg = load("copy_types_de.json")
    tone_hint = next((t["hint"] for t in types_cfg["tones"] if t["id"] == args.tone), args.tone)
    length_hint = next((l["hint"] for l in types_cfg["lengths"] if l["id"] == args.length), args.length)

    if args.subject:
        subjects = {s["id"]: s for s in load("subjects_de.json")["subjects"]}
        if args.subject not in subjects:
            sys.exit(f"Unbekanntes Subjekt '{args.subject}'. Verfügbar: {', '.join(subjects)}")
        s = subjects[args.subject]
        name, branche, fakten = s["name"], s.get("branche", ""), s.get("fakten", [])
    else:
        if not (args.name and args.branche):
            sys.exit("Ohne --subject brauchst du --name und --branche.")
        name, branche, fakten = args.name, args.branche, args.fakt

    all_types = types_cfg["copy_types"]
    if args.types != "all":
        wanted = {t.strip() for t in args.types.split(",")}
        all_types = [t for t in all_types if t["id"] in wanted]

    out_lines: list[str] = [f"# Copy-Entwürfe — {name} ({branche})",
                            f"_Modell: {MODEL} · temp {args.temperature}"
                            f"{' · min_p ' + str(args.min_p) if args.min_p else ''} · Ton {args.tone}/{args.length}_\n"]
    for ct in all_types:
        prompt = build_prompt(ct["template"], name=name, branche=branche, fakten=fakten,
                              tone_hint=tone_hint, length_hint=length_hint)
        print(f"→ {ct['label']} …", file=sys.stderr)
        try:
            text = generate(prompt, temperature=args.temperature, min_p=args.min_p)
        except requests.HTTPError as e:
            text = f"[FEHLER {e.response.status_code}: {e.response.text[:200]}]"
        out_lines.append(f"## {ct['label']}\n\n{text}\n")

    result = "\n".join(out_lines)
    if args.out:
        Path(args.out).write_text(result, encoding="utf-8")
        print(f"\nGeschrieben: {args.out}", file=sys.stderr)
    else:
        print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
