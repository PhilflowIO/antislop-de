# vendor/: Upstream-Code von Dritten

Dieses Verzeichnis ist im veröffentlichten Repo **leer bis auf zwei Markdown-Dateien**.
Der eigentliche Upstream-Code liegt nicht hier, weil er nicht unserer ist. Er wird
lokal geholt und dann gepatcht.

## Was hier fehlt

`vendor/auto-antislop/`: Sam Paechs FTPO-Pipeline, in der Entwicklung als
eingefrorene flache Kopie mitgeführt (inklusive der beiden Submodule, ohne
`.git/`). Steht in `.gitignore` und ist damit kein Teil dieses Repos.

## Eingefrorener Stand

Die DE-Patches wurden gegen genau diese Commits gebaut (geklont 2026-06-07,
Quelle: `vendor/PATCHES-DE.md`):

| Repo | Upstream | Commit |
|---|---|---|
| `auto-antislop` | https://github.com/sam-paech/auto-antislop | `8fb98fdf019e6fcc20164f9bdec41f9008fcd632` |
| `antislop-vllm` (Submodul) | https://github.com/sam-paech/antislop-vllm | `9204efc348b936c4995994586c063f6ed3282219` |
| `slop-forensics` (Submodul) | https://github.com/sam-paech/slop-forensics | `fa5465881033c9196af35bd281bb391666c3b26f` |

Paper zur Methode: https://arxiv.org/abs/2510.15061

## Holen

```bash
git clone https://github.com/sam-paech/auto-antislop vendor/auto-antislop
git -C vendor/auto-antislop checkout 8fb98fdf019e6fcc20164f9bdec41f9008fcd632
git -C vendor/auto-antislop submodule update --init --recursive
```

Die beiden Submodul-Commits oben sind die Stände, gegen die wir gemessen haben.
Weicht `submodule update` davon ab, checke sie einzeln aus.

Beim Vendoren wurden ausgeschlossen: alle `.git/`, `*.ipynb`, die zwei englischen
Beispielprofile `data/human_writing_profile.json` (74 MB + 29 MB, wir nutzen unser
DE-Profil) und `slop-forensics/results/`. Das ist eine Platz-Optimierung, keine
funktionale.

## Patchen

`vendor/PATCHES-DE.md` listet jede Änderung mit Datei und Zeile: Sprache auf Deutsch (n-gram-Sprache, NLTK-Stopwords, `wordfreq`-Locale), Basismodell,
Profilpfad, die DE-Banlisten und zwei Kompatibilitäts-Fixes ohne Sprachbezug.
Im gepatchten Code trägt jede Stelle einen `# DE-PATCH`-Marker.

## Lizenz

Der Code in `auto-antislop`, `antislop-vllm` und `slop-forensics` gehört
Sam Paech, nicht uns. Es gilt, was im jeweiligen Upstream-Repo steht.

Im eingefrorenen Stand vom 2026-06-07 lag genau **eine** Lizenzdatei:
`slop-forensics/LICENSE`, MIT, `Copyright (c) 2025 Sam Paech`. Für
`auto-antislop` und `antislop-vllm` enthielt der übernommene Baum keine
Lizenzdatei. Prüfe die Lizenz dieser beiden also im Upstream-Repo selbst,
bevor du ihren Code weitergibst. Die Apache-2.0-Lizenz dieses Repos
(`../LICENSE`) deckt sie nicht ab.
