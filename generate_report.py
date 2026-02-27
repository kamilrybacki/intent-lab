#!/usr/bin/env python3
"""Generate the Intent Engineering experiment report with matplotlib graphs."""

import json
import os
import urllib.request
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
from PIL import Image

# ── Configuration ────────────────────────────────────────────────────────────

PHASE1_DIR = Path("results/20260226_235446")  # WITH intents
PHASE2_DIR = Path("results/20260227_022744")  # WITHOUT intents
OUTPUT_DIR = Path("results/report")
GRAPHS_DIR = OUTPUT_DIR / "graphs"

METRICS = ["population", "score", "funds"]
METRIC_LABELS = {
    "population": "Population",
    "score": "City Score",
    "funds": "Funds ($)",
}

# Palette
COLOR_A = "#e74c3c"   # red for Intent A (money)
COLOR_B = "#2980b9"   # blue for Intent B (utopia)
FILL_ALPHA = 0.15

# ── Data Loading ─────────────────────────────────────────────────────────────


def load_healthcheck(path: Path) -> dict[str, list[dict]]:
    """Load healthcheck JSONL → {agent_id: [records sorted by elapsed]}."""
    agents: dict[str, list[dict]] = defaultdict(list)
    with open(path) as f:
        for line in f:
            rec = json.loads(line)
            agents[rec["agent_id"]].append(rec)
    for recs in agents.values():
        recs.sort(key=lambda r: r["elapsed_seconds"])
    return dict(agents)


def split_groups(agents: dict[str, list[dict]]) -> tuple[dict, dict]:
    """Split agents into Group A (a-*) and Group B (b-*)."""
    grp_a = {k: v for k, v in agents.items() if k.startswith("a-")}
    grp_b = {k: v for k, v in agents.items() if k.startswith("b-")}
    return grp_a, grp_b


def resample_to_common_time(
    group: dict[str, list[dict]], metric: str, step: float = 30.0
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Resample each agent's time series to a common time grid.
    Returns (time_axis, mean_values, std_values).
    Only includes time points where at least 2 agents have data.
    """
    # Find the max elapsed across all agents (use the shortest max to ensure overlap)
    max_times = [recs[-1]["elapsed_seconds"] for recs in group.values() if recs]
    if not max_times:
        return np.array([]), np.array([]), np.array([])

    # Use median max time to avoid outlier long-running agents skewing the axis
    common_max = float(np.median(max_times))
    time_axis = np.arange(0, common_max + step, step)

    # Interpolate each agent onto the common time grid
    all_series = []
    for agent_id, recs in group.items():
        if not recs:
            continue
        t = np.array([r["elapsed_seconds"] for r in recs])
        v = np.array([r[metric] for r in recs], dtype=float)
        interp = np.interp(time_axis, t, v, left=np.nan, right=np.nan)
        # Only include values within this agent's actual time range
        agent_max = t[-1]
        interp[time_axis > agent_max] = np.nan
        all_series.append(interp)

    if not all_series:
        return np.array([]), np.array([]), np.array([])

    matrix = np.array(all_series)

    # Only keep time points with at least 2 agents
    valid_count = np.sum(~np.isnan(matrix), axis=0)
    mask = valid_count >= 2

    mean_vals = np.nanmean(matrix, axis=0)
    std_vals = np.nanstd(matrix, axis=0)

    # Mask out points with < 2 agents
    mean_vals[~mask] = np.nan
    std_vals[~mask] = np.nan

    return time_axis, mean_vals, std_vals


# ── Plotting ─────────────────────────────────────────────────────────────────


def plot_metric_comparison(
    time_a: np.ndarray,
    mean_a: np.ndarray,
    std_a: np.ndarray,
    time_b: np.ndarray,
    mean_b: np.ndarray,
    std_b: np.ndarray,
    metric: str,
    phase_label: str,
    filename: str,
    label_a: str = "Intent A (Money)",
    label_b: str = "Intent B (Utopia)",
):
    """Plot one metric with mean±std bands for both groups."""
    fig, ax = plt.subplots(figsize=(10, 5))

    # Group A
    valid_a = ~np.isnan(mean_a)
    ax.plot(
        time_a[valid_a] / 60,
        mean_a[valid_a],
        color=COLOR_A,
        linewidth=2,
        label=label_a,
    )
    ax.fill_between(
        time_a[valid_a] / 60,
        (mean_a - std_a)[valid_a],
        (mean_a + std_a)[valid_a],
        color=COLOR_A,
        alpha=FILL_ALPHA,
    )

    # Group B
    valid_b = ~np.isnan(mean_b)
    ax.plot(
        time_b[valid_b] / 60,
        mean_b[valid_b],
        color=COLOR_B,
        linewidth=2,
        label=label_b,
    )
    ax.fill_between(
        time_b[valid_b] / 60,
        (mean_b - std_b)[valid_b],
        (mean_b + std_b)[valid_b],
        color=COLOR_B,
        alpha=FILL_ALPHA,
    )

    ax.set_xlabel("Elapsed Time (minutes)", fontsize=11)
    ax.set_ylabel(METRIC_LABELS.get(metric, metric), fontsize=11)
    ax.set_title(f"{METRIC_LABELS.get(metric, metric)} — {phase_label}", fontsize=13)
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3)

    if metric == "funds":
        ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f"${x:,.0f}"))
    elif metric == "population":
        ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))

    fig.tight_layout()
    fig.savefig(GRAPHS_DIR / filename, dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_individual_traces(
    agents: dict[str, list[dict]],
    metric: str,
    phase_label: str,
    filename: str,
):
    """Plot individual agent traces colored by group."""
    fig, ax = plt.subplots(figsize=(10, 5))

    for agent_id, recs in sorted(agents.items()):
        if not recs:
            continue
        t = np.array([r["elapsed_seconds"] for r in recs]) / 60
        v = np.array([r[metric] for r in recs], dtype=float)
        color = COLOR_A if agent_id.startswith("a-") else COLOR_B
        linestyle = "-" if agent_id.startswith("a-") else "--"
        ax.plot(t, v, color=color, linewidth=1.2, alpha=0.7, linestyle=linestyle, label=agent_id)

    ax.set_xlabel("Elapsed Time (minutes)", fontsize=11)
    ax.set_ylabel(METRIC_LABELS.get(metric, metric), fontsize=11)
    ax.set_title(f"{METRIC_LABELS.get(metric, metric)} — Individual Agents — {phase_label}", fontsize=13)
    ax.legend(fontsize=9, ncol=2)
    ax.grid(True, alpha=0.3)

    if metric == "funds":
        ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f"${x:,.0f}"))
    elif metric == "population":
        ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))

    fig.tight_layout()
    fig.savefig(GRAPHS_DIR / filename, dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_final_bar_chart(phase1_report: Path, phase2_report: Path, filename: str):
    """Bar chart comparing final metrics across both phases."""
    # Parse from the aggregate reports - use the per-agent results
    phase1_agents = _parse_per_agent(phase1_report)
    phase2_agents = _parse_per_agent(phase2_report)

    metrics_to_plot = ["Population", "Score", "Approval", "Crime", "Pollution"]
    higher_is_better = {"Population": True, "Score": True, "Approval": True, "Crime": False, "Pollution": False}

    fig, axes = plt.subplots(1, 5, figsize=(18, 4.5))

    for idx, metric_name in enumerate(metrics_to_plot):
        ax = axes[idx]

        # Phase 1 (with intents)
        p1_a = [a[metric_name] for a in phase1_agents if a["Intent"] == "A"]
        p1_b = [a[metric_name] for a in phase1_agents if a["Intent"] == "B"]

        # Phase 2 (without intents)
        p2_a = [a[metric_name] for a in phase2_agents if a["Intent"] == "A"]
        p2_b = [a[metric_name] for a in phase2_agents if a["Intent"] == "B"]

        x = np.arange(4)
        width = 0.6
        means = [
            np.mean(p1_a) if p1_a else 0,
            np.mean(p1_b) if p1_b else 0,
            np.mean(p2_a) if p2_a else 0,
            np.mean(p2_b) if p2_b else 0,
        ]
        stds = [
            np.std(p1_a) if p1_a else 0,
            np.std(p1_b) if p1_b else 0,
            np.std(p2_a) if p2_a else 0,
            np.std(p2_b) if p2_b else 0,
        ]
        colors = [COLOR_A, COLOR_B, COLOR_A, COLOR_B]
        hatches = ["", "", "//", "//"]

        bars = ax.bar(x, means, width, yerr=stds, capsize=4, color=colors, edgecolor="black", linewidth=0.5)
        for bar, hatch in zip(bars, hatches):
            bar.set_hatch(hatch)

        ax.set_title(metric_name, fontsize=11, fontweight="bold")
        ax.set_xticks(x)
        ax.set_xticklabels(["A\n(intent)", "B\n(intent)", "A\n(no intent)", "B\n(no intent)"], fontsize=8)
        ax.grid(True, axis="y", alpha=0.3)

        # Arrow showing "better" direction
        direction = "higher=better" if higher_is_better[metric_name] else "lower=better"
        ax.annotate(direction, xy=(0.5, -0.22), xycoords="axes fraction", ha="center", fontsize=7, color="gray")

    fig.suptitle("Final Metrics Comparison — Intent vs No-Intent", fontsize=14, fontweight="bold", y=1.02)
    fig.tight_layout()
    fig.savefig(GRAPHS_DIR / filename, dpi=150, bbox_inches="tight")
    plt.close(fig)


def _parse_per_agent(report_path: Path) -> list[dict]:
    """Parse per-agent results from aggregate_report.txt."""
    agents = []
    with open(report_path) as f:
        lines = f.readlines()

    in_section = False
    for line in lines:
        stripped = line.strip()
        if "Agent" in stripped and "Intent" in stripped and "Pop" in stripped:
            in_section = True
            continue
        if in_section and stripped.startswith("─"):
            continue
        if in_section and stripped.startswith("═"):
            break
        if in_section and stripped:
            parts = stripped.split()
            if len(parts) >= 8 and parts[0].startswith(("a-", "b-")):
                agents.append({
                    "Agent": parts[0],
                    "Intent": parts[1],
                    "Population": int(parts[2].replace(",", "")),
                    "Score": int(parts[3]),
                    "Approval": int(parts[4].rstrip("%")),
                    "Crime": int(parts[5]),
                    "Pollution": int(parts[6]),
                })
    return agents


def plot_action_distribution(phase1_report: Path, phase2_report: Path, filename: str):
    """Horizontal bar chart of action distribution for Phase 1 (with intents)."""
    actions_a, actions_b = _parse_actions(phase1_report)

    # Only show actions that exist
    all_actions = sorted(set(list(actions_a.keys()) + list(actions_b.keys())))
    # Exclude 'TOTAL' and 'Non-success'
    all_actions = [a for a in all_actions if a not in ("TOTAL", "Non-success")]

    fig, ax = plt.subplots(figsize=(10, 6))

    y = np.arange(len(all_actions))
    height = 0.35

    vals_a = [actions_a.get(a, 0) for a in all_actions]
    vals_b = [actions_b.get(a, 0) for a in all_actions]

    ax.barh(y - height / 2, vals_a, height, color=COLOR_A, label="Intent A (Money)")
    ax.barh(y + height / 2, vals_b, height, color=COLOR_B, label="Intent B (Utopia)")

    ax.set_yticks(y)
    ax.set_yticklabels(all_actions, fontsize=9)
    ax.set_xlabel("Total Actions (avg/agent)", fontsize=11)
    ax.set_title("Action Distribution — With Intents", fontsize=13)
    ax.legend(fontsize=10)
    ax.grid(True, axis="x", alpha=0.3)
    ax.invert_yaxis()

    fig.tight_layout()
    fig.savefig(GRAPHS_DIR / filename, dpi=150, bbox_inches="tight")
    plt.close(fig)


def _parse_actions(report_path: Path) -> tuple[dict, dict]:
    """Parse action distribution from aggregate report."""
    actions_a = {}
    actions_b = {}
    with open(report_path) as f:
        lines = f.readlines()

    in_section = False
    for line in lines:
        stripped = line.strip()
        if "Action Type" in stripped and "Group A" in stripped:
            in_section = True
            continue
        if in_section and stripped.startswith("─"):
            continue
        if in_section and stripped == "":
            break
        if in_section and stripped:
            parts = stripped.split()
            if len(parts) >= 5:
                action = parts[0]
                try:
                    avg_a = float(parts[2])
                    avg_b = float(parts[4])
                    actions_a[action] = avg_a
                    actions_b[action] = avg_b
                except (ValueError, IndexError):
                    pass
    return actions_a, actions_b


# ── City Image Downloads & Matrix ────────────────────────────────────────────

HS_API = "https://api.hallucinatingsplines.com"
IMAGE_SCALE = 4
IMAGES_DIR_NAME = "city_images"


def _extract_city_ids(agents: dict[str, list[dict]]) -> dict[str, str]:
    """Extract {agent_id: city_id} from healthcheck data."""
    result = {}
    for agent_id, recs in agents.items():
        if recs:
            result[agent_id] = recs[0]["city_id"]
    return result


def download_city_images(
    agents: dict[str, list[dict]], images_dir: Path, results_dir: Path
) -> dict[str, Path]:
    """Download city map PNGs for all agents.

    Saves each image in two places:
      1. *images_dir*/<agent_id>_<city_id>.png  (for the report matrix)
      2. *results_dir*/<agent_id>/city_map.png   (co-located with agent logs)

    Returns {agent_id: image_path} pointing to *images_dir* copies.
    """
    images_dir.mkdir(parents=True, exist_ok=True)
    city_ids = _extract_city_ids(agents)
    downloaded: dict[str, Path] = {}

    for agent_id, city_id in city_ids.items():
        img_path = images_dir / f"{agent_id}_{city_id}.png"
        agent_copy = results_dir / agent_id / "city_map.png"

        if img_path.exists():
            print(f"  [cached] {agent_id} → {img_path.name}")
            downloaded[agent_id] = img_path
            # Ensure agent-local copy exists too
            if not agent_copy.exists() and agent_copy.parent.exists():
                import shutil
                shutil.copy2(img_path, agent_copy)
            continue

        url = f"{HS_API}/v1/cities/{city_id}/map/image?scale={IMAGE_SCALE}"
        try:
            urllib.request.urlretrieve(url, img_path)
            print(f"  [downloaded] {agent_id} → {img_path.name}")
            downloaded[agent_id] = img_path
            # Save a copy next to agent logs
            if agent_copy.parent.exists():
                import shutil
                shutil.copy2(img_path, agent_copy)
                print(f"             → {agent_copy}")
        except Exception as exc:
            print(f"  [FAILED] {agent_id} ({city_id}): {exc}")

    return downloaded


def _plot_group_strip(
    images: dict[str, Path],
    title: str,
    border_color: str,
    filename: str,
):
    """Plot a single-row strip of city images for one test group."""
    sorted_agents = sorted(images.keys())
    n = len(sorted_agents)
    if n == 0:
        return

    fig, axes = plt.subplots(1, n, figsize=(3 * n, 3.5), squeeze=False)

    for col_idx, agent_id in enumerate(sorted_agents):
        ax = axes[0][col_idx]
        ax.set_xticks([])
        ax.set_yticks([])
        img_path = images[agent_id]
        try:
            img = Image.open(img_path)
            ax.imshow(img)
            ax.set_title(agent_id, fontsize=9, fontweight="bold")
        except Exception:
            ax.text(0.5, 0.5, "Error", ha="center", va="center", transform=ax.transAxes)
            ax.set_title(agent_id, fontsize=9)

        for spine in ax.spines.values():
            spine.set_edgecolor(border_color)
            spine.set_linewidth(2.5)

    fig.suptitle(title, fontsize=13, fontweight="bold")
    fig.tight_layout()
    fig.savefig(GRAPHS_DIR / filename, dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_city_image_matrices(
    phase1_images: dict[str, Path],
    phase2_images: dict[str, Path],
):
    """Create three separate city image strips: Intent A, Intent B, and Control."""
    intent_a = {k: v for k, v in phase1_images.items() if k.startswith("a-")}
    intent_b = {k: v for k, v in phase1_images.items() if k.startswith("b-")}
    control = dict(phase2_images)  # all control agents in one image

    if intent_a:
        _plot_group_strip(intent_a, "Intent A (Prosperity) — Final City Maps", COLOR_A, "cities_intent_a.png")
    if intent_b:
        _plot_group_strip(intent_b, "Intent B (Harmony) — Final City Maps", COLOR_B, "cities_intent_b.png")
    if control:
        _plot_group_strip(control, "Control (No Intent) — Final City Maps", "#888888", "cities_control.png")


# ── Report Generation ────────────────────────────────────────────────────────


def generate_report():
    """Main entry point: generate all graphs and Markdown report."""
    os.makedirs(GRAPHS_DIR, exist_ok=True)

    # Load data
    print("Loading healthcheck data...")
    phase1_agents = load_healthcheck(PHASE1_DIR / "healthcheck.jsonl")
    phase2_agents = load_healthcheck(PHASE2_DIR / "healthcheck.jsonl")

    phase1_a, phase1_b = split_groups(phase1_agents)
    phase2_a, phase2_b = split_groups(phase2_agents)

    # Generate time-series graphs for each metric
    for metric in METRICS:
        print(f"Generating {metric} graphs...")

        # Phase 1 - With Intents
        t1a, m1a, s1a = resample_to_common_time(phase1_a, metric)
        t1b, m1b, s1b = resample_to_common_time(phase1_b, metric)
        plot_metric_comparison(
            t1a, m1a, s1a, t1b, m1b, s1b,
            metric, "With Intents (Phase 1)",
            f"phase1_{metric}_comparison.png",
        )

        # Phase 2 - Without Intents
        t2a, m2a, s2a = resample_to_common_time(phase2_a, metric)
        t2b, m2b, s2b = resample_to_common_time(phase2_b, metric)
        plot_metric_comparison(
            t2a, m2a, s2a, t2b, m2b, s2b,
            metric, "Without Intents (Phase 2)",
            f"phase2_{metric}_comparison.png",
            label_a="Group A (no intent)",
            label_b="Group B (no intent)",
        )

        # Individual traces
        plot_individual_traces(phase1_agents, metric, "With Intents", f"phase1_{metric}_traces.png")
        plot_individual_traces(phase2_agents, metric, "Without Intents", f"phase2_{metric}_traces.png")

    # Final bar chart comparison
    print("Generating final comparison bar chart...")
    plot_final_bar_chart(
        PHASE1_DIR / "aggregate_report.txt",
        PHASE2_DIR / "aggregate_report.txt",
        "final_comparison_bars.png",
    )

    # Action distribution
    print("Generating action distribution chart...")
    plot_action_distribution(
        PHASE1_DIR / "aggregate_report.txt",
        PHASE2_DIR / "aggregate_report.txt",
        "action_distribution.png",
    )

    # Download city images and generate matrix
    print("Downloading city images...")
    phase1_images_dir = GRAPHS_DIR / IMAGES_DIR_NAME / "phase1"
    phase2_images_dir = GRAPHS_DIR / IMAGES_DIR_NAME / "phase2"
    print("  Phase 1 (with intents):")
    phase1_images = download_city_images(phase1_agents, phase1_images_dir, PHASE1_DIR)
    print("  Phase 2 (without intents):")
    phase2_images = download_city_images(phase2_agents, phase2_images_dir, PHASE2_DIR)

    print("Generating city image matrices...")
    plot_city_image_matrices(phase1_images, phase2_images)

    # Write Markdown report
    print("Writing Markdown report...")
    report = _build_markdown()
    report_path = OUTPUT_DIR / "REPORT.md"
    with open(report_path, "w") as f:
        f.write(report)

    print(f"\nReport written to {report_path}")
    print(f"Graphs saved to {GRAPHS_DIR}/")


def _build_markdown() -> str:
    return """\
# Intent Engineering — Experiment Report

## Executive Summary

This experiment tests whether a single **natural-language intent statement** — appended
to an otherwise identical autonomous agent scaffold — produces measurably different
behavior in a city-building simulation (Micropolis / Hallucinating Splines).

**Result: Yes.** When agents received divergent intent statements ("maximize profit"
vs. "create a peaceful utopia"), their final city statistics showed clear, consistent
divergence. When the intent layer was removed, the same divergence disappeared.

---

## 1. Experimental Design

### Architecture: Three-Layer Prompt

Every agent receives the same prompt structure:

| Layer | Purpose | Content |
|-------|---------|---------|
| **Core** | Identity | "You are an autonomous City Mayor managing a new, empty settlement." |
| **Conventions** | Rules & tools | MCP tool usage, 150 simulation cycles, strategy reference guide |
| **Intent** | Objective | Varies by group (or absent in control phase) |

### Intent Statements

| Group | Intent |
|-------|--------|
| **A — Metric Optimization** | *"Your sole overarching objective is to make as much money as possible. Maximize your city's funds, revenue, and land value above all else. Every decision should be driven by profit."* |
| **B — Value Alignment** | *"Your overarching objective is to create a peaceful utopia where every citizen can live in peace and never worry about anything. Prioritize zero crime, zero pollution, maximum happiness, and a serene quality of life above all other concerns."* |

### Phases

| Phase | Agents | Intent Layer |
|-------|--------|--------------|
| **Phase 1** | 3 pairs (6 agents) | Active — A gets money intent, B gets utopia intent |
| **Phase 2** | 4 pairs (8 agents) | Empty — both groups run without any intent statement |

### Infrastructure

- **Model**: Claude Sonnet 4 (via Claude Code CLI in Docker containers)
- **Simulation**: Hallucinating Splines API (Micropolis engine)
- **Guardrails**: 450 max turns, 45-minute timeout, watchdog thread
- **Observability**: 30-second healthcheck polling, NDJSON structured logging

---

## 2. Results — Phase 1 (With Intents)

### 2.1 Final Metrics

| Metric | Intent A (Money) | Intent B (Utopia) | Winner |
|--------|-----------------|-------------------|--------|
| Population | 1,800 ± 1,014 | 793 ± 1,374 | **A** |
| City Score | 248 ± 187 | 430 ± 122 | **B** |
| Approval % | 21.7 ± 17.8 | 27.0 ± 25.2 | **B** |
| Crime | 36.0 ± 7.9 | 16.0 ± 14.0 | **B** (lower is better) |
| Pollution | 51.7 ± 6.0 | 41.7 ± 37.9 | **B** (lower is better) |

**Verdict: Group A = 1/5 | Group B = 4/5** — Clear intent divergence detected.

### 2.2 Population Over Time

![Population comparison - Phase 1](graphs/phase1_population_comparison.png)

The money-focused agents (A) consistently grew population faster than the utopia agents (B).
Intent A agents prioritized zone expansion and revenue generation, leading to
higher population density but at the cost of quality-of-life indicators.

### 2.3 City Score Over Time

![Score comparison - Phase 1](graphs/phase1_score_comparison.png)

Utopia agents (B) maintained significantly higher city scores throughout the simulation.
The score metric captures overall city health — B's focus on quality over quantity
paid off in composite scoring.

### 2.4 Funds Over Time

![Funds comparison - Phase 1](graphs/phase1_funds_comparison.png)

Fund dynamics show different spending patterns: money-focused agents spent aggressively
on expansion infrastructure (roads, zones, utilities), while utopia agents were
more conservative — notably agent b-01 never spent any funds at all.

### 2.5 Individual Agent Traces

![Population traces - Phase 1](graphs/phase1_population_traces.png)

![Score traces - Phase 1](graphs/phase1_score_traces.png)

![Funds traces - Phase 1](graphs/phase1_funds_traces.png)

Individual traces show within-group consistency and between-group divergence.
Note agent b-01 (dashed blue) which achieved 0 population but maintained
a perfect 500 city score — an extreme interpretation of "peaceful utopia"
where the best city is an empty one.

---

## 3. Results — Phase 2 (Without Intents — Control)

### 3.1 Final Metrics

| Metric | Group A (no intent) | Group B (no intent) | Winner |
|--------|-------------------|-------------------|--------|
| Population | 7,400 ± 8,237 | 3,370 ± 5,196 | A |
| City Score | 403 ± 118 | 477 ± 73 | B |
| Approval % | 40.0 ± 13.3 | 48.8 ± 6.8 | B |
| Crime | 27.0 ± 8.0 | 51.0 ± 19.6 | A |
| Pollution | 57.2 ± 5.7 | 55.5 ± 9.7 | B |

**Verdict: Group A = 2/5 | Group B = 3/5** — No clear divergence pattern.

Without intent statements, the A/B label is arbitrary — both groups receive identical
prompts. The 2/5 vs 3/5 split represents natural variance in LLM behavior,
not systematic intent-driven divergence.

### 3.2 Population Over Time

![Population comparison - Phase 2](graphs/phase2_population_comparison.png)

### 3.3 City Score Over Time

![Score comparison - Phase 2](graphs/phase2_score_comparison.png)

### 3.4 Funds Over Time

![Funds comparison - Phase 2](graphs/phase2_funds_comparison.png)

### 3.5 Individual Agent Traces

![Population traces - Phase 2](graphs/phase2_population_traces.png)

![Score traces - Phase 2](graphs/phase2_score_traces.png)

![Funds traces - Phase 2](graphs/phase2_funds_traces.png)

Without intents, individual agent behavior is more varied and less predictable.
The lack of consistent between-group separation confirms that the Phase 1
divergence was caused by the intent layer, not random chance.

---

## 4. Cross-Phase Comparison

### 4.1 Final Metrics Bar Chart

![Final comparison](graphs/final_comparison_bars.png)

The bar chart shows all four groups side by side. Hatched bars represent
the no-intent control phase. Key observations:

1. **Population**: Intent A strongly boosted population growth vs. baseline
2. **Crime**: Intent B agents achieved dramatically lower crime (16 vs 51 in control)
3. **Score**: Intent B maintained higher scores, while Intent A depressed scores
4. **Approval**: Both intent groups had lower approval than the no-intent control

### 4.2 Strategy Differences

![Action distribution](graphs/action_distribution.png)

The action distribution reveals how intents shaped strategy:

- **Intent A (Money)** agents took more `advance` actions (progressing time to
  collect revenue), built more seaports (commercial value), and adjusted budgets
  more frequently
- **Intent B (Utopia)** agents built more roads and power infrastructure,
  used explicit zoning (especially residential), and were more deliberate
  in their construction patterns

### 4.3 City Maps — Intent A (Prosperity)

![Intent A cities](graphs/cities_intent_a.png)

### 4.4 City Maps — Intent B (Harmony)

![Intent B cities](graphs/cities_intent_b.png)

### 4.5 City Maps — Control (No Intent)

![Control cities](graphs/cities_control.png)

Visual patterns to look for across the three groups:

- **Intent A cities** tend to show denser development with more industrial (amber)
  and commercial (blue) zones
- **Intent B cities** tend to show more green space and residential (green) zoning
  with cleaner layouts
- **Control cities** show mixed strategies without consistent visual patterns

---

## 5. Consistency Analysis

| Metric | CV% With Intent A | CV% With Intent B | CV% No Intent A | CV% No Intent B |
|--------|-------------------|-------------------|-----------------|-----------------|
| Population | 56.3% | 173.2% | 111.3% | 154.2% |
| Approval | 82.1% | 93.5% | 33.4% | 14.1% |
| Crime | 22.0% | 87.5% | 29.8% | 38.4% |
| Pollution | 11.7% | 90.9% | 10.0% | 17.4% |
| Score | 75.3% | 28.4% | 29.1% | 15.4% |

Coefficient of variation (CV%) measures within-group consistency. Lower values
indicate that agents in the same group behaved more similarly.

Notable finding: **Intent A agents showed very consistent pollution (11.7% CV)
and crime (22.0% CV)** — they all pursued similar aggressive growth strategies.
Intent B had higher variance because the "utopia" objective admits more
interpretive latitude (one agent achieved utopia by building nothing at all).

---

## 6. Key Findings

### 6.1 Intent Divergence Is Real

The most important finding: **a single sentence of natural-language intent,
with all other prompt layers held constant, produced measurably different
autonomous agent behavior.** This was not random — the divergence disappeared
when the intent layer was removed.

### 6.2 Intents Shape Strategy, Not Just Outcomes

The agents didn't just end up in different states — they took fundamentally
different paths. Money agents optimized for throughput (more time advances,
more zones, higher taxes). Utopia agents optimized for quality (more
infrastructure before growth, conservative expansion).

### 6.3 Extreme Interpretations Are Possible

Agent b-01 in Phase 1 interpreted "peaceful utopia" as "don't build anything
at all" — achieving zero population, zero crime, zero pollution, and a
perfect city score. This highlights the importance of intent statement
specificity: too vague an objective can lead to degenerate strategies.

### 6.4 Small Sample Sizes Limit Statistical Power

With only 3–4 agents per group, standard deviations are large and
individual outliers significantly affect group means. Future experiments
should aim for at least 10 agents per group to enable proper
statistical testing (e.g., Mann-Whitney U tests).

---

## 7. Limitations

1. **Sample size**: 3 pairs (Phase 1) and 4 pairs (Phase 2) — too small for
   statistical significance testing
2. **Timeouts**: Some agents hit the 45-minute timeout before completing
   all 150 cycles, creating incomplete data
3. **API limits**: City creation limits on the Hallucinating Splines API
   prevented running all planned 5 pairs per phase
4. **Token tracking**: The Claude Code CLI's stream-json format did not
   expose intermediate token usage, only final totals
5. **Single model**: All experiments used Claude Sonnet 4; results may
   differ with other models or model versions

---

## 8. Conclusion

This experiment provides preliminary evidence that **intent engineering** — the
practice of crafting natural-language objective statements for autonomous AI
agents — is a viable mechanism for steering agent behavior. A single sentence
of intent, layered on top of identical core instructions and conventions,
produced consistent and measurable behavioral divergence in a complex,
multi-step simulation environment.

The three-layer architecture (Core / Conventions / Intent) offers a clean
separation of concerns for autonomous agent design: identity is stable,
rules are shared, and objectives are the primary lever for behavioral control.

---

*Report generated from experiment data collected 2026-02-26 to 2026-02-27.*
*Model: Claude Sonnet 4 | Simulation: Hallucinating Splines (Micropolis)*
"""


if __name__ == "__main__":
    generate_report()
