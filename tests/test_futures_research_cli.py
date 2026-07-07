from __future__ import annotations

import csv
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from agent_office import cli
from agent_office.futures_research import REQUIRED_DATASETS


def run_cli(argv: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        exit_code = cli.main(argv)
    return exit_code, stdout.getvalue(), stderr.getvalue()


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def build_data_lake(root: Path, *, full: bool) -> Path:
    lake = root / "data_lake"
    ohlcv = []
    base_ts = 1_700_000_000
    price = 100.0
    for index in range(80):
        ts = base_ts + index * 60
        price += 0.35 if index < 45 else -0.12
        ohlcv.append({"timestamp": ts, "open": price, "high": price + 1.2, "low": price - 0.9, "close": price + 0.2, "volume": 1000 + index * 3})
    write_csv(lake / "ohlcv.csv", ohlcv)
    if not full:
        return lake
    funding = []
    premium = []
    open_interest = []
    long_short = []
    taker = []
    liquidation = []
    orderflow = []
    basis = []
    vol_structure = []
    for index, row in enumerate(ohlcv):
        ts = row["timestamp"]
        funding.append({"timestamp": ts, "funding_rate": -0.0002 + index * 0.00001})
        premium.append({"timestamp": ts, "premium": 0.0005 + index * 0.000001})
        open_interest.append({"timestamp": ts, "open_interest": 10_000 + index * 25})
        long_short.append({"timestamp": ts, "long_short_ratio": 0.9 + (index % 9) * 0.04})
        taker.append({"timestamp": ts, "buy_volume": 600 + index * 4, "sell_volume": 450 + index * 2})
        liquidation.append({"timestamp": ts, "long_liquidation": index % 5, "short_liquidation": (index + 2) % 5})
        orderflow.append({"timestamp": ts, "delta": 10 + index})
        basis.append({"timestamp": ts, "basis": 0.002 + index * 0.00001})
        vol_structure.append({"timestamp": ts, "term_structure": 0.01 + index * 0.0001})
    for name, rows in {
        "funding": funding,
        "premium": premium,
        "open_interest": open_interest,
        "long_short_ratio": long_short,
        "taker_buy_sell": taker,
        "liquidation": liquidation,
        "orderflow": orderflow,
        "basis": basis,
        "volatility_structure": vol_structure,
    }.items():
        write_csv(lake / f"{name}.csv", rows)
    return lake


class FuturesResearchCliTests(unittest.TestCase):
    maxDiff = None

    def test_audit_records_missing_datasets_without_fabrication(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            lake = build_data_lake(root, full=False)
            out = root / "feature_store"
            code, stdout, stderr = run_cli(["futures-research", "audit", "--data-lake", str(lake), "--out", str(out), "--json"])

        self.assertEqual(code, 2)
        self.assertEqual(stderr, "")
        payload = json.loads(stdout)
        self.assertFalse(payload["ok"])
        self.assertIn("open_interest", payload["missing_datasets"])
        self.assertTrue(payload["no_fake_data"])
        self.assertTrue(payload["no_interpolation"])
        self.assertEqual(len(payload["datasets"]), len(REQUIRED_DATASETS))
        failed = [item for item in payload["datasets"] if item["name"] == "open_interest"][0]
        self.assertEqual(failed["source_status"], "missing")
        self.assertEqual(failed["quality"]["error"], "dataset_missing")

    def test_full_loop_builds_features_walk_forward_failure_memory_and_research_layers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            lake = build_data_lake(root, full=True)
            feature_store = root / "feature_store"
            trial_store = root / "trial_store"
            loop_args = [
                "futures-research",
                "loop",
                "--data-lake",
                str(lake),
                "--feature-store",
                str(feature_store),
                "--trial-store",
                str(trial_store),
                "--strategy",
                "all",
                "--json",
            ]
            code, stdout, stderr = run_cli(loop_args)
            self.assertEqual(code, 0, stdout + stderr)
            code, stdout, stderr = run_cli(loop_args)

            features = [json.loads(line) for line in (feature_store / "features.jsonl").read_text(encoding="utf-8").splitlines()]
            latest = json.loads((trial_store / "latest_trial.json").read_text(encoding="utf-8"))
            edge_search = json.loads((trial_store / "edge_search" / "latest_edge_search.json").read_text(encoding="utf-8"))
            memory_files = list((trial_store / "strategy_memory").glob("*/*.json"))

        self.assertEqual(code, 0, stdout + stderr)
        payload = json.loads(stdout)
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["trading_allowed"])
        self.assertEqual(payload["feature_store"]["feature_version"], "futures_feature_v2.0")
        self.assertTrue(payload["feature_store"]["exact_timestamp_join"])
        self.assertTrue(payload["feature_store"]["no_interpolation"])
        self.assertEqual(len(features), 80)
        self.assertTrue(all(row["feature_version"] == "futures_feature_v2.0" for row in features))
        self.assertTrue(all(row.get("source_hash") for row in features))
        self.assertIn("funding_zscore", features[-1])
        self.assertIn("oi_acceleration", features[-1])
        self.assertIn("taker_imbalance", features[-1])
        self.assertIn("market_regime", features[-1])
        self.assertEqual(latest["status"], "TARGET_FAILED")
        self.assertFalse(latest["trading_allowed"])
        self.assertFalse(latest["paper_trading_started"])
        self.assertFalse(latest["private_api_touched"])
        self.assertEqual(latest["source_lineage"]["feature_version"], "futures_feature_v2.0")
        self.assertTrue(latest["source_lineage"]["no_fake_data"])
        self.assertTrue(latest["source_lineage"]["no_interpolation"])
        self.assertEqual(len(latest["source_lineage"]["datasets"]), len(REQUIRED_DATASETS))
        self.assertEqual(set(latest["strategy_memory_summary"]), {item["strategy"] for item in latest["strategies"]})
        self.assertEqual(latest["edge_search"], edge_search)
        self.assertEqual(latest["edge_search"]["kind"], "agentoffice.futures_research.edge_search.v2")
        self.assertEqual(latest["edge_search"]["status"], "EDGE_NOT_FOUND")
        self.assertFalse(latest["edge_search"]["trading_allowed"])
        self.assertFalse(latest["edge_search"]["paper_trading_started"])
        self.assertFalse(latest["edge_search"]["private_api_touched"])
        self.assertEqual(len(latest["edge_search"]["candidates"]), 7)
        self.assertEqual(latest["chrono_dual"]["macro_model"], "TimesFM")
        self.assertEqual(latest["chrono_dual"]["micro_model"], "Kronos")
        self.assertFalse(latest["chrono_dual"]["model_calls"])
        self.assertEqual(len(latest["strategies"]), 7)
        self.assertEqual(len(memory_files), 7)
        self.assertTrue(any(item["strategy_memory"]["repeated_failure_reasons"] for item in latest["strategies"]))
        self.assertTrue(all("edge_score" in item for item in latest["edge_search"]["candidates"]))
        self.assertTrue(all(item["research_action"] in {"candidate_review", "avoid_repeat_without_new_evidence", "research_new_hypothesis"} for item in latest["edge_search"]["candidates"]))
        self.assertTrue(any("repeated_failure_memory" in item["blockers"] for item in latest["edge_search"]["candidates"]))
        for strategy in latest["strategies"]:
            validation = strategy["walk_forward"]["validation_standard"]
            self.assertFalse(validation["random_split"])
            self.assertFalse(validation["future_leakage"])
            self.assertFalse(validation["same_bar_fill"])
            self.assertTrue(validation["train_validation_oos"])
            for metric in ("pf", "avgR", "sharpe", "dd", "trade_count", "cost_impact", "stability"):
                self.assertIn(metric, strategy["walk_forward"]["overall"]["metrics"])
            for segment in ("train", "validation", "oos"):
                self.assertIn(segment, strategy["walk_forward"]["segments"])
            for trade in strategy["walk_forward"]["overall"]["trades"]:
                self.assertGreater(trade["entry_timestamp"], trade["signal_timestamp"])
                self.assertFalse(trade["same_bar_fill"])
            self.assertIn(strategy["failure_report"]["status"], {"failed", "review"})
            self.assertIn(strategy["failure_report"]["research_recommendation"], {"avoid_repeat_without_new_features", "review_with_new_hypothesis"})
            self.assertGreaterEqual(strategy["strategy_memory"]["prior_trials"], 1)
            self.assertIn("repeated_failure_reasons", strategy["strategy_memory"])
            self.assertEqual(strategy["meta_label"]["target"], "signal_execution_probability_not_direction_prediction")
            self.assertIn("logistic_regression", strategy["meta_label"]["models"])
            self.assertIn("gradient_boosting", strategy["meta_label"]["models"])
            self.assertIn("random_forest", strategy["meta_label"]["models"])


if __name__ == "__main__":
    unittest.main()
