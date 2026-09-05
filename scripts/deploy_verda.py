#!/usr/bin/env python3
"""Deploy (oder aktualisiere) das antislop-de v2-Modell als Serverless-vLLM-
Endpoint auf Verda (ex-DataCrunch). Idempotent nutzbar.

Voraussetzungen (Env, keine Secrets im Repo):
    export VERDA_CLIENT_ID="..."         # Verda Console -> Keys
    export VERDA_CLIENT_SECRET="..."
    export HF_TOKEN="hf_..."             # read-Scope auf das private Modell-Repo

Nutzung:
    python scripts/deploy_verda.py                 # anlegen (min_replica=1, warm)
    python scripts/deploy_verda.py --gpu L40S      # anderer GPU-Tier
    python scripts/deploy_verda.py --scale-to-zero # nur min_replica=0 setzen (idle=0 Kosten)
    python scripts/deploy_verda.py --status        # Status + Replicas zeigen

Wichtige Fallen (aus dem 2026-07-07-Bringup, siehe docs/SERVING.md):
  * vLLM-Image-Tag MUSS >= v0.11.0 sein (gemma-3 sonst rope_scaling-Crash).
  * GPU >= 40 GB (12b bf16 ~24 GB Gewichte). L40S 48 GB = billigster Sweet-Spot.
  * Das Modell-Repo MUSS `preprocessor_config.json` enthalten (multimodale
    gemma-3-Config lädt sonst den Image-Processor nicht -> IndexError-Crash).
    ensure_processor_files() legt sie bei Bedarf aus dem Base-Modell nach.
"""
from __future__ import annotations

import argparse
import os
import sys

NAME = "antislop-de-v2"
MODEL = os.environ.get("VERDA_MODEL", "PhilflowIO/gemma-3-12b-it-antislop-de")
BASE = os.environ.get("VERDA_BASE_MODEL", "google/gemma-3-12b-it")
IMAGE = os.environ.get("VLLM_IMAGE", "vllm/vllm-openai:v0.11.0")


def client():
    from verda import VerdaClient
    cid, sec = os.environ.get("VERDA_CLIENT_ID"), os.environ.get("VERDA_CLIENT_SECRET")
    if not (cid and sec):
        sys.exit("Fehlt: VERDA_CLIENT_ID / VERDA_CLIENT_SECRET in der Env.")
    return VerdaClient(cid, sec)


def ensure_processor_files() -> None:
    """Kopiert preprocessor_config.json + processor_config.json aus dem Base-Modell
    ins Modell-Repo, falls sie fehlen (verhindert den vLLM-Image-Processor-Crash)."""
    from huggingface_hub import HfApi, hf_hub_download
    tok = os.environ.get("HF_TOKEN")
    if not tok:
        sys.exit("Fehlt: HF_TOKEN (read+write auf das Modell-Repo) in der Env.")
    api = HfApi(token=tok)
    have = set(api.list_repo_files(MODEL, token=tok))
    for f in ("preprocessor_config.json", "processor_config.json"):
        if f in have:
            print(f"  ok: {f} bereits im Repo")
            continue
        p = hf_hub_download(BASE, f, token=tok)
        api.upload_file(path_or_fileobj=p, path_in_repo=f, repo_id=MODEL, token=tok,
                        commit_message=f"add {f} from base (fix vLLM image-processor load)")
        print(f"  nachgelegt: {f}")


def scaling(min_replica: int):
    from verda.containers import (ScalingOptions, ScalingPolicy, ScalingTriggers,
                                  QueueLoadScalingTrigger)
    return ScalingOptions(
        min_replica_count=min_replica, max_replica_count=1,
        scale_down_policy=ScalingPolicy(delay_seconds=300),
        scale_up_policy=ScalingPolicy(delay_seconds=15),
        queue_message_ttl_seconds=600, concurrent_requests_per_replica=4,
        scaling_triggers=ScalingTriggers(queue_load=QueueLoadScalingTrigger(threshold=1)),
    )


def deploy(gpu: str):
    from verda.containers import (
        Container, Deployment, ComputeResource, EnvVar, EnvVarType,
        HealthcheckSettings, EntrypointOverridesSettings, ContainerRegistrySettings,
    )
    ensure_processor_files()
    c = client()
    container = Container(
        name=NAME, image=IMAGE, exposed_port=8000,
        healthcheck=HealthcheckSettings(enabled=True, port=8000, path="/health"),
        entrypoint_overrides=EntrypointOverridesSettings(enabled=True, cmd=[
            "--model", MODEL, "--dtype", "bfloat16",
            "--max-model-len", "8192", "--gpu-memory-utilization", "0.9",
        ]),
        env=[EnvVar(name="HF_TOKEN",
                    value_or_reference_to_secret=os.environ["HF_TOKEN"],
                    type=EnvVarType.PLAIN)],
    )
    dep = Deployment(
        name=NAME, containers=[container],
        compute=ComputeResource(name=gpu, size=1),
        container_registry_settings=ContainerRegistrySettings(is_private=False),
        is_spot=False, scaling=scaling(1),
    )
    created = c.containers.create_deployment(dep)
    print("CREATED:", getattr(created, "name", created))
    print("ENDPOINT:", getattr(created, "endpoint_base_url", None))
    print("Hinweis: Inference-API-Key in der Verda-Console anlegen "
          "(Credentials -> Inference API Keys) — nicht per API erzeugbar.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gpu", default="L40S", help="Serverless-Compute-Name (Default L40S)")
    ap.add_argument("--scale-to-zero", action="store_true")
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()

    if args.status:
        c = client()
        print("status:", c.containers.get_deployment_status(NAME))
        for r in c.containers.get_deployment_replicas(NAME):
            print("replica:", r.status, r.started_at)
        return 0
    if args.scale_to_zero:
        c = client()
        c.containers.update_deployment_scaling_options(NAME, scaling(0))
        print("min_replica=0 gesetzt (idle = keine Kosten, nächster Aufruf ~Cold-Start).")
        return 0
    deploy(args.gpu)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
