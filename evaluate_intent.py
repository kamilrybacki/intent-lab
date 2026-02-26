#!/usr/bin/env python3
"""
Intent Engineering Experiment — Evaluation Script
==================================================
Thin entry-point. All logic lives in src.evaluator.

Modes:
  Single pair:   python3 evaluate_intent.py <city_a_id> <city_b_id>
  Pool (meta):   python3 evaluate_intent.py --meta experiment_meta.json
  All runs:      python3 evaluate_intent.py --all-runs
"""

from src.evaluator.cli import main

if __name__ == "__main__":
    main()
