#!/usr/bin/env python3
"""
Intent Engineering Experiment — Parallel Pool Runner
=====================================================
Thin entry-point. All logic lives in src.runner.cli.

Usage:
    python3 run_experiment.py                   # 10 agents (5A + 5B)
    python3 run_experiment.py -n 20             # 20 agents (10A + 10B)
    python3 run_experiment.py -n 6 --batch 3    # 6 agents, 3 at a time
"""

from src.runner.cli import main

if __name__ == "__main__":
    main()
