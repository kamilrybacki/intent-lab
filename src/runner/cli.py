"""CLI entrypoint for the sequential-pair experiment runner.

Architecture:
  1. Provision a single HS key (or reuse from .hs_key)
  2. For each pair:
     a. Create 2 cities under that key
     b. Launch Agent A + Agent B in parallel
     c. Wait for both to finish
     d. Retire both cities (frees slots for the next pair)
  3. Aggregate results across all pairs
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import shutil
import subprocess
import sys
import textwrap
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from src.common.console import C, fail, info, ok, warn
from src.common.constants import CCR_PORT, PROJECT_ROOT
from src.common.http import http_get
from src.common.logging import configure_structlog
from src.common.redis import (
    peek_hs_key,
    store_agent_result,
    store_experiment,
    store_hs_key,
)
from src.runner.agent import Agent
from src.runner.docker import run_agent
from src.runner.healthcheck import HealthChecker
from src.runner.time_pacer import TimePacer
from src.runner.provisioning import (
    create_pair,
    prepare_workspace,
    provision_hs_key,
    retire_pair,
)


def _load_dotenv() -> None:
    """Load variables from .env file into os.environ (no overwrite)."""
    env_path = PROJECT_ROOT / ".env"
    if not env_path.is_file():
        return
    info(f"Loading environment from {env_path}")
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("\"'")
            os.environ.setdefault(key, value)


def _load_or_create_key() -> str:
    """Load existing HS key from Redis, or provision a new one and store it."""
    existing = peek_hs_key()
    if existing:
        ok(f"Reusing HS key from Redis: {existing[:12]}...")
        return existing

    info("No saved key found — provisioning a new Hallucinating Splines API key ...")
    key = provision_hs_key()
    store_hs_key(key)
    ok(f"Key stored in Redis: {key[:12]}...")
    return key


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Intent Engineering Experiment — Sequential Pair Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            examples:
              python3 run_experiment.py              # 5 pairs
              python3 run_experiment.py -n 10        # 10 pairs
        """),
    )
    parser.add_argument(
        "-n", "--pairs", type=int, default=5,
        help="Number of experiment pairs (each = 1 Agent A + 1 Agent B). Default: 5",
    )
    args = parser.parse_args()
    n_pairs = args.pairs

    configure_structlog()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_dir = PROJECT_ROOT / "results" / timestamp
    results_dir.mkdir(parents=True, exist_ok=True)

    # ── Banner ───────────────────────────────────────────────────────────
    print()
    print(f"{C.BOLD}{'=' * 62}{C.NC}")
    print(f"{C.BOLD}  Intent Engineering — Sequential Pair Runner{C.NC}")
    print(f"{C.BOLD}{'=' * 62}{C.NC}")
    print()
    info(f"Pairs: {n_pairs}  (2 agents per pair, run sequentially)")
    info("Each pair: create 2 cities -> run A+B in parallel -> retire cities")
    print()

    # ── Collect credentials ──────────────────────────────────────────────
    _load_dotenv()

    ccr_api_key = os.environ.get("ANTHROPIC_AUTH_TOKEN", "").strip()
    if ccr_api_key:
        ok("ANTHROPIC_AUTH_TOKEN loaded from environment.")
    else:
        ccr_api_key = getpass.getpass(
            "Enter your claude-code-router API key (ANTHROPIC_AUTH_TOKEN): "
        ).strip()
        if not ccr_api_key:
            fail("API key cannot be empty.")

    model_name = os.environ.get("CCR_MODEL", "").strip()
    if model_name:
        ok(f"CCR_MODEL loaded from environment: {model_name}")
    else:
        model_name = input(
            "Which model is your router configured for? (e.g. deepseek-chat): "
        ).strip()
        if not model_name:
            warn("No model specified — continuing anyway.")
    print()
    info(f"Model: {model_name or '<not specified>'}")

    # ── Verify claude-code-router ────────────────────────────────────────
    info(f"Checking claude-code-router at http://127.0.0.1:{CCR_PORT} ...")
    try:
        http_get(f"http://127.0.0.1:{CCR_PORT}", timeout=5)
        ok("claude-code-router is alive.")
    except Exception:
        fail(
            f"Cannot reach claude-code-router on port {CCR_PORT}. Run:  ccr start"
        )

    # ── Provision / load HS key ──────────────────────────────────────────
    hs_key = _load_or_create_key()

    # ── Run pairs sequentially ───────────────────────────────────────────
    all_finished: list[Agent] = []

    for pi in range(1, n_pairs + 1):
        print()
        print(f"{C.BOLD}{'─' * 62}{C.NC}")
        info(f"PAIR {pi}/{n_pairs}")
        print(f"{C.BOLD}{'─' * 62}{C.NC}")

        # Create two cities
        try:
            city_a_id, city_b_id = create_pair(hs_key)
            ok(f"Cities created:  A={city_a_id[:12]}...  B={city_b_id[:12]}...")
        except Exception as exc:
            warn(f"Pair {pi}: city creation failed — {exc}")
            continue

        idx = f"{pi:02d}"
        agent_a = Agent(
            agent_id=f"a-{idx}", intent="a",
            intent_file="intent_a.txt",
            label=f"Agent A-{idx} (Metric Optimization)",
            hs_key=hs_key, city_id=city_a_id,
        )
        agent_b = Agent(
            agent_id=f"b-{idx}", intent="b",
            intent_file="intent_b.txt",
            label=f"Agent B-{idx} (Value Alignment)",
            hs_key=hs_key, city_id=city_b_id,
        )

        # Prepare workspaces
        try:
            agent_a.workspace = prepare_workspace(agent_a)
            agent_b.workspace = prepare_workspace(agent_b)
        except Exception as exc:
            warn(f"Pair {pi}: workspace prep failed — {exc}")
            # Retire cities we won't use
            try:
                retire_pair(hs_key, city_a_id, city_b_id)
            except Exception:
                pass
            continue

        # Run both agents in parallel
        info("Launching Agent A + Agent B in parallel ...")
        pair_agents: list[Agent] = []
        health_targets = [(agent_a.agent_id, city_a_id), (agent_b.agent_id, city_b_id)]
        with HealthChecker(
            health_targets,
            hs_key,
            log_dir=results_dir,
            interval=30.0,
        ), TimePacer(
            health_targets,
            hs_key,
            total_cycles=150,
            interval=30.0,
        ), ThreadPoolExecutor(max_workers=2) as pool:
            futures = {
                pool.submit(
                    run_agent, agent, ccr_api_key,
                    results_dir / agent.agent_id,
                ): agent
                for agent in (agent_a, agent_b)
            }
            for future in as_completed(futures):
                try:
                    finished = future.result()
                    pair_agents.append(finished)
                except Exception as exc:
                    agent = futures[future]
                    agent.status = "failed"
                    warn(f"{agent.agent_id} raised: {exc}")
                    pair_agents.append(agent)

        all_finished.extend(pair_agents)

        # Persist agent results in Redis (truncate HS key for safety)
        for agent in pair_agents:
            store_agent_result(timestamp, {
                "agent_id": agent.agent_id,
                "intent": agent.intent,
                "hs_key": agent.hs_key[:12] + "...",
                "city_id": agent.city_id,
                "status": agent.status,
            })

        # Cleanup workspaces
        for agent in pair_agents:
            if agent.workspace and agent.workspace.exists():
                shutil.rmtree(agent.workspace, ignore_errors=True)

        # Retire cities to free slots for the next pair
        info("Retiring cities ...")
        try:
            retire_pair(hs_key, city_a_id, city_b_id)
            ok("Cities retired — slots freed.")
        except Exception as exc:
            warn(f"City retirement failed: {exc}")

        # Brief pause before next pair
        if pi < n_pairs:
            time.sleep(2.0)

    # ── Write metadata ───────────────────────────────────────────────────
    meta_file = results_dir / "experiment_meta.json"
    meta = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": model_name,
        "n_pairs": n_pairs,
        "hs_key": hs_key[:12] + "...",
        "intent_a_count": n_pairs,
        "intent_b_count": n_pairs,
        "agents": [
            {
                "agent_id": a.agent_id,
                "intent": a.intent,
                "hs_key": a.hs_key[:12] + "...",
                "city_id": a.city_id,
                "status": a.status,
            }
            for a in all_finished
        ],
    }
    meta_file.write_text(json.dumps(meta, indent=2))
    ok(f"Metadata saved to {meta_file}")

    # Persist experiment metadata in Redis
    try:
        store_experiment(timestamp, {
            **meta,
            "timestamp_unix": time.time(),
            "status": "completed",
        })
        ok("Experiment metadata stored in Redis.")
    except Exception as exc:
        warn(f"Redis store failed (non-fatal): {exc}")

    # ── Summary ──────────────────────────────────────────────────────────
    cities_ok = sum(1 for a in all_finished if a.city_id)
    errored = sum(1 for a in all_finished if a.status == "failed")

    print()
    print("=" * 62)
    print(f"{C.BOLD}  EXPERIMENT COMPLETE{C.NC}")
    print("=" * 62)
    print()
    info(f"Pairs:          {n_pairs}")
    ok(f"Agents finished: {len(all_finished)}")
    if errored:
        warn(f"Failed:          {errored}")
    ok(f"Cities with data: {cities_ok}")
    print()
    info(f"Results: {results_dir}")
    print()

    # ── Run evaluation ───────────────────────────────────────────────────
    if cities_ok > 0:
        info(f"Running evaluation across {cities_ok} agents ...")
        print()
        eval_script = PROJECT_ROOT / "evaluate_intent.py"
        report_file = results_dir / "aggregate_report.txt"
        raw_data_file = results_dir / "aggregate_raw_data.json"

        eval_cmd = [
            sys.executable,
            str(eval_script),
            "--meta",
            str(meta_file),
            "-o",
            str(raw_data_file),
        ]

        result = subprocess.run(eval_cmd, capture_output=True, text=True)
        print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        report_file.write_text(result.stdout)
        ok(f"Report saved to {report_file}")
    else:
        warn("No cities with data — skipping evaluation.")

    print()
    print(f"{C.BOLD}All done.{C.NC}")
    print(f"  Per-agent logs:    {results_dir}/<agent_id>/stdout.log")
    print(f"  Aggregate report:  {results_dir}/aggregate_report.txt")
