"""Stufe-1 Modal-App: Infrastruktur-Skelett für den FTPO-Lauf.

Zwei Phasen, die nicht gleichzeitig in den VRAM passen (auto-antislop stoppt
vLLM vor dem Training): erst vLLM-Generierung + DE-Slop-Profiling, dann
FTPO-LoRA-Training. Beide teilen sich den persistenten Volume-Cache, damit das
12B-Modell nicht zweimal geladen werden muss.

Stand Stufe 1 (Infra): die SDK-Syntax ist gegen Modal 1.4.2 verifiziert und der
App-Graph baut lokal ohne Auth. `preflight` ist lauffähig und prüft Secret +
gated-gemma-Zugang + Volume. `generate_and_profile` und `train_ftpo` sind
bewusst Stubs — ihr Inneres ist der auto-antislop-DE-Umbau (eigenes Issue,
HANDOFF-STUFE-1-MODAL.md Schritt 2), nicht Teil dieser Infra-Aufgabe.

Voraussetzungen (Phil-seitig, account-extern):
    1. `modal token new`            — Modal-CLI re-authentifizieren
    2. Modal-Secret `huggingface`   — HF_TOKEN (read+write), gated-gemma-fähig
    3. Modal-Volume `antislop-de-vol` (legt `preflight` via create_if_missing an)
    4. `google/gemma-3-12b-it` gated-Lizenz auf HF akzeptiert

Lauf:  modal run modal_app.py            # -> preflight
       modal run modal_app.py::preflight
"""

from __future__ import annotations

import os

import modal

# --- Konstanten -------------------------------------------------------------

APP_NAME = "antislop-de"
BASE_MODEL = "google/gemma-3-12b-it"  # gated, gemma-Lizenz, Dense, FTPO-validiert
GPU = "H100"  # 80GB; A100-80GB (~2.50 $/h) als Spar-Alternative, gleicher VRAM-Komfort
CACHE_DIR = "/cache"  # Volume-Mountpoint: Modelle, generierte Daten, Slop-Profil, LoRA

# auto-antislop-DE ist jetzt vendored (Issue #16, vendor/auto-antislop) statt
# zur Laufzeit geklont: eingefrorener, reproduzierbarer Stand für die teuren
# GPU-Läufe, DE-Patches im selben Repo sichtbar (vendor/PATCHES-DE.md). Das
# GPU-Image kopiert diesen Pfad in den Container (add_local_dir), kein git clone.
AUTO_ANTISLOP_LOCAL = "vendor/auto-antislop"  # repo-relativ
AUTO_ANTISLOP_DIR = "/root/auto-antislop"  # Ziel im Container

# --- Images -----------------------------------------------------------------
# `modal run` baut die Images ALLER registrierten Functions zur App-Build-Zeit
# (nicht lazy pro Aufruf). Zwei getrennte Images: ein leichtes CPU-Image fürs
# preflight, ein schweres GPU-Image für die Pipeline.
cpu_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("huggingface-hub")
    .env({"HF_HUB_DISABLE_XET": "1", "HF_HOME": f"{CACHE_DIR}/hf"})
)

# GPU-Image: CUDA-devel-Basis (hat nvcc) — entschieden gegen debian_slim, weil
# flash-attn gegen nvcc kompiliert. CUDA 12.6 passt zu torch 2.8 (cu126), damit
# flash-attn nicht gegen eine fremde CUDA-Version baut. torch/vllm sind als
# kohärentes Tripel gepinnt (Spec: research/anti-slop-modal-trainingsplan).
# Der vendored auto-antislop-Baum wird ins Image kopiert (kein git clone).
gpu_image = (
    modal.Image.from_registry(
        "nvidia/cuda:12.6.2-devel-ubuntu22.04", add_python="3.11"
    )
    .apt_install("git", "build-essential", "ninja-build")
    # torch ZUERST und gepinnt (flash-attn/vllm bauen dagegen).
    .pip_install("torch==2.8.*", "setuptools", "wheel", "packaging", "ninja")
    # vLLM (Generierung) + Finetuning-Stack, kohärent zu torch 2.8.
    # vLLM auf 0.11.0 (nicht 0.10.2): 0.11.0 hat native, CI-getestete gemma-3-
    # Unterstützung gegen torch==2.8.0 — exakt unser torch-Pin, also kein
    # flash-attn-Rebuild gegen ein fremdes torch (0.11.1 verlangt torch 2.9 und
    # würde das Tripel sprengen). Der frühere 0.10.2-Lauf crashte beim vLLM-Start
    # mit „rope_scaling should have a 'rope_type' key": 0.10.2s ModelConfig patcht
    # gemma-3s rope-Dict falsch. 0.11.0 liest gemma-3s rope nativ (model_executor/
    # models/gemma3.py) und erreicht patch_rope_scaling_dict für gemma-3 gar nicht
    # erst, weil dessen top-level `rope_scaling` None ist. transformers bleibt
    # gepinnt auf 4.56.2: vLLM 0.11.0s requires_dist lautet `transformers>=4.55.2`
    # OHNE Upper-Bound, deshalb zog pip transformers 5.x — und genau 5.x benennt
    # gemma-3s top-level `rope_scaling` in `rope_parameters` um (HF-Breaking-Change,
    # vLLM-PR #28542). vLLM 0.11.0 kennt diese Forward-Compat noch nicht, liest ein
    # `rope_scaling`-Dict ohne `rope_type` und crasht beim Serve-Start mit
    # „rope_scaling should have a 'rope_type' key" (Smoke 2026-06-07, sowohl unter
    # 0.10.2 als auch 0.11.0). 4.56.2 ist die von vLLM 0.11.1 CI-validierte gemma-3-
    # Version (Release-Notes #24638 + gemma3-Fix #23178) und setzt gemma-3s top-level
    # `rope_scaling=None` (configuration_gemma3.py v4.56.2), womit der rope-Patch für
    # gemma-3 gar nicht erst greift. trl<1.0 (0.22.x) verlangt nur transformers>=4.55.0
    # (kein Upper-Bound), ist also 4.56.2-kompatibel und liefert die DPO/KTO/ORPO-
    # Trainer, die core/finetuning.py importiert.
    .pip_install(
        "vllm==0.11.0",
        "transformers==4.56.2",
        "trl<1.0",
        "peft",
        "accelerate",
        "bitsandbytes",
        "datasets",
        "sentencepiece",
        "protobuf",
        "hf_transfer",
        "tensorboard",
    )
    # auto-antislop / slop-forensics Laufzeit-Deps.
    .pip_install(
        "pyyaml>=6.0", "pandas>=1.5", "numpy>=1.20", "nltk>=3.6",
        "requests>=2.25", "tqdm>=4.60", "tiktoken", "wordfreq>=3.0",
        "regex", "python-dotenv", "scipy",
    )
    # flash-attn zuletzt: HART auf 2.8.3 als PREBUILT-Wheel (kein Source-Compile).
    # Für 2.8.2 gibt es KEIN torch-2.8-Wheel (Dao-AILab-Releases springen bei torch
    # 2.8 direkt auf 2.8.3); `pip install flash-attn==2.8.2` erzwang daher einen
    # Source-Build, dessen setup.py beim Wheel-Lookup 404 wirft und mit „TypeError:
    # not enough arguments for format string" crasht — Image-Build rot (Smoke
    # 2026-06-08). Der alte 2.8.2-Cap stammte aus vLLM 0.10.2, dessen ViT-Selector
    # den SigLIP-Tower über das EXTERNE flash-attn führte und 2.8.3 ablehnte. vLLM
    # 0.11.0 nutzt für den ViT-Pfad sein GEBÜNDELTES vllm_flash_attn (platforms/
    # cuda.py get_vit_attn_backend -> FLASH_ATTN_V1 auf SM80+), nicht das externe
    # Paket — der 2.8.2-Cap entfällt. Direkter Wheel-URL erzwingt das prebuilt-Wheel
    # (abiFALSE = torch-Standard-ABI), Build läuft in Sekunden statt ~30 min Compile.
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})
    .run_commands(
        "pip install https://github.com/Dao-AILab/flash-attention/releases/download/"
        "v2.8.3/flash_attn-2.8.3+cu12torch2.8cxx11abiFALSE-cp311-cp311-linux_x86_64.whl"
    )
    .env({"HF_HUB_DISABLE_XET": "1", "HF_HOME": f"{CACHE_DIR}/hf"})
    # Vendored DE-gepatchter auto-antislop-Baum in den Container.
    .add_local_dir(AUTO_ANTISLOP_LOCAL, AUTO_ANTISLOP_DIR, copy=True)
)

app = modal.App(APP_NAME)

# Persistenter Cache, projekt-eigen (nicht das bestehende bernd-hf-cache).
vol = modal.Volume.from_name("antislop-de-vol", create_if_missing=True)

# HF-Token für gated gemma-Download + privaten Merge-Upload. required_keys lässt
# den Aufruf früh und klar scheitern, wenn das Secret den Key nicht enthält.
hf_secret = modal.Secret.from_name("huggingface", required_keys=["HF_TOKEN"])


# --- Preflight: Infra-Abnahme (lauffähig) -----------------------------------


@app.function(
    image=cpu_image,
    volumes={CACHE_DIR: vol},
    secrets=[hf_secret],
    timeout=10 * 60,
)
def preflight() -> dict:
    """Prüft die Stufe-1-Akzeptanzkriterien von innerhalb Modal.

    1. HF_TOKEN ist im Secret vorhanden und gültig (whoami).
    2. gemma-3-12b-it gated-Lizenz akzeptiert (Config-Download liefert 200,
       nicht 401) — der eine Fehler, der den ganzen Lauf sonst beim
       Modell-Download kippt.
    3. Volume ist gemountet und beschreibbar (write -> commit -> read-back).
    """
    from huggingface_hub import hf_hub_download, whoami
    from huggingface_hub.utils import GatedRepoError, RepositoryNotFoundError

    report: dict = {}

    # 1. Token gültig?
    token = os.environ["HF_TOKEN"]  # required_keys garantiert Präsenz
    who = whoami(token=token)
    report["hf_user"] = who.get("name")

    # 2. gated-gemma-Zugang? config.json ist klein — billiger Lizenz-Probe-Download.
    try:
        cfg = hf_hub_download(
            repo_id=BASE_MODEL,
            filename="config.json",
            token=token,
            cache_dir=f"{CACHE_DIR}/hf",
        )
        report["gemma_access"] = "ok"
        report["gemma_config"] = cfg
    except GatedRepoError:
        report["gemma_access"] = "GATED — Lizenz auf HF noch nicht akzeptiert (401)"
    except RepositoryNotFoundError:
        report["gemma_access"] = "NOT_FOUND — Token hat keinen Repo-Zugang"

    # 3. Volume schreibbar?
    marker = f"{CACHE_DIR}/.preflight_ok"
    with open(marker, "w") as fh:
        fh.write("antislop-de preflight\n")
    vol.commit()
    report["volume_writable"] = os.path.exists(marker)

    return report


# --- Pipeline: Generierung + DE-Slop-Profiling + FTPO-Training --------------
# auto-antislop managed vLLM selbst (Start -> Generierung -> Stop -> Finetune in
# EINEM Prozess), darum eine End-to-End-Function statt zweier. Skaliert über die
# De-Risking-Leiter via max_prompts / max_train_examples.


@app.function(
    image=gpu_image,
    gpu=GPU,
    volumes={CACHE_DIR: vol},
    secrets=[hf_secret],
    timeout=8 * 60 * 60,
)
def run_pipeline(
    max_prompts: int = 20,
    max_train_examples: int = 200,
    num_iterations: int = 2,
    run_finetune: bool = True,
) -> dict:
    """Voller auto-antislop-DE-Lauf: DE-Generierung -> Slop-Profil/Banlist -> FTPO.

    Erwartet im Volume (vom local_entrypoint hochgeladen):
      /cache/human_writing_profile_de.json  (Baseline-Lineal, config:human_profile_path)
      /cache/prompts_de.json                 (DE-Copy-Prompts als Liste von Strings)

    Schreibt Ergebnisse nach /cache/auto_antislop_runs (config:experiment_base_dir).
    """
    import subprocess

    os.environ.setdefault("HF_TOKEN", os.environ.get("HF_TOKEN", ""))
    # vLLM/HF lesen den Token aus der Env; gemma ist gated.
    os.environ["HUGGING_FACE_HUB_TOKEN"] = os.environ["HF_TOKEN"]

    for required in ("human_writing_profile_de.json", "prompts_de.json"):
        path = f"{CACHE_DIR}/{required}"
        if not os.path.exists(path):
            raise FileNotFoundError(f"{path} fehlt — local_entrypoint muss es hochladen.")

    cmd = [
        "python", "main.py",
        "-c", "auto_antislop_config.yaml",
        "--generation-max-prompts", str(max_prompts),
        "--num-iterations", str(num_iterations),
    ]
    if run_finetune:
        cmd += ["--run-finetune", "--finetune-mode", "ftpo"]
        # Steuert die Zahl der FTPO-Trainingsbeispiele ehrlich über die CLI
        # (Patch #20) statt über eine stille config-Mutation.
        cmd += ["--finetune-max-train-examples", str(max_train_examples)]

    print(f"[run_pipeline] cwd={AUTO_ANTISLOP_DIR} cmd={' '.join(cmd)}", flush=True)
    proc = subprocess.run(cmd, cwd=AUTO_ANTISLOP_DIR)
    vol.commit()

    runs_dir = f"{CACHE_DIR}/auto_antislop_runs"
    runs = sorted(os.listdir(runs_dir)) if os.path.isdir(runs_dir) else []
    return {"returncode": proc.returncode, "runs_dir": runs_dir, "runs": runs}


# --- Eval-Generierung: Baseline vs. FTPO Augenschein ------------------------
# Erste Sprosse der Eval-Leiter (#22): identische Prompts, einmal vom Baseline-
# gemma, einmal vom FTPO-Merge. Bewusst transformers statt vLLM — bei ~8 Prompts
# ist Server-Orchestrierung Overkill; sequentielles Laden (erst Baseline, dann
# FTPO) passt bequem in 80 GB. Gleicher Seed je Prompt für beide Modelle, damit
# die Sampling-Bedingung fair ist und der Unterschied am Modell hängt, nicht am
# Zufall. System-Prompt + Sampling spiegeln die Pipeline-Generierung.

# Pipeline-Generierungs-Setup (auto_antislop_config.yaml:65/66/75/76).
EVAL_SYSTEM_PROMPT = (
    "Du bist ein erfahrener deutscher Werbetexter. Gib ausschließlich den "
    "fertigen Website-Text aus — keine Vorrede, keine Erklärung, keine Optionen."
)
EVAL_TEMPERATURE = 1.0
EVAL_TOP_P = 1.0
EVAL_MAX_NEW_TOKENS = 1000
# 1.0 = aus (Baseline-Parität). >1 bestraft Token-Wiederholung — Hebel gegen die
# degenerierten „inklusive…inklusive"-Run-ons (#38); ~1.15–1.3 ist der Testbereich.
EVAL_REPETITION_PENALTY = 1.0


def _eval_out_suffix(
    temperature: float, repetition_penalty: float, lora_scale: float = 1.0
) -> str:
    """Datei-Suffix für Eval-Outputs — temp immer, rep-penalty + lora-scale nur
    wenn aktiv, damit Varianten-Läufe sich nicht gegenseitig überschreiben
    (rep-penalty #38, lora-scale #40)."""
    suffix = f"_t{temperature:g}"
    if repetition_penalty != 1.0:
        suffix += f"_rp{repetition_penalty:g}"
    if lora_scale != 1.0:
        suffix += f"_ls{lora_scale:g}"
    return suffix
# Voller FTPO-Lauf 2026-06-08 (chosen_win 0.86), HANDOFF-STUFE-3.
DEFAULT_FTPO_MERGE = (
    "/cache/auto_antislop_runs/run_20260608_061845/"
    "finetuned_model_ftpo_exp01/merged_16bit"
)
# PEFT-Adapter desselben Laufs (r=128/alpha=128 inkl. lm_head) — für den
# Scale-down-Test (#40), der die FTPO-Seite aus Basis + skaliertem Adapter lädt.
DEFAULT_FTPO_ADAPTER = (
    "/cache/auto_antislop_runs/run_20260608_061845/"
    "finetuned_model_ftpo_exp01/lora_adapters"
)
# v2 — sanftes Rezept (chosen_win 0.7874, ThresholdStop), #42/#43. Das finale Modell.
DEFAULT_V2_MERGE = (
    "/cache/auto_antislop_runs/run_20260609_140022/"
    "finetuned_model_ftpo_exp01/merged_16bit"
)
HF_MODEL_REPO = "PhilflowIO/gemma-3-12b-it-antislop-de"


@app.function(
    image=gpu_image,
    gpu=GPU,
    volumes={CACHE_DIR: vol},
    secrets=[hf_secret],
    timeout=90 * 60,  # Marge: Scale-down lädt gemma 2× + merged den Adapter (#40)
)
def eval_generate(
    ftpo_merge_path: str = DEFAULT_FTPO_MERGE,
    temperature: float = EVAL_TEMPERATURE,
    repetition_penalty: float = EVAL_REPETITION_PENALTY,
    max_new_tokens: int = EVAL_MAX_NEW_TOKENS,
    lora_adapter_path: str = "",
    lora_scale: float = 1.0,
    register: str = "",
    out_tag: str = "",
) -> list[dict]:
    """Generiert jeden Eval-Prompt mit Baseline-gemma UND dem FTPO-Modell.

    Erwartet `/cache/eval_raven_prompts.json` (Liste von {id, prompt, ...}) im
    Volume. Gibt eine Liste {id, copy_type, tone, prompt, baseline, ftpo} zurück.
    `temperature` steuert das Sampling — 1.0 = Pipeline-Default (heiß), 0.7 =
    ruhigerer Inferenz-Test, um Fluss-Defekte vom Sampling-Rauschen zu trennen.
    `register` (optional) wird an den System-Prompt angehängt, um die Anrede zu
    pinnen (z.B. "du" für Raven — die du/Sie-Inkonsistenz war fehlende Vorgabe,
    kein Defekt).
    `repetition_penalty` (>1) und `max_new_tokens`-Cap (#38) sind der billige
    Inferenz-Hebel gegen die degenerierten „inklusive…inklusive"-Run-ons; beide
    werden identisch auf Baseline UND FTPO angewandt, damit der Vergleich fair
    bleibt.
    `lora_adapter_path` + `lora_scale` (#40): wenn gesetzt, wird die FTPO-Seite
    NICHT aus dem gemergten Modell geladen, sondern aus Basis + PEFT-Adapter, dessen
    LoRA-Scaling mit `lora_scale` multipliziert wird (0.0 = reine Basis, 1.0 = volle
    Trainingsstärke). Test gegen das überpresste r=128/alpha=128-LoRA (inkl. lm_head).
    """
    import json

    import torch
    from transformers import AutoModelForImageTextToText, AutoTokenizer, set_seed

    os.environ["HUGGING_FACE_HUB_TOKEN"] = os.environ["HF_TOKEN"]

    prompts_path = f"{CACHE_DIR}/eval_raven_prompts.json"
    if not os.path.exists(prompts_path):
        raise FileNotFoundError(f"{prompts_path} fehlt — eval_compare muss es hochladen.")
    use_lora = bool(lora_adapter_path)
    if use_lora:
        if not os.path.isdir(lora_adapter_path):
            raise FileNotFoundError(f"LoRA-Adapter fehlt: {lora_adapter_path}")
    elif not os.path.isdir(ftpo_merge_path):
        raise FileNotFoundError(f"FTPO-Merge fehlt: {ftpo_merge_path}")
    with open(prompts_path, encoding="utf-8") as fh:
        items = json.load(fh)

    system_prompt = EVAL_SYSTEM_PROMPT + (f" {register.strip()}" if register.strip() else "")

    def _load_plain(model_id_or_path: str):
        tok = AutoTokenizer.from_pretrained(model_id_or_path)
        model = AutoModelForImageTextToText.from_pretrained(
            model_id_or_path, torch_dtype=torch.bfloat16, device_map="cuda"
        )
        return model, tok

    def _load_lora_scaled(adapter_path: str, scale: float):
        """Basis + PEFT-Adapter, LoRA-Scaling mit `scale` multipliziert (#40).
        scale=1.0 reproduziert den gemergten Merge, scale<1.0 dämpft die
        Antislop-Pressung — Test ob das die Kohärenz zurückbringt."""
        from peft import PeftModel

        tok = AutoTokenizer.from_pretrained(adapter_path)
        base = AutoModelForImageTextToText.from_pretrained(
            BASE_MODEL, torch_dtype=torch.bfloat16, device_map="cuda"
        )
        model = PeftModel.from_pretrained(base, adapter_path)
        scaled = 0
        for module in model.modules():
            # Jede LoRA-Layer hält ein scaling-Dict {adapter_name: alpha/r}.
            if hasattr(module, "scaling") and isinstance(module.scaling, dict):
                for k in list(module.scaling):
                    module.scaling[k] = module.scaling[k] * scale
                    scaled += 1
        # Skaliertes Delta in die Basis backen → Inferenz läuft auf gemergten
        # Gewichten (schnell). Unmerged-PEFT mit r=128 auf allen Modulen inkl.
        # lm_head ist ~5× langsamer und sprengte den 1h-Funktions-Timeout (#40).
        # merge nutzt das oben gesetzte scaling → die gebackene Delta ist gedämpft.
        model = model.merge_and_unload()
        print(
            f"[eval_generate]   LoRA scaling ×{scale:g} auf {scaled} Layer, dann gemergt",
            flush=True,
        )
        return model, tok

    def _run(model, tok) -> list[str]:
        model.eval()
        outs: list[str] = []
        for idx, it in enumerate(items):
            # gemma-3 hat keine eigene System-Rolle → System in den User-Turn
            # falten (äquivalent zu wie das Chat-Template es ohnehin auflöst).
            user = f"{system_prompt}\n\n{it['prompt']}"
            msgs = [{"role": "user", "content": user}]
            input_ids = tok.apply_chat_template(
                msgs, add_generation_prompt=True, return_tensors="pt"
            ).to("cuda")
            set_seed(1234 + idx)  # gleicher Seed je Prompt für beide Modelle
            with torch.no_grad():
                gen = model.generate(
                    input_ids,
                    max_new_tokens=max_new_tokens,
                    do_sample=True,
                    temperature=temperature,
                    top_p=EVAL_TOP_P,
                    repetition_penalty=repetition_penalty,
                )
            text = tok.decode(gen[0, input_ids.shape[1]:], skip_special_tokens=True)
            outs.append(text.strip())
        del model
        torch.cuda.empty_cache()
        return outs

    print(f"[eval_generate] Baseline {BASE_MODEL} …", flush=True)
    baseline = _run(*_load_plain(BASE_MODEL))
    if use_lora:
        print(f"[eval_generate] FTPO LoRA {lora_adapter_path} @ scale {lora_scale:g} …", flush=True)
        ftpo = _run(*_load_lora_scaled(lora_adapter_path, lora_scale))
    else:
        print(f"[eval_generate] FTPO {ftpo_merge_path} …", flush=True)
        ftpo = _run(*_load_plain(ftpo_merge_path))

    results = []
    for it, b, f in zip(items, baseline, ftpo):
        results.append(
            {
                "id": it.get("id"),
                "copy_type": it.get("copy_type"),
                "tone": it.get("tone"),
                "length": it.get("length"),
                "prompt": it["prompt"],
                "baseline": b,
                "ftpo": f,
            }
        )

    eff_scale = lora_scale if use_lora else 1.0
    suffix = _eval_out_suffix(temperature, repetition_penalty, eff_scale)
    out_path = f"{CACHE_DIR}/eval_raven_compare{out_tag}{suffix}.json"
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=2)
    vol.commit()
    print(
        f"[eval_generate] {len(results)} Paare (temp {temperature:g}, "
        f"rep_pen {repetition_penalty:g}, max_new {max_new_tokens}, "
        f"lora_scale {eff_scale:g}) -> {out_path}",
        flush=True,
    )
    return results


# --- Capability-Spotcheck: GSM8K + MMLU, Baseline vs FTPO --------------------
# Der FTPO-vs-DPO-Kernanspruch: Slop weg OHNE Fähigkeits-Verlust. Leichtgewichtiger
# Eigen-Harness (kein lm-eval-Dep — Spotcheck, kein Leaderboard). Greedy für
# Reproduzierbarkeit; beide Modelle sehen identische, vorab fixierte Tasks.


@app.function(
    image=gpu_image,
    gpu=GPU,
    volumes={CACHE_DIR: vol},
    secrets=[hf_secret],
    timeout=60 * 60,
)
def capability_eval(
    ftpo_merge_path: str = DEFAULT_FTPO_MERGE,
    n_gsm8k: int = 100,
    n_mmlu: int = 100,
) -> dict:
    """Misst GSM8K (Mathe-Reasoning) + MMLU (Wissen) für Baseline & FTPO."""
    import json
    import re

    import torch
    from datasets import load_dataset
    from transformers import AutoModelForImageTextToText, AutoTokenizer

    os.environ["HUGGING_FACE_HUB_TOKEN"] = os.environ["HF_TOKEN"]
    if not os.path.isdir(ftpo_merge_path):
        raise FileNotFoundError(f"FTPO-Merge fehlt: {ftpo_merge_path}")

    # --- Tasks vorab fixieren (beide Modelle identisch) ---
    gsm = load_dataset("openai/gsm8k", "main", split=f"test[:{n_gsm8k}]")
    gsm_tasks = []
    for ex in gsm:
        gold = ex["answer"].split("####")[-1].strip().replace(",", "")
        gsm_tasks.append((ex["question"], gold))

    mmlu = load_dataset("cais/mmlu", "all", split="test").shuffle(seed=0).select(range(n_mmlu))
    mmlu_tasks = []
    for ex in mmlu:
        letters = ["A", "B", "C", "D"]
        block = "\n".join(f"{letters[i]}) {c}" for i, c in enumerate(ex["choices"]))
        mmlu_tasks.append((ex["question"], block, letters[ex["answer"]]))

    def _num(s: str):
        m = re.findall(r"-?\d+(?:\.\d+)?", s.replace(",", ""))
        if not m:
            return None
        try:
            return float(m[-1])
        except ValueError:
            return None

    def _run(path: str) -> dict:
        tok = AutoTokenizer.from_pretrained(path)
        model = AutoModelForImageTextToText.from_pretrained(
            path, torch_dtype=torch.bfloat16, device_map="cuda"
        )
        model.eval()

        def gen(prompt: str, max_new: int) -> str:
            ids = tok.apply_chat_template(
                [{"role": "user", "content": prompt}],
                add_generation_prompt=True, return_tensors="pt",
            ).to("cuda")
            with torch.no_grad():
                out = model.generate(ids, max_new_tokens=max_new, do_sample=False)
            return tok.decode(out[0, ids.shape[1]:], skip_special_tokens=True)

        gsm_ok = 0
        gold_f_cache = {}
        for q, gold in gsm_tasks:
            o = gen(f"{q}\n\nSolve step by step. Give the final answer on the last "
                    f"line as '#### <number>'.", 320)
            tail = o.split("####")[-1] if "####" in o else o
            pred, g = _num(tail), gold_f_cache.get(gold) or _num(gold)
            gold_f_cache[gold] = g
            if pred is not None and g is not None and abs(pred - g) < 1e-3:
                gsm_ok += 1

        mmlu_ok = 0
        for q, block, gold in mmlu_tasks:
            o = gen(f"{q}\n\n{block}\n\nAnswer with the single letter (A, B, C, or D).", 8)
            m = re.search(r"[ABCD]", o.upper())
            if m and m.group(0) == gold:
                mmlu_ok += 1

        del model
        torch.cuda.empty_cache()
        return {
            "gsm8k": round(100 * gsm_ok / len(gsm_tasks), 1),
            "mmlu": round(100 * mmlu_ok / len(mmlu_tasks), 1),
        }

    print(f"[capability] Baseline {BASE_MODEL} …", flush=True)
    base = _run(BASE_MODEL)
    print(f"[capability] FTPO {ftpo_merge_path} …", flush=True)
    ftpo = _run(ftpo_merge_path)
    result = {
        "n_gsm8k": len(gsm_tasks),
        "n_mmlu": len(mmlu_tasks),
        "baseline": base,
        "ftpo": ftpo,
        "delta": {k: round(ftpo[k] - base[k], 1) for k in base},
    }
    out = f"{CACHE_DIR}/eval_capability.json"
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    vol.commit()
    print(f"[capability] {result} -> {out}", flush=True)
    return result


@app.local_entrypoint()
def main() -> None:
    """Default-Lauf: Infra-Preflight. Gibt den Abnahme-Report aus."""
    report = preflight.remote()
    print("=== antislop-de Preflight ===")
    for key, value in report.items():
        print(f"  {key}: {value}")


def _build_prompts_json(jsonl_path: str, out_path: str) -> int:
    """prompts_de.jsonl (Objekte mit 'prompt') -> JSON-Liste von Strings."""
    import json

    prompts = []
    with open(jsonl_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                prompts.append(json.loads(line)["prompt"])
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(prompts, fh, ensure_ascii=False)
    return len(prompts)


@app.local_entrypoint()
def smoke(max_prompts: int = 20, max_train_examples: int = 200) -> None:
    """Smoke der De-Risking-Leiter: lädt Profil + Prompts ins Volume, fährt einen
    kleinen End-to-End-Lauf. `modal run modal_app.py::smoke`.
    """
    import os as _os
    import tempfile

    root = _os.path.dirname(_os.path.abspath(__file__))
    profile = _os.path.join(root, "data/baseline/human_writing_profile_de.json")
    prompts_jsonl = _os.path.join(root, "data/prompts_de.jsonl")
    for p in (profile, prompts_jsonl):
        if not _os.path.exists(p):
            raise SystemExit(f"FEHLT lokal: {p}")

    tmp = tempfile.mkdtemp()
    prompts_json = _os.path.join(tmp, "prompts_de.json")
    n = _build_prompts_json(prompts_jsonl, prompts_json)
    print(f"[smoke] {n} Prompts -> prompts_de.json; lade Profil + Prompts ins Volume …")

    with vol.batch_upload(force=True) as batch:
        batch.put_file(profile, "/human_writing_profile_de.json")
        batch.put_file(prompts_json, "/prompts_de.json")
    print("[smoke] Upload fertig. Starte run_pipeline …")

    report = run_pipeline.remote(
        max_prompts=max_prompts, max_train_examples=max_train_examples
    )
    print("=== run_pipeline ===")
    for key, value in report.items():
        print(f"  {key}: {value}")


@app.local_entrypoint()
def eval_compare(
    ftpo_merge_path: str = DEFAULT_FTPO_MERGE,
    temperature: float = 1.0,
    repetition_penalty: float = EVAL_REPETITION_PENALTY,
    max_new_tokens: int = EVAL_MAX_NEW_TOKENS,
    lora_scale: float = 1.0,
    lora_adapter_path: str = "",
    broad: bool = False,
    register: str = "",
) -> None:
    """Baseline-vs-FTPO Augenschein (#22): lädt die Raven-Holdout-Prompts ins
    Volume, generiert beide Seiten, zieht das Side-by-side lokal.
    `modal run modal_app.py::eval_compare --temperature 0.7`.
    `--broad` nutzt das breite ~36-Prompt-Set (#29), `--register "Duze die Leser
    durchgehend."` pinnt die Anrede.
    `--repetition-penalty 1.2 --max-new-tokens 700` ist der Inferenz-Fix gegen die
    degenerierten Run-ons (#38) — fair auf beide Modelle angewandt.
    `--lora-scale 0.5` (#40) lädt die FTPO-Seite aus Basis + Adapter bei halbem
    LoRA-Gewicht (default-Adapter = der volle Lauf), Test gegen das überpresste
    r=128-LoRA. Sweep: 0.3 / 0.5 / 0.7 / 1.0.
    """
    import json as _json
    import os as _os
    import tempfile

    root = _os.path.dirname(_os.path.abspath(__file__))
    tag = "_broad" if broad else ""
    fname = "eval_raven_prompts_broad.jsonl" if broad else "eval_raven_prompts.jsonl"
    prompts_jsonl = _os.path.join(root, "data", fname)
    if not _os.path.exists(prompts_jsonl):
        raise SystemExit(
            f"FEHLT lokal: {prompts_jsonl} — erst `python scripts/build_eval_prompts.py"
            f"{' --broad' if broad else ''}`."
        )

    items = []
    with open(prompts_jsonl, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                items.append(_json.loads(line))

    tmp = tempfile.mkdtemp()
    prompts_json = _os.path.join(tmp, "eval_raven_prompts.json")
    with open(prompts_json, "w", encoding="utf-8") as fh:
        _json.dump(items, fh, ensure_ascii=False)
    print(f"[eval_compare] {len(items)} Prompts (broad={broad}) -> Volume; starte eval_generate …")

    with vol.batch_upload(force=True) as batch:
        batch.put_file(prompts_json, "/eval_raven_prompts.json")

    # Scale-down (#40): wenn lora_scale != 1.0 und kein Adapter explizit gesetzt,
    # den Adapter des vollen Laufs nehmen. Bei scale==1.0 bleibt es beim Merge-Pfad.
    adapter = lora_adapter_path or (DEFAULT_FTPO_ADAPTER if lora_scale != 1.0 else "")

    results = eval_generate.remote(
        ftpo_merge_path=ftpo_merge_path, temperature=temperature,
        repetition_penalty=repetition_penalty, max_new_tokens=max_new_tokens,
        lora_adapter_path=adapter, lora_scale=lora_scale,
        register=register, out_tag=tag,
    )

    eff_scale = lora_scale if adapter else 1.0
    suffix = _eval_out_suffix(temperature, repetition_penalty, eff_scale)
    out_local = _os.path.join(root, f"data/eval_raven_compare{tag}{suffix}.json")
    with open(out_local, "w", encoding="utf-8") as fh:
        _json.dump(results, fh, ensure_ascii=False, indent=2)
    print(
        f"=== eval_compare: {len(results)} Paare (temp {temperature:g}, "
        f"lora_scale {eff_scale:g}) -> {out_local} ==="
    )


@app.local_entrypoint()
def capability_compare(
    ftpo_merge_path: str = DEFAULT_FTPO_MERGE, n_gsm8k: int = 100, n_mmlu: int = 100
) -> None:
    """Capability-Spotcheck (#31): GSM8K + MMLU Baseline vs FTPO, zieht das
    Ergebnis lokal. `modal run modal_app.py::capability_compare`.
    """
    import json as _json
    import os as _os

    result = capability_eval.remote(
        ftpo_merge_path=ftpo_merge_path, n_gsm8k=n_gsm8k, n_mmlu=n_mmlu
    )
    root = _os.path.dirname(_os.path.abspath(__file__))
    out_local = _os.path.join(root, "data/eval_capability.json")
    with open(out_local, "w", encoding="utf-8") as fh:
        _json.dump(result, fh, ensure_ascii=False, indent=2)
    print("=== capability_compare ===")
    print(f"  GSM8K  baseline {result['baseline']['gsm8k']}  ftpo {result['ftpo']['gsm8k']}  Δ {result['delta']['gsm8k']}")
    print(f"  MMLU   baseline {result['baseline']['mmlu']}  ftpo {result['ftpo']['mmlu']}  Δ {result['delta']['mmlu']}")
    print(f"  -> {out_local}")


# --- HF-Upload: v2 als finales Modell (#44) ---------------------------------
# Privat, nur Gewichte+config+tokenizer (liegen alle im merged_16bit) + eine
# ehrliche Model-Card. KEIN Business-Text, KEINE Prompts (Phils Sorge aus Session 2).

MODEL_CARD = """---
license: gemma
base_model: google/gemma-3-12b-it
language:
- de
tags:
- gemma3
- german
- anti-slop
- ftpo
- marketing-copy
pipeline_tag: text-generation
---

# gemma-3-12b-it-antislop-de

Ein FTPO-Finetune von `google/gemma-3-12b-it` für **natürlicheres deutsches
Schreiben** — speziell deutsche Website-/Marketing-Copy. Trainiert mit der
*Final Token Preference Optimization* (FTPO) Methode aus Sam Paechs
[`auto-antislop`](https://github.com/sam-paech/auto-antislop), auf Deutsch
portiert (deutsches Human-n-gram-Profil, deutsche Banlist, `wordfreq de`).

**Built with Gemma.** Es gelten die [Gemma Terms of Use](https://ai.google.dev/gemma/terms)
und die [Prohibited Use Policy](https://ai.google.dev/gemma/prohibited_use_policy).

## Was es kann

Gegenüber der Basis erzeugt es deutsche Copy mit deutlich weniger
KI-Floskel-Slop und einer lebendigeren, direkteren Tonalität. Der FTPO-Kern-
anspruch — Slop runter **ohne** Capability-Verlust — wird gehalten (GSM8K/MMLU
im Spotcheck unverändert).

## Inferenz

**Default: `temperature=0.7`** (die Trainings-Temperatur 1.0 ist für die
Auslieferung zu heiß). Greedy/0.7 liefert die stabilsten Ergebnisse.

```python
from transformers import AutoModelForImageTextToText, AutoTokenizer
tok = AutoTokenizer.from_pretrained("PhilflowIO/gemma-3-12b-it-antislop-de")
model = AutoModelForImageTextToText.from_pretrained(
    "PhilflowIO/gemma-3-12b-it-antislop-de", torch_dtype="bfloat16", device_map="cuda")
```

## Ehrliche Limitierungen

- **Tic-Umverteilung statt -Beseitigung.** FTPO + feste Banlist bändigt den
  jeweils benannten Floskel-Tic, das Modell weicht aber auf neue Lieblingswörter
  aus (in der Entwicklung: „inklusive" → „maximal"). Es ist *weniger* sloppy als
  die Basis, aber nicht slopfrei.
- **Feine Grammatik.** Vereinzelt Kasus-/Rektionspatzer (v.a. bei Langtext).
- **Human-Edit empfohlen.** Brauchbare Copy als *Entwurf*, nicht als
  unbeaufsichtigter Endtext.

## Nicht enthalten

Nur Modellgewichte, Config und Tokenizer. Keine Trainings-Prompts, keine
Geschäftsdaten.
"""


@app.function(
    image=cpu_image,
    volumes={CACHE_DIR: vol},
    secrets=[hf_secret],
    timeout=60 * 60,
)
def upload_to_hf(
    merge_path: str = DEFAULT_V2_MERGE,
    repo_id: str = HF_MODEL_REPO,
    private: bool = True,
) -> dict:
    """Lädt das gemergte Modell (Gewichte+config+tokenizer) + Model-Card privat
    nach HF. Liest aus dem Volume, nutzt den HF_TOKEN aus dem Secret."""
    import tempfile

    from huggingface_hub import HfApi

    if not os.path.isdir(merge_path):
        raise FileNotFoundError(f"Merge fehlt im Volume: {merge_path}")

    token = os.environ["HF_TOKEN"]
    api = HfApi(token=token)
    api.create_repo(repo_id=repo_id, repo_type="model", private=private, exist_ok=True)
    print(f"[upload] Repo {repo_id} (private={private}) bereit. Lade Gewichte aus {merge_path} …", flush=True)

    # 1. Gewichte + config + tokenizer (alles, was im merged_16bit liegt).
    api.upload_folder(
        folder_path=merge_path,
        repo_id=repo_id,
        repo_type="model",
        commit_message="v2 FTPO-Merge (chosen_win 0.7874, sanftes Rezept #42/#43)",
    )
    # 2. Model-Card separat (gehört nicht ins Gewichts-Verzeichnis).
    with tempfile.TemporaryDirectory() as tmp:
        card = os.path.join(tmp, "README.md")
        with open(card, "w", encoding="utf-8") as fh:
            fh.write(MODEL_CARD)
        api.upload_file(
            path_or_fileobj=card, path_in_repo="README.md",
            repo_id=repo_id, repo_type="model", commit_message="honest model card",
        )
    url = f"https://huggingface.co/{repo_id}"
    print(f"[upload] fertig -> {url}", flush=True)
    return {"repo": repo_id, "private": private, "url": url}


@app.local_entrypoint()
def publish(merge_path: str = DEFAULT_V2_MERGE, repo_id: str = HF_MODEL_REPO) -> None:
    """Privater HF-Upload des finalen v2-Modells (#44).
    `modal run modal_app.py::publish`. Gewichte+config+README, kein Business-Text."""
    res = upload_to_hf.remote(merge_path=merge_path, repo_id=repo_id, private=True)
    print(f"=== publish: {res['url']} (private={res['private']}) ===")
