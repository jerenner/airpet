from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd


@dataclass
class FeatureScaler:
    method: str
    params: Dict[str, Any]

    def transform(self, x: np.ndarray) -> np.ndarray:
        if self.method == "none":
            return x
        if self.method == "standard":
            mean = np.asarray(self.params.get("mean"), dtype=float)
            std = np.asarray(self.params.get("std"), dtype=float)
            std = np.where(std == 0.0, 1.0, std)
            return (x - mean) / std
        if self.method == "minmax":
            mn = np.asarray(self.params.get("min"), dtype=float)
            mx = np.asarray(self.params.get("max"), dtype=float)
            denom = np.where((mx - mn) == 0.0, 1.0, (mx - mn))
            return (x - mn) / denom
        return x


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_json_or_yaml(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore
        except Exception as exc:
            raise ValueError("YAML config requested but PyYAML is not installed. Use JSON or install pyyaml.") from exc
        payload = yaml.safe_load(text)
        if not isinstance(payload, dict):
            raise ValueError("Experiment config must parse to an object/dict.")
        return payload

    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("Experiment config must parse to an object/dict.")
    return payload


def _resolve_path(value: Optional[str], base_dir: Path) -> Optional[Path]:
    if not value:
        return None
    p = Path(value)
    if p.is_absolute():
        return p
    return (base_dir / p).resolve()


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _pick_feature_columns(df: pd.DataFrame, input_params: Sequence[str]) -> List[str]:
    cols = list(df.columns)

    if input_params:
        picked: List[str] = []
        for name in input_params:
            c_prefixed = f"param__{name}"
            if c_prefixed in cols:
                picked.append(c_prefixed)
            elif name in cols:
                picked.append(name)
        if not picked:
            raise ValueError(
                f"None of the requested input params were found in dataset columns: {list(input_params)}"
            )
        return picked

    auto = [c for c in cols if c.startswith("param__")]
    if auto:
        return auto

    reserved = {
        "split", "source_kind", "source_path", "source_run_id", "study_name", "method", "seed", "timestamp",
        "run_index", "success", "failed", "error", "target_objective", "target_value",
    }
    numeric_cols = [c for c in cols if c not in reserved and pd.api.types.is_numeric_dtype(df[c])]
    if not numeric_cols:
        raise ValueError("No feature columns found.")
    return numeric_cols


def _pick_target_column(df: pd.DataFrame, target_objective: Optional[str]) -> str:
    if target_objective:
        prefixed = f"objective__{target_objective}"
        if prefixed in df.columns:
            return prefixed
        if target_objective in df.columns:
            return target_objective

    if "target_value" in df.columns:
        return "target_value"

    objective_cols = [c for c in df.columns if c.startswith("objective__")]
    if objective_cols:
        return objective_cols[0]

    raise ValueError("No target column found in dataset.")


def _fit_scaler(x_train: np.ndarray, method: str) -> FeatureScaler:
    method = (method or "none").lower().strip()
    if method in {"none", "off", "disabled"}:
        return FeatureScaler(method="none", params={})
    if method == "standard":
        return FeatureScaler(method="standard", params={"mean": x_train.mean(axis=0), "std": x_train.std(axis=0)})
    if method == "minmax":
        return FeatureScaler(method="minmax", params={"min": x_train.min(axis=0), "max": x_train.max(axis=0)})
    raise ValueError(f"Unsupported feature scaling method '{method}'.")


def _rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))


def _mae(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.mean(np.abs(y_true - y_pred)))


def _r2(y_true: np.ndarray, y_pred: np.ndarray) -> Optional[float]:
    ss_res = float(np.sum((y_true - y_pred) ** 2))
    ss_tot = float(np.sum((y_true - np.mean(y_true)) ** 2))
    if ss_tot <= 1e-15:
        return None
    return float(1.0 - (ss_res / ss_tot))


def _compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, Any]:
    return {
        "rmse": _rmse(y_true, y_pred),
        "mae": _mae(y_true, y_pred),
        "r2": _r2(y_true, y_pred),
    }


def _rbf_kernel(x1: np.ndarray, x2: np.ndarray, length_scale: float) -> np.ndarray:
    l2 = max(float(length_scale) ** 2, 1e-12)
    d2 = np.sum((x1[:, None, :] - x2[None, :, :]) ** 2, axis=2)
    return np.exp(-0.5 * d2 / l2)


def _default_length_scale(x: np.ndarray) -> float:
    if x.shape[0] <= 1:
        return 1.0
    d2 = np.sum((x[:, None, :] - x[None, :, :]) ** 2, axis=2)
    d = np.sqrt(np.maximum(d2, 0.0))
    upper = d[np.triu_indices_from(d, k=1)]
    upper = upper[np.isfinite(upper)]
    upper = upper[upper > 0]
    if upper.size == 0:
        return 1.0
    return float(np.median(upper))


def _train_gp(
    x_train: np.ndarray,
    y_train: np.ndarray,
    x_val: np.ndarray,
    length_scale: Optional[float] = None,
    noise: float = 1e-6,
) -> Tuple[np.ndarray, Dict[str, Any]]:
    if length_scale is None:
        length_scale = _default_length_scale(x_train)

    k = _rbf_kernel(x_train, x_train, length_scale=length_scale)
    k = k + float(noise) * np.eye(x_train.shape[0], dtype=float)

    try:
        alpha = np.linalg.solve(k, y_train)
    except np.linalg.LinAlgError:
        alpha = np.linalg.lstsq(k, y_train, rcond=None)[0]

    k_val = _rbf_kernel(x_val, x_train, length_scale=length_scale)
    y_pred = k_val @ alpha

    model_info = {
        "type": "gp",
        "length_scale": float(length_scale),
        "noise": float(noise),
        "n_train": int(x_train.shape[0]),
        "n_features": int(x_train.shape[1]),
    }
    return y_pred, model_info


def _train_mlp(
    x_train: np.ndarray,
    y_train: np.ndarray,
    x_val: np.ndarray,
    *,
    hidden_size: int,
    epochs: int,
    learning_rate: float,
    l2: float,
    seed: int,
) -> Tuple[np.ndarray, Dict[str, Any]]:
    rng = np.random.default_rng(seed)
    n_samples, n_features = x_train.shape

    hidden_size = max(2, int(hidden_size))
    epochs = max(1, int(epochs))
    learning_rate = float(learning_rate)
    l2 = max(0.0, float(l2))

    w1 = rng.normal(0.0, 0.1, size=(n_features, hidden_size))
    b1 = np.zeros((1, hidden_size), dtype=float)
    w2 = rng.normal(0.0, 0.1, size=(hidden_size, 1))
    b2 = np.zeros((1, 1), dtype=float)

    y_train_col = y_train.reshape(-1, 1)

    for _ in range(epochs):
        h_pre = x_train @ w1 + b1
        h = np.tanh(h_pre)
        y_hat = h @ w2 + b2

        err = y_hat - y_train_col
        d_y = (2.0 / max(1, n_samples)) * err

        d_w2 = h.T @ d_y + l2 * w2
        d_b2 = np.sum(d_y, axis=0, keepdims=True)

        d_h = d_y @ w2.T
        d_h_pre = d_h * (1.0 - np.tanh(h_pre) ** 2)

        d_w1 = x_train.T @ d_h_pre + l2 * w1
        d_b1 = np.sum(d_h_pre, axis=0, keepdims=True)

        w2 -= learning_rate * d_w2
        b2 -= learning_rate * d_b2
        w1 -= learning_rate * d_w1
        b1 -= learning_rate * d_b1

    h_val = np.tanh(x_val @ w1 + b1)
    y_pred = (h_val @ w2 + b2).reshape(-1)

    model_info = {
        "type": "mlp",
        "hidden_size": hidden_size,
        "epochs": epochs,
        "learning_rate": learning_rate,
        "l2": l2,
        "seed": int(seed),
        "n_train": int(x_train.shape[0]),
        "n_features": int(x_train.shape[1]),
    }
    return y_pred, model_info


def _load_dataset_for_experiment(config: Dict[str, Any], config_dir: Path) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    dataset_cfg = dict(config.get("dataset") or {})

    manifest_path = _resolve_path(dataset_cfg.get("manifest"), config_dir)
    manifest: Dict[str, Any] = {}
    if manifest_path and manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            manifest = {}

    train_csv = _resolve_path(dataset_cfg.get("train_csv"), config_dir)
    val_csv = _resolve_path(dataset_cfg.get("val_csv"), config_dir)

    if (not train_csv or not train_csv.exists()) and manifest:
        train_csv = _resolve_path((manifest.get("outputs") or {}).get("train_csv"), config_dir)
    if (not val_csv or not val_csv.exists()) and manifest:
        val_csv = _resolve_path((manifest.get("outputs") or {}).get("val_csv"), config_dir)

    if train_csv and train_csv.exists() and val_csv and val_csv.exists():
        return pd.read_csv(train_csv), pd.read_csv(val_csv), manifest

    dataset_csv = _resolve_path(dataset_cfg.get("dataset_csv"), config_dir)
    if (not dataset_csv or not dataset_csv.exists()) and manifest:
        dataset_csv = _resolve_path((manifest.get("outputs") or {}).get("dataset_csv"), config_dir)
    if not dataset_csv or not dataset_csv.exists():
        raise ValueError("Could not resolve dataset input. Provide train/val CSVs or dataset CSV (or a manifest pointing to them).")

    all_df = pd.read_csv(dataset_csv)
    if "split" in all_df.columns:
        train_df = all_df[all_df["split"] == "train"].copy()
        val_df = all_df[all_df["split"] == "val"].copy()
        if len(train_df) > 0 and len(val_df) > 0:
            return train_df, val_df, manifest

    split_cfg = dict(config.get("split") or {})
    val_ratio = float(split_cfg.get("val_ratio", 0.2))
    seed = int(split_cfg.get("seed", 42))

    rng = np.random.default_rng(seed)
    idx = np.arange(len(all_df))
    rng.shuffle(idx)

    n_total = len(idx)
    n_val = int(round(n_total * max(0.0, min(1.0, val_ratio))))
    if val_ratio > 0.0 and n_total > 1:
        n_val = max(1, min(n_total - 1, n_val))
    else:
        n_val = 0

    val_idx = set(idx[:n_val])
    val_mask = np.array([i in val_idx for i in range(n_total)], dtype=bool)

    train_df = all_df.loc[~val_mask].copy()
    val_df = all_df.loc[val_mask].copy()
    return train_df, val_df, manifest


def run_surrogate_experiment(config: Dict[str, Any], config_dir: Optional[Path] = None) -> Dict[str, Any]:
    cfg = dict(config)
    config_dir = config_dir or Path.cwd()

    experiment_name = cfg.get("experiment_name") or datetime.now(timezone.utc).strftime("exp_%Y%m%dT%H%M%SZ")

    train_df, val_df, manifest = _load_dataset_for_experiment(cfg, config_dir)

    features_cfg = dict(cfg.get("features") or {})
    input_params = list(features_cfg.get("input_params") or [])
    target_objective = features_cfg.get("target_objective") or (manifest.get("target_objective") if isinstance(manifest, dict) else None)

    feat_cols = _pick_feature_columns(train_df, input_params)
    target_col = _pick_target_column(train_df, target_objective)

    train_df = train_df.copy()
    val_df = val_df.copy()

    for c in feat_cols + [target_col]:
        train_df[c] = pd.to_numeric(train_df[c], errors="coerce")
        val_df[c] = pd.to_numeric(val_df[c], errors="coerce")

    train_df = train_df.dropna(subset=[target_col])
    val_df = val_df.dropna(subset=[target_col])

    if len(train_df) == 0 or len(val_df) == 0:
        raise ValueError("Training or validation set is empty after removing rows with missing target values.")

    feature_means = train_df[feat_cols].mean(numeric_only=True)
    train_df[feat_cols] = train_df[feat_cols].fillna(feature_means)
    val_df[feat_cols] = val_df[feat_cols].fillna(feature_means)

    x_train = train_df[feat_cols].to_numpy(dtype=float)
    y_train = train_df[target_col].to_numpy(dtype=float)
    x_val = val_df[feat_cols].to_numpy(dtype=float)
    y_val = val_df[target_col].to_numpy(dtype=float)

    scaling_cfg = dict(features_cfg.get("feature_scaling") or {})
    scaling_enabled = bool(scaling_cfg.get("enabled", False))
    scaling_method = scaling_cfg.get("method", "standard") if scaling_enabled else "none"

    scaler = _fit_scaler(x_train, scaling_method)
    x_train_scaled = scaler.transform(x_train)
    x_val_scaled = scaler.transform(x_val)

    model_cfg = dict(cfg.get("model") or {})
    model_type = str(model_cfg.get("type", "gp")).lower().strip()
    training_cfg = dict(cfg.get("training") or {})
    seed = int(training_cfg.get("seed", 42))

    t0 = time.perf_counter()

    if model_type == "gp":
        gp_cfg = dict(model_cfg.get("gp") or {})
        y_pred, model_info = _train_gp(
            x_train_scaled,
            y_train,
            x_val_scaled,
            length_scale=_safe_float(gp_cfg.get("length_scale")),
            noise=float(gp_cfg.get("noise", 1e-6)),
        )
    elif model_type == "mlp":
        mlp_cfg = dict(model_cfg.get("mlp") or {})
        y_pred, model_info = _train_mlp(
            x_train_scaled,
            y_train,
            x_val_scaled,
            hidden_size=int(mlp_cfg.get("hidden_size", training_cfg.get("hidden_size", 16))),
            epochs=int(mlp_cfg.get("epochs", training_cfg.get("epochs", 400))),
            learning_rate=float(mlp_cfg.get("learning_rate", training_cfg.get("learning_rate", 0.01))),
            l2=float(mlp_cfg.get("l2", training_cfg.get("l2", 0.0))),
            seed=seed,
        )
    else:
        raise ValueError(f"Unsupported model type '{model_type}'. Use 'gp' or 'mlp'.")

    train_time_s = float(time.perf_counter() - t0)

    t1 = time.perf_counter()
    metrics = _compute_metrics(y_val, y_pred)
    eval_time_s = float(time.perf_counter() - t1)

    output_cfg = dict(cfg.get("output") or {})
    output_root = output_cfg.get("root", "surrogate/experiments")
    output_dir = _resolve_path(output_root, config_dir) / experiment_name
    output_dir.mkdir(parents=True, exist_ok=True)

    predictions_df = pd.DataFrame({
        "y_true": y_val,
        "y_pred": y_pred,
        "abs_error": np.abs(y_val - y_pred),
    })
    pred_path = output_dir / "val_predictions.csv"
    predictions_df.to_csv(pred_path, index=False)

    report: Dict[str, Any] = {
        "success": True,
        "experiment_name": experiment_name,
        "created_at": _utc_now_iso(),
        "model": model_info,
        "dataset": {
            "n_train": int(len(train_df)),
            "n_val": int(len(val_df)),
            "feature_columns": feat_cols,
            "target_column": target_col,
            "target_objective": target_objective,
        },
        "scaling": {
            "enabled": scaling_enabled,
            "method": scaler.method,
        },
        "metrics": metrics,
        "timing": {
            "train_time_s": train_time_s,
            "evaluation_time_s": eval_time_s,
            "prediction_rows": int(len(val_df)),
            "prediction_time_per_row_ms": (eval_time_s / max(1, len(val_df))) * 1000.0,
        },
        "artifacts": {
            "output_dir": str(output_dir),
            "val_predictions_csv": str(pred_path),
        },
        "config": cfg,
    }

    report_path = output_dir / "report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    report["artifacts"]["report_json"] = str(report_path)
    return report


def run_surrogate_experiment_from_path(config_path: str) -> Dict[str, Any]:
    path = Path(config_path).expanduser().resolve()
    config = _read_json_or_yaml(path)
    return run_surrogate_experiment(config=config, config_dir=path.parent)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run surrogate baseline experiment (GP/MLP) from config.")
    parser.add_argument("--config", required=True, help="Path to JSON/YAML experiment config.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    report = run_surrogate_experiment_from_path(args.config)
    print(json.dumps({
        "success": True,
        "experiment_name": report.get("experiment_name"),
        "metrics": report.get("metrics"),
        "timing": report.get("timing"),
        "report": report.get("artifacts", {}).get("report_json"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
