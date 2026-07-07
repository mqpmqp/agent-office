from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


FEATURE_VERSION = "futures_feature_v2.0"
RESEARCH_VERSION = "futures_research_v2.0"
REQUIRED_DATASETS = (
    "ohlcv",
    "funding",
    "premium",
    "open_interest",
    "long_short_ratio",
    "taker_buy_sell",
    "liquidation",
    "orderflow",
    "basis",
    "volatility_structure",
)
STRATEGIES = (
    "momentum",
    "mean_reversion",
    "breakout",
    "funding_carry",
    "oi_divergence",
    "orderflow",
    "regime_strategy",
)


class FuturesResearchError(RuntimeError):
    pass


@dataclass(frozen=True)
class DatasetAudit:
    name: str
    status: str
    path: str | None
    checksum: str | None
    rows: int
    coverage: dict[str, Any]
    quality: dict[str, Any]
    source_status: str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def write_json(path: Path, payload: Any) -> None:
    atomic_write(path, json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n")



def read_json_file(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_dataset_name(name: str) -> str:
    return name.strip().lower().replace("-", "_").replace(" ", "_")


def dataset_candidates(data_lake: Path, dataset: str) -> list[Path]:
    names = {dataset, dataset.replace("_", "-"), dataset.replace("_", "")}
    suffixes = {".csv", ".json", ".jsonl", ".ndjson"}
    candidates = []
    for path in data_lake.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in suffixes:
            continue
        stem = normalize_dataset_name(path.stem)
        parent = normalize_dataset_name(path.parent.name)
        if stem in names or parent in names:
            candidates.append(path)
    return sorted(candidates, key=lambda item: (len(item.parts), str(item)))


def parse_timestamp(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = int(value)
        return number // 1000 if number > 10_000_000_000 else number
    text = str(value).strip()
    if not text:
        return None
    try:
        number = int(float(text))
        return number // 1000 if number > 10_000_000_000 else number
    except ValueError:
        pass
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp())


def timestamp_value(row: dict[str, Any]) -> int | None:
    for key in ("timestamp", "time", "open_time", "close_time", "date", "datetime"):
        if key in row:
            parsed = parse_timestamp(row.get(key))
            if parsed is not None:
                return parsed
    return None


def numeric(value: Any) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(float(value)) else None
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        parsed = float(text)
    except ValueError:
        return None
    return parsed if math.isfinite(parsed) else None


def first_number(row: dict[str, Any], keys: Iterable[str]) -> float | None:
    for key in keys:
        if key in row:
            parsed = numeric(row.get(key))
            if parsed is not None:
                return parsed
    return None


def load_rows(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            return [dict(row) for row in csv.DictReader(fh)]
    if suffix in {".jsonl", ".ndjson"}:
        rows = []
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise FuturesResearchError(f"JSONL rows must be objects: {path}")
                rows.append(value)
        return rows
    if suffix == ".json":
        value = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(value, list):
            if not all(isinstance(item, dict) for item in value):
                raise FuturesResearchError(f"JSON arrays must contain objects: {path}")
            return list(value)
        if isinstance(value, dict) and isinstance(value.get("rows"), list):
            rows = value["rows"]
            if not all(isinstance(item, dict) for item in rows):
                raise FuturesResearchError(f"JSON rows must contain objects: {path}")
            return list(rows)
        raise FuturesResearchError(f"Unsupported JSON dataset shape: {path}")
    raise FuturesResearchError(f"Unsupported dataset file type: {path}")


def coverage_for(rows: list[dict[str, Any]]) -> dict[str, Any]:
    timestamps = sorted(ts for ts in (timestamp_value(row) for row in rows) if ts is not None)
    return {
        "start_ts": timestamps[0] if timestamps else None,
        "end_ts": timestamps[-1] if timestamps else None,
        "points": len(timestamps),
        "unique_points": len(set(timestamps)),
    }


def dataset_quality(rows: list[dict[str, Any]]) -> dict[str, Any]:
    timestamps = [timestamp_value(row) for row in rows]
    valid = [item for item in timestamps if item is not None]
    sorted_valid = sorted(valid)
    gap_count = 0
    if len(sorted_valid) > 2:
        diffs = [b - a for a, b in zip(sorted_valid, sorted_valid[1:]) if b > a]
        if diffs:
            expected = int(statistics.median(diffs))
            gap_count = sum(1 for diff in diffs if expected > 0 and diff > expected * 1.5)
    return {
        "rows": len(rows),
        "timestamp_valid_rows": len(valid),
        "timestamp_missing_rows": len(rows) - len(valid),
        "duplicate_timestamps": len(valid) - len(set(valid)),
        "large_gap_count": gap_count,
        "no_interpolation_applied": True,
    }


def audit_data_lake(data_lake: str | Path, out: str | Path) -> dict[str, Any]:
    lake = Path(data_lake)
    output = Path(out)
    if not lake.exists() or not lake.is_dir():
        raise FuturesResearchError(f"data_lake_missing: {lake}")
    audits = []
    for dataset in REQUIRED_DATASETS:
        candidates = dataset_candidates(lake, dataset)
        if not candidates:
            audit = DatasetAudit(
                dataset,
                "failed",
                None,
                None,
                0,
                {"start_ts": None, "end_ts": None, "points": 0, "unique_points": 0},
                {"rows": 0, "error": "dataset_missing", "no_interpolation_applied": True},
                "missing",
            )
        else:
            path = candidates[0]
            try:
                rows = load_rows(path)
                quality = dataset_quality(rows)
                status = "ready" if rows and quality["timestamp_missing_rows"] == 0 else "degraded"
                source_status = "available" if status == "ready" else "available_with_quality_warnings"
                audit = DatasetAudit(dataset, status, str(path), sha256_file(path), len(rows), coverage_for(rows), quality, source_status)
            except Exception as exc:
                audit = DatasetAudit(
                    dataset,
                    "failed",
                    str(path),
                    sha256_file(path) if path.exists() else None,
                    0,
                    {"start_ts": None, "end_ts": None, "points": 0, "unique_points": 0},
                    {"rows": 0, "error": f"dataset_read_failed:{type(exc).__name__}", "detail": str(exc), "no_interpolation_applied": True},
                    "read_failed",
                )
        audits.append(audit)
        dataset_dir = output / "data_audit" / dataset
        write_json(
            dataset_dir / "manifest.json",
            {
                "dataset": audit.name,
                "status": audit.status,
                "path": audit.path,
                "checksum": audit.checksum,
                "coverage": audit.coverage,
                "source_status": audit.source_status,
                "created_at": utc_now(),
            },
        )
        write_json(dataset_dir / "quality_report.json", audit.quality)
    payload = {
        "kind": "agentoffice.futures_research.data_audit.v2",
        "ok": all(audit.status in {"ready", "degraded"} for audit in audits),
        "data_lake": str(lake),
        "out": str(output),
        "datasets": [audit.__dict__ for audit in audits],
        "missing_datasets": [audit.name for audit in audits if audit.status == "failed"],
        "no_fake_data": True,
        "no_interpolation": True,
        "created_at": utc_now(),
    }
    write_json(output / "data_audit" / "audit.json", payload)
    return payload


def load_audited_datasets(audit: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    loaded = {}
    for item in audit["datasets"]:
        path = item.get("path")
        if item.get("status") in {"ready", "degraded"} and path:
            loaded[item["name"]] = sorted(load_rows(Path(path)), key=lambda row: timestamp_value(row) or -1)
    return loaded


def index_by_timestamp(rows: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    indexed = {}
    for row in rows:
        ts = timestamp_value(row)
        if ts is not None and ts not in indexed:
            indexed[ts] = row
    return indexed


def mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def stdev(values: list[float]) -> float | None:
    return statistics.pstdev(values) if len(values) >= 2 else None


def rolling(values: list[float], window: int) -> list[float]:
    return values[-window:]


def zscore(value: float | None, history: list[float]) -> float | None:
    if value is None or len(history) < 3:
        return None
    avg = mean(history)
    sd = stdev(history)
    if avg is None or sd in {None, 0}:
        return None
    return (value - avg) / sd


def classify_trend(close: float, slow_avg: float | None) -> str:
    if slow_avg is None:
        return "unknown"
    if close > slow_avg * 1.002:
        return "up"
    if close < slow_avg * 0.998:
        return "down"
    return "flat"


def classify_volatility(volatility: float | None, history: list[float]) -> str:
    if volatility is None or len(history) < 5:
        return "unknown"
    avg = mean(history)
    if avg is None:
        return "unknown"
    if volatility > avg * 1.5:
        return "high"
    if volatility < avg * 0.7:
        return "low"
    return "normal"


def build_feature_store(data_lake: str | Path, feature_store: str | Path) -> dict[str, Any]:
    store = Path(feature_store)
    audit = audit_data_lake(data_lake, store)
    datasets = load_audited_datasets(audit)
    ohlcv = datasets.get("ohlcv", [])
    if not ohlcv:
        payload = {
            "kind": "agentoffice.futures_research.feature_store.v2",
            "ok": False,
            "status": "failed",
            "reason": "ohlcv_required",
            "feature_version": FEATURE_VERSION,
            "source_hash": sha256_text(json.dumps(audit, sort_keys=True)),
            "rows": 0,
            "trading_allowed": False,
        }
        write_json(store / "manifest.json", payload)
        return payload

    indexes = {name: index_by_timestamp(rows) for name, rows in datasets.items() if name != "ohlcv"}
    closes: list[float] = []
    volumes: list[float] = []
    returns: list[float] = []
    true_ranges: list[float] = []
    funding_values: list[float] = []
    oi_changes: list[float] = []
    feature_rows = []
    exact_join_misses = {name: 0 for name in indexes}

    for row in ohlcv:
        ts = timestamp_value(row)
        open_price = first_number(row, ("open", "o"))
        high = first_number(row, ("high", "h"))
        low = first_number(row, ("low", "l"))
        close = first_number(row, ("close", "c"))
        volume = first_number(row, ("volume", "base_volume", "vol", "v"))
        if ts is None or open_price is None or high is None or low is None or close is None:
            continue
        prev_close = closes[-1] if closes else None
        ret = None if prev_close in {None, 0} else close / prev_close - 1.0
        if ret is not None:
            returns.append(ret)
        true_ranges.append(max(high - low, abs(high - prev_close), abs(low - prev_close)) if prev_close is not None else high - low)
        closes.append(close)
        volumes.append(volume or 0.0)

        joined = {}
        for name, index in indexes.items():
            joined[name] = index.get(ts)
            if joined[name] is None:
                exact_join_misses[name] += 1

        funding = first_number(joined.get("funding") or {}, ("funding_rate", "funding", "rate", "value"))
        funding_z = zscore(funding, funding_values[-30:])
        funding_change = None if funding is None or not funding_values else funding - funding_values[-1]
        if funding is not None:
            funding_values.append(funding)
        premium = first_number(joined.get("premium") or {}, ("premium", "premium_index", "mark_premium", "spread", "value"))
        basis = first_number(joined.get("basis") or {}, ("basis", "annualized_basis", "spread", "value"))
        oi = first_number(joined.get("open_interest") or {}, ("open_interest", "oi", "sumOpenInterest", "value"))
        prev_oi = feature_rows[-1].get("open_interest") if feature_rows else None
        oi_change = None if oi is None or prev_oi in {None, 0} else oi / float(prev_oi) - 1.0
        oi_acceleration = None if oi_change is None or not oi_changes else oi_change - oi_changes[-1]
        if oi_change is not None:
            oi_changes.append(oi_change)
        oi_price_divergence = oi_change - ret if oi_change is not None and ret is not None else None
        long_short = first_number(joined.get("long_short_ratio") or {}, ("long_short_ratio", "longShortRatio", "ratio", "value"))
        long_short_imbalance = long_short - 1.0 if long_short is not None else None
        taker_buy = first_number(joined.get("taker_buy_sell") or {}, ("buy_volume", "taker_buy_volume", "buyVol", "buy"))
        taker_sell = first_number(joined.get("taker_buy_sell") or {}, ("sell_volume", "taker_sell_volume", "sellVol", "sell"))
        taker_total = (taker_buy or 0.0) + (taker_sell or 0.0)
        taker_imbalance = None if taker_total == 0 else ((taker_buy or 0.0) - (taker_sell or 0.0)) / taker_total
        volume_delta = None if taker_buy is None and taker_sell is None else (taker_buy or 0.0) - (taker_sell or 0.0)
        liq_long = first_number(joined.get("liquidation") or {}, ("long_liquidation", "longLiquidation", "long", "sell_liquidation"))
        liq_short = first_number(joined.get("liquidation") or {}, ("short_liquidation", "shortLiquidation", "short", "buy_liquidation"))
        liquidation_imbalance = None
        if liq_long is not None or liq_short is not None:
            liq_total = (liq_long or 0.0) + (liq_short or 0.0)
            liquidation_imbalance = None if liq_total == 0 else ((liq_short or 0.0) - (liq_long or 0.0)) / liq_total
        orderflow_delta = first_number(joined.get("orderflow") or {}, ("delta", "volume_delta", "imbalance", "value"))
        vol_term = first_number(joined.get("volatility_structure") or {}, ("term_structure", "vol_spread", "iv_spread", "value"))
        fast_avg = mean(rolling(closes, 5))
        slow_avg = mean(rolling(closes, 20))
        volatility = stdev(rolling(returns, 20)) if returns else None
        atr = mean(rolling(true_ranges, 14))
        momentum = None if len(closes) <= 10 or closes[-11] == 0 else close / closes[-11] - 1.0
        volume_ma = mean(rolling(volumes, 20))
        volume_change = None if volume_ma in {None, 0} else (volume or 0.0) / volume_ma - 1.0
        trend = None if fast_avg is None or slow_avg is None else fast_avg / slow_avg - 1.0
        trend_state = classify_trend(close, slow_avg)
        prior_vol = [item["volatility"] for item in feature_rows if item.get("volatility") is not None]
        volatility_state = classify_volatility(volatility, prior_vol)
        crowding_inputs = [abs(value) for value in (funding_z, long_short_imbalance, oi_change, taker_imbalance) if value is not None]
        crowding_score = min(1.0, sum(crowding_inputs) / len(crowding_inputs)) if crowding_inputs else None
        market_regime = f"{trend_state}_{volatility_state}_vol" if trend_state != "unknown" and volatility_state != "unknown" else "unknown"

        feature_rows.append(
            {
                "timestamp": ts,
                "feature_version": FEATURE_VERSION,
                "source_hash": sha256_text(json.dumps({"audit_hash": audit["created_at"], "timestamp": ts}, sort_keys=True)),
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
                "returns": ret,
                "volatility": volatility,
                "atr": atr,
                "trend": trend,
                "momentum": momentum,
                "volume_change": volume_change,
                "funding_rate": funding,
                "funding_zscore": funding_z,
                "funding_change": funding_change,
                "premium_spread": premium,
                "basis": basis,
                "open_interest": oi,
                "oi_change": oi_change,
                "oi_acceleration": oi_acceleration,
                "oi_price_divergence": oi_price_divergence,
                "long_short_ratio": long_short,
                "long_short_imbalance": long_short_imbalance,
                "taker_imbalance": taker_imbalance,
                "buy_sell_pressure": taker_imbalance,
                "volume_delta": volume_delta,
                "liquidation_imbalance": liquidation_imbalance,
                "orderflow_delta": orderflow_delta,
                "volatility_term_structure": vol_term,
                "market_regime": market_regime,
                "trend_state": trend_state,
                "volatility_state": volatility_state,
                "crowding_score": crowding_score,
            }
        )

    rows_path = store / "features.jsonl"
    atomic_write(rows_path, "".join(json.dumps(row, sort_keys=True) + "\n" for row in feature_rows))
    manifest = {
        "kind": "agentoffice.futures_research.feature_store.v2",
        "ok": bool(feature_rows),
        "status": "ready" if feature_rows else "failed",
        "feature_version": FEATURE_VERSION,
        "source_hash": sha256_text(json.dumps(audit, sort_keys=True)),
        "rows": len(feature_rows),
        "path": str(rows_path),
        "exact_timestamp_join": True,
        "no_interpolation": True,
        "join_misses": exact_join_misses,
        "created_at": utc_now(),
        "trading_allowed": False,
    }
    write_json(store / "manifest.json", manifest)
    write_json(
        store / "quality_report.json",
        {
            "rows": len(feature_rows),
            "null_counts": {key: sum(1 for row in feature_rows if row.get(key) is None) for key in feature_rows[0]} if feature_rows else {},
            "no_interpolation_applied": True,
            "exact_join_misses": exact_join_misses,
        },
    )
    return manifest


def load_features(feature_store: str | Path) -> list[dict[str, Any]]:
    path = Path(feature_store) / "features.jsonl"
    if not path.exists():
        raise FuturesResearchError(f"feature_store_missing: {path}")
    return sorted((json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()), key=lambda row: row["timestamp"])



def feature_source_summary(feature_store: str | Path) -> dict[str, Any]:
    store = Path(feature_store)
    manifest = read_json_file(store / "manifest.json") or {}
    audit = read_json_file(store / "data_audit" / "audit.json") or {}
    datasets = []
    for item in audit.get("datasets", []):
        if not isinstance(item, dict):
            continue
        datasets.append(
            {
                "name": item.get("name"),
                "status": item.get("status"),
                "checksum": item.get("checksum"),
                "coverage": item.get("coverage"),
                "source_status": item.get("source_status"),
            }
        )
    return {
        "feature_version": manifest.get("feature_version"),
        "source_hash": manifest.get("source_hash"),
        "rows": manifest.get("rows"),
        "exact_timestamp_join": bool(manifest.get("exact_timestamp_join")),
        "no_interpolation": bool(manifest.get("no_interpolation")) and bool(audit.get("no_interpolation", True)),
        "no_fake_data": bool(audit.get("no_fake_data", True)),
        "join_misses": manifest.get("join_misses", {}),
        "datasets": datasets,
    }

def read_strategy_memory(store: Path, strategy: str, limit: int = 20) -> dict[str, Any]:
    memory_dir = store / "strategy_memory" / strategy
    files = sorted(memory_dir.glob("*.json"))[-limit:] if memory_dir.exists() else []
    status_counts: dict[str, int] = {}
    reason_counts: dict[str, int] = {}
    recent_reports = []
    malformed = 0
    for report_path in files:
        try:
            report = read_json_file(report_path) or {}
        except Exception:
            malformed += 1
            continue
        status = str(report.get("status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        reasons = [str(reason) for reason in report.get("failure_reasons", []) if reason]
        for reason in reasons:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
        recent_reports.append({"trial_file": report_path.name, "status": status, "failure_reasons": reasons})
    return {
        "prior_trials": sum(status_counts.values()),
        "prior_failed_trials": status_counts.get("failed", 0),
        "status_counts": status_counts,
        "historical_failure_reasons": dict(sorted(reason_counts.items())),
        "recent_reports": recent_reports,
        "malformed_reports": malformed,
    }


def signal_for(strategy: str, row: dict[str, Any]) -> int:
    if strategy == "momentum":
        value = row.get("momentum")
        return 1 if value is not None and value > 0.003 else -1 if value is not None and value < -0.003 else 0
    if strategy == "mean_reversion":
        value = row.get("returns")
        return -1 if value is not None and value > 0.01 else 1 if value is not None and value < -0.01 else 0
    if strategy == "breakout":
        if row.get("trend_state") == "up" and row.get("volatility_state") in {"normal", "high"}:
            return 1
        if row.get("trend_state") == "down" and row.get("volatility_state") in {"normal", "high"}:
            return -1
        return 0
    if strategy == "funding_carry":
        value = row.get("funding_zscore")
        return -1 if value is not None and value > 1.5 else 1 if value is not None and value < -1.5 else 0
    if strategy == "oi_divergence":
        value = row.get("oi_price_divergence")
        return -1 if value is not None and value > 0.02 else 1 if value is not None and value < -0.02 else 0
    if strategy == "orderflow":
        value = row.get("taker_imbalance") if row.get("taker_imbalance") is not None else row.get("orderflow_delta")
        return 1 if value is not None and value > 0.2 else -1 if value is not None and value < -0.2 else 0
    if strategy == "regime_strategy":
        if row.get("market_regime") == "up_normal_vol" and (row.get("crowding_score") or 0) < 0.8:
            return 1
        if row.get("market_regime") == "down_normal_vol" and (row.get("crowding_score") or 0) < 0.8:
            return -1
        return 0
    raise FuturesResearchError(f"unknown_strategy: {strategy}")


def split_walk_forward(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    count = len(rows)
    train_end = max(1, int(count * 0.6))
    validation_end = max(train_end + 1, int(count * 0.8)) if count >= 3 else count
    return {"train": rows[:train_end], "validation": rows[train_end:validation_end], "oos": rows[validation_end:]}


def stability_score(pf: float | None, sharpe: float | None, trade_count: int) -> float:
    if trade_count == 0:
        return 0.0
    pf_score = min(1.0, (pf or 0.0) / 2.0)
    sharpe_score = min(1.0, max(0.0, (sharpe or 0.0) / 2.0))
    sample_score = min(1.0, trade_count / 30.0)
    return round((pf_score + sharpe_score + sample_score) / 3.0, 6)


def simulate(rows: list[dict[str, Any]], strategy: str, *, cost_bps: float, slippage_bps: float, holding_period: int) -> dict[str, Any]:
    trades = []
    total_cost = (cost_bps + slippage_bps) / 10_000.0
    for index in range(0, max(0, len(rows) - holding_period - 1)):
        signal = signal_for(strategy, rows[index])
        if signal == 0:
            continue
        entry_row = rows[index + 1]
        exit_row = rows[index + 1 + holding_period]
        entry = entry_row.get("open")
        exit_price = exit_row.get("open")
        if entry in {None, 0} or exit_price is None:
            continue
        gross = signal * (float(exit_price) / float(entry) - 1.0)
        net = gross - total_cost
        atr = rows[index].get("atr") or 0
        trades.append(
            {
                "signal_timestamp": rows[index]["timestamp"],
                "entry_timestamp": entry_row["timestamp"],
                "exit_timestamp": exit_row["timestamp"],
                "direction": signal,
                "gross_return": gross,
                "net_return": net,
                "r": net / (float(atr) / float(entry)) if atr and entry else net,
                "same_bar_fill": False,
            }
        )
    returns = [trade["net_return"] for trade in trades]
    wins = [item for item in returns if item > 0]
    losses = [item for item in returns if item < 0]
    profit = sum(wins)
    loss = abs(sum(losses))
    pf = None if loss == 0 else profit / loss
    avg_r = mean([trade["r"] for trade in trades]) if trades else None
    sharpe = None
    if len(returns) >= 2:
        sd = statistics.pstdev(returns)
        sharpe = None if sd == 0 else (mean(returns) or 0.0) / sd * math.sqrt(len(returns))
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for value in returns:
        equity += value
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
    cost_impact = len(trades) * total_cost
    return {
        "trades": trades,
        "metrics": {
            "pf": pf,
            "avgR": avg_r,
            "sharpe": sharpe,
            "dd": max_dd,
            "trade_count": len(trades),
            "cost_impact": cost_impact,
            "stability": stability_score(pf, sharpe, len(trades)),
        },
    }


def failure_report(strategy: str, walk: dict[str, Any]) -> dict[str, Any]:
    oos = walk["segments"]["oos"]["metrics"]
    metrics = walk["overall"]["metrics"]
    reasons = []
    if metrics["trade_count"] < 5:
        reasons.append("sample_insufficient")
    if oos["trade_count"] == 0:
        reasons.append("oos_no_trades")
    if (metrics["pf"] or 0) <= 1.0:
        reasons.append("direction_or_signal_edge_failed")
    if metrics["trade_count"] > 0 and abs(metrics["cost_impact"]) > abs(metrics["avgR"] or 0.0):
        reasons.append("costs_consumed_edge")
    if (oos["stability"] or 0.0) < 0.35:
        reasons.append("unstable_across_walk_forward")
    if strategy in {"funding_carry", "oi_divergence", "orderflow"} and metrics["trade_count"] == 0:
        reasons.append("feature_or_regime_not_active")
    if not reasons:
        reasons.append("edge_candidate_needs_review")
    return {
        "strategy": strategy,
        "status": "failed" if reasons != ["edge_candidate_needs_review"] else "review",
        "failure_reasons": reasons,
        "direction_error": "direction_or_signal_edge_failed" in reasons,
        "entry_delay": "not_detected_next_bar_fill_used" if metrics["trade_count"] else "not_enough_trades",
        "costs_consumed_edge": "costs_consumed_edge" in reasons,
        "feature_invalid": "feature_or_regime_not_active" in reasons,
        "regime_mismatch": "unstable_across_walk_forward" in reasons,
        "sample_insufficient": "sample_insufficient" in reasons,
    }


def chrono_dual_state(rows: list[dict[str, Any]]) -> dict[str, Any]:
    latest = rows[-1] if rows else {}
    confidence = min(1.0, sum(abs(latest.get(key) or 0.0) for key in ("trend", "momentum", "taker_imbalance")))
    risk_adjustment = "reduce" if latest.get("volatility_state") == "high" or (latest.get("crowding_score") or 0) > 0.8 else "neutral"
    return {
        "macro_model": "TimesFM",
        "micro_model": "Kronos",
        "reviewer": "LLM",
        "status": "research_layer_contract_only",
        "execution_allowed": False,
        "model_calls": False,
        "market_state": latest.get("market_regime", "unknown"),
        "confidence": confidence,
        "risk_adjustment": risk_adjustment,
    }


def meta_examples(rows: list[dict[str, Any]], strategy: str, holding_period: int, cost_bps: float, slippage_bps: float) -> list[dict[str, Any]]:
    examples = []
    cost = (cost_bps + slippage_bps) / 10_000.0
    for index in range(0, max(0, len(rows) - holding_period - 1)):
        signal = signal_for(strategy, rows[index])
        if signal == 0:
            continue
        entry = rows[index + 1].get("open")
        exit_price = rows[index + 1 + holding_period].get("open")
        if entry in {None, 0} or exit_price is None:
            continue
        net = signal * (float(exit_price) / float(entry) - 1.0) - cost
        features = [float(rows[index].get(key) or 0.0) for key in ("returns", "volatility", "trend", "momentum", "funding_zscore", "oi_change", "taker_imbalance", "crowding_score")]
        examples.append({"x": features, "y": 1 if net > 0 else 0})
    return examples


def sigmoid(value: float) -> float:
    if value < -50:
        return 0.0
    if value > 50:
        return 1.0
    return 1.0 / (1.0 + math.exp(-value))


def train_logistic(examples: list[dict[str, Any]]) -> dict[str, Any]:
    if len(examples) < 4:
        return {"status": "failed", "reason": "sample_insufficient", "trade_probability": None}
    weights = [0.0] * len(examples[0]["x"])
    bias = 0.0
    for _ in range(80):
        for example in examples:
            pred = sigmoid(sum(weight * value for weight, value in zip(weights, example["x"])) + bias)
            err = pred - example["y"]
            weights = [weight - 0.1 * err * value for weight, value in zip(weights, example["x"])]
            bias -= 0.1 * err
    probs = [sigmoid(sum(weight * value for weight, value in zip(weights, example["x"])) + bias) for example in examples]
    return {"status": "trained", "trade_probability": mean(probs), "coefficients": weights, "bias": bias, "examples": len(examples)}


def decision_stump(examples: list[dict[str, Any]], target: str = "y") -> dict[str, Any]:
    best = {"feature": 0, "threshold": 0.0, "left": 0.0, "right": 0.0, "loss": float("inf")}
    for feature in range(len(examples[0]["x"])):
        for threshold in sorted(set(example["x"][feature] for example in examples))[:20]:
            left = [example[target] for example in examples if example["x"][feature] <= threshold]
            right = [example[target] for example in examples if example["x"][feature] > threshold]
            if not left or not right:
                continue
            left_mean = mean(left) or 0.0
            right_mean = mean(right) or 0.0
            loss = sum((example[target] - (left_mean if example["x"][feature] <= threshold else right_mean)) ** 2 for example in examples)
            if loss < best["loss"]:
                best = {"feature": feature, "threshold": threshold, "left": left_mean, "right": right_mean, "loss": loss}
    return best


def train_gradient_boosting(examples: list[dict[str, Any]]) -> dict[str, Any]:
    if len(examples) < 6:
        return {"status": "failed", "reason": "sample_insufficient", "trade_probability": None}
    base = mean([example["y"] for example in examples]) or 0.0
    scores = [base] * len(examples)
    work = [dict(example) for example in examples]
    stumps = []
    for _ in range(5):
        for index, example in enumerate(work):
            example["residual"] = example["y"] - scores[index]
        stump = decision_stump(work, "residual")
        stumps.append({key: stump[key] for key in ("feature", "threshold", "left", "right")})
        for index, example in enumerate(work):
            scores[index] += 0.25 * (stump["left"] if example["x"][stump["feature"]] <= stump["threshold"] else stump["right"])
    probs = [min(1.0, max(0.0, score)) for score in scores]
    return {"status": "trained", "trade_probability": mean(probs), "base_rate": base, "stumps": stumps, "examples": len(examples)}


def train_random_forest(examples: list[dict[str, Any]]) -> dict[str, Any]:
    if len(examples) < 6:
        return {"status": "failed", "reason": "sample_insufficient", "trade_probability": None}
    trees = []
    predictions = []
    for tree_id in range(7):
        sample = [examples[(tree_id * 3 + index * 5) % len(examples)] for index in range(len(examples))]
        stump = decision_stump(sample)
        trees.append({key: stump[key] for key in ("feature", "threshold", "left", "right")})
    for example in examples:
        votes = [tree["left"] if example["x"][tree["feature"]] <= tree["threshold"] else tree["right"] for tree in trees]
        predictions.append(mean(votes) or 0.0)
    return {"status": "trained", "trade_probability": mean(predictions), "trees": trees, "examples": len(examples)}


def train_meta_label(rows: list[dict[str, Any]], strategy: str, holding_period: int, cost_bps: float, slippage_bps: float) -> dict[str, Any]:
    examples = meta_examples(rows, strategy, holding_period, cost_bps, slippage_bps)
    return {
        "target": "signal_execution_probability_not_direction_prediction",
        "strategy": strategy,
        "examples": len(examples),
        "models": {
            "logistic_regression": train_logistic(examples),
            "gradient_boosting": train_gradient_boosting(examples),
            "random_forest": train_random_forest(examples),
        },
    }



def edge_search_report(trial: dict[str, Any], store: Path) -> dict[str, Any]:
    candidates = []
    for result in trial.get('strategies', []):
        strategy = result.get('strategy')
        walk = result.get('walk_forward', {})
        overall = walk.get('overall', {}).get('metrics', {})
        oos = walk.get('segments', {}).get('oos', {}).get('metrics', {})
        failure = result.get('failure_report', {})
        memory = result.get('strategy_memory', {})
        pf = float(oos.get('pf') or 0.0)
        sharpe = float(oos.get('sharpe') or 0.0)
        stability = float(oos.get('stability') or 0.0)
        trades = int(oos.get('trade_count') or 0)
        dd = abs(float(oos.get('dd') or 0.0))
        cost = abs(float(overall.get('cost_impact') or 0.0))
        score = min(1.0, max(0.0, (pf / 2.0) * 0.35 + max(0.0, sharpe / 2.0) * 0.25 + stability * 0.25 + min(1.0, trades / 20.0) * 0.15 - dd - cost))
        blockers = []
        if trades < 5:
            blockers.append('oos_trade_count_insufficient')
        if pf <= 1.0:
            blockers.append('oos_profit_factor_not_positive')
        if failure.get('status') == 'failed':
            blockers.extend(failure.get('failure_reasons', []))
        if memory.get('skip_recommendation'):
            blockers.append('repeated_failure_memory')
        blockers = sorted(set(str(item) for item in blockers if item))
        if score >= 0.65 and not blockers:
            action = 'candidate_review'
        elif memory.get('skip_recommendation'):
            action = 'avoid_repeat_without_new_evidence'
        else:
            action = 'research_new_hypothesis'
        candidates.append({
            'strategy': strategy,
            'edge_score': score,
            'research_action': action,
            'blockers': blockers,
            'metrics': {
                'oos_pf': oos.get('pf'),
                'oos_sharpe': oos.get('sharpe'),
                'oos_dd': oos.get('dd'),
                'oos_trade_count': trades,
                'cost_impact': overall.get('cost_impact'),
            },
            'failure_reasons': failure.get('failure_reasons', []),
            'repeated_failure_reasons': memory.get('repeated_failure_reasons', []),
        })
    candidates.sort(key=lambda item: item['edge_score'], reverse=True)
    status = 'EDGE_CANDIDATE_REVIEW' if any(item['research_action'] == 'candidate_review' for item in candidates) else 'EDGE_NOT_FOUND'
    payload = {
        'kind': 'agentoffice.futures_research.edge_search.v2',
        'trial_id': trial.get('trial_id'),
        'status': status,
        'trading_allowed': False,
        'paper_trading_started': False,
        'private_api_touched': False,
        'selection_rule': 'research_only_oos_score_with_failure_memory_blockers',
        'candidates': candidates,
        'created_at': utc_now(),
    }
    trial_file = str(trial.get('trial_id') or 'unknown') + '.json'
    write_json(store / 'edge_search' / trial_file, payload)
    write_json(store / 'edge_search' / 'latest_edge_search.json', payload)
    return payload

def run_research(feature_store: str | Path, trial_store: str | Path, strategy: str = "all", *, cost_bps: float = 4.0, slippage_bps: float = 2.0, holding_period: int = 3) -> dict[str, Any]:
    if holding_period < 1:
        raise FuturesResearchError("holding_period_must_be_positive")
    selected = list(STRATEGIES if strategy == "all" else (strategy,))
    unknown = [item for item in selected if item not in STRATEGIES]
    if unknown:
        raise FuturesResearchError(f"unknown_strategy: {', '.join(unknown)}")
    rows = load_features(feature_store)
    store = Path(trial_store)
    trial_id = f"trial_{sha256_text(json.dumps({'rows': len(rows), 'strategy': selected, 'cost': cost_bps, 'slippage': slippage_bps}, sort_keys=True))[:12]}"
    segments = split_walk_forward(rows)
    results = []
    for name in selected:
        segment_results = {segment: simulate(segment_rows, name, cost_bps=cost_bps, slippage_bps=slippage_bps, holding_period=holding_period) for segment, segment_rows in segments.items()}
        overall = simulate(rows, name, cost_bps=cost_bps, slippage_bps=slippage_bps, holding_period=holding_period)
        walk = {
            "strategy": name,
            "segments": segment_results,
            "overall": overall,
            "validation_standard": {
                "random_split": False,
                "future_leakage": False,
                "same_bar_fill": False,
                "train_validation_oos": True,
                "cost_model_bps": cost_bps,
                "slippage_bps": slippage_bps,
            },
        }
        failure = failure_report(name, walk)
        memory = read_strategy_memory(store, name)
        repeated = [reason for reason in failure["failure_reasons"] if memory["historical_failure_reasons"].get(reason, 0) != 0]
        memory["repeated_failure_reasons"] = repeated
        memory["skip_recommendation"] = bool(repeated and failure["status"] == "failed")
        failure["memory_repeated_failure"] = bool(repeated)
        failure["research_recommendation"] = "avoid_repeat_without_new_features" if memory["skip_recommendation"] else "review_with_new_hypothesis"
        result = {
            "strategy": name,
            "walk_forward": walk,
            "failure_report": failure,
            "strategy_memory": memory,
            "meta_label": train_meta_label(rows, name, holding_period, cost_bps, slippage_bps),
        }
        results.append(result)
        write_json(store / "strategy_memory" / name / f"{trial_id}.json", failure)
    payload = {
        "kind": "agentoffice.futures_research.trial.v2",
        "trial_id": trial_id,
        "research_version": RESEARCH_VERSION,
        "status": "TARGET_FAILED",
        "trading_allowed": False,
        "paper_trading_started": False,
        "private_api_touched": False,
        "feature_store": str(feature_store),
        "source_lineage": feature_source_summary(feature_store),
        "strategies": results,
        "strategy_memory_summary": {result["strategy"]: result["strategy_memory"] for result in results},
        "chrono_dual": chrono_dual_state(rows),
        "created_at": utc_now(),
    }
    payload['edge_search'] = edge_search_report(payload, store)
    write_json(store / "trials" / f"{trial_id}.json", payload)
    write_json(store / "latest_trial.json", payload)
    return payload


def run_full_loop(data_lake: str | Path, feature_store: str | Path, trial_store: str | Path, strategy: str = "all", *, cost_bps: float = 4.0, slippage_bps: float = 2.0, holding_period: int = 3) -> dict[str, Any]:
    features = build_feature_store(data_lake, feature_store)
    if not features.get("ok"):
        payload = {"kind": "agentoffice.futures_research.loop.v2", "ok": False, "status": "feature_build_failed", "feature_store": features, "trading_allowed": False}
        write_json(Path(trial_store) / "latest_trial.json", payload)
        return payload
    trial = run_research(feature_store, trial_store, strategy, cost_bps=cost_bps, slippage_bps=slippage_bps, holding_period=holding_period)
    return {"kind": "agentoffice.futures_research.loop.v2", "ok": True, "feature_store": features, "trial": trial, "trading_allowed": False}


def format_research_payload(payload: dict[str, Any]) -> str:
    lines = [str(payload.get("kind", "agentoffice.futures_research"))]
    for key in ("ok", "status", "rows", "trial_id"):
        if key in payload:
            value = payload[key]
            lines.append(f"{key}: {str(value).lower() if isinstance(value, bool) else value}")
    if payload.get("missing_datasets"):
        lines.append(f"missing_datasets: {', '.join(payload['missing_datasets'])}")
    if isinstance(payload.get("trial"), dict):
        lines.append(f"trial_id: {payload['trial'].get('trial_id')}")
        lines.append(f"trial_status: {payload['trial'].get('status')}")
    lines.append("trading_allowed: false")
    lines.append("paper_trading_started: false")
    lines.append("private_api_touched: false")
    return "\n".join(lines)
