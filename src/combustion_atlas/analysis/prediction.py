"""Nearest observed runs plus a gated gradient-boosting estimate.

This is a statistical estimate from unreviewed candidate data, not a validated
prediction. The model answers only when there are enough runs, cross-validation
beats a median baseline, and the inputs fall inside the training domain; otherwise
it returns "insufficient_data" with the reason. Nearest observed runs are always
shown so users can see the evidence directly.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any

from .coverage import FIELDS, OUTCOMES, coverage_payload

MIN_TRAIN = 30
BASELINE_RATIO = 0.9  # CV MAE must be at most 90% of the median-baseline MAE
CATEGORY_FEATURES = ["family", "material"]
_MODEL_CACHE: dict[str, dict[str, Any]] = {}


def _target_value(record: dict[str, Any], target: str) -> float | None:
    value = record.get("outcomes", {}).get(target, {}).get("value")
    return float(value) if isinstance(value, int | float) and math.isfinite(value) else None


def prediction_options(workspace: Any) -> dict[str, Any]:
    records = coverage_payload(workspace)["records"]
    targets: list[dict[str, Any]] = [
        {
            "key": key,
            "label": meta["label"],
            "unit": meta["unit"],
            "n": sum(_target_value(r, key) is not None for r in records),
        }
        for key, meta in OUTCOMES.items()
    ]
    features: list[dict[str, Any]] = []
    for key, meta in FIELDS.items():
        values = [r[key] for r in records if r.get(key) is not None]
        if values:
            features.append(
                {
                    "key": key,
                    "label": meta["label"],
                    "unit": meta["unit"],
                    "kind": "numeric",
                    "min": min(values),
                    "max": max(values),
                    "values": [],
                }
            )
    for key in CATEGORY_FEATURES:
        values = sorted({str(r[key]) for r in records if r.get(key)})
        if values:
            features.append(
                {
                    "key": key,
                    "label": key.title(),
                    "unit": None,
                    "kind": "category",
                    "min": None,
                    "max": None,
                    "values": values,
                }
            )
    return {"targets": [t for t in targets if int(t["n"]) > 0], "features": features}


def _scales(records: list[dict[str, Any]], keys: list[str]) -> dict[str, float]:
    scales = {}
    for key in keys:
        values = [float(r[key]) for r in records if r.get(key) is not None]
        if len(values) > 1:
            mean = sum(values) / len(values)
            spread = math.sqrt(sum((v - mean) ** 2 for v in values) / (len(values) - 1))
            scales[key] = spread or 1.0
        else:
            scales[key] = 1.0
    return scales


def _distance(
    record: dict[str, Any],
    inputs: dict[str, Any],
    numeric: list[str],
    categories: list[str],
    scales: dict[str, float],
) -> float | None:
    total, used = 0.0, 0
    for key in numeric:
        if record.get(key) is None:
            return None  # cannot compare on a condition the run did not report
        total += ((float(record[key]) - float(inputs[key])) / scales[key]) ** 2
        used += 1
    for key in categories:
        total += 0.0 if str(record.get(key) or "").lower() == str(inputs[key]).lower() else 1.0
        used += 1
    return math.sqrt(total / used) if used else None


def _fit(
    records: list[dict[str, Any]], target: str, numeric: list[str], categories: list[str]
) -> dict[str, Any]:
    import numpy as np
    from sklearn.ensemble import HistGradientBoostingRegressor  # type: ignore[import-untyped]
    from sklearn.model_selection import KFold  # type: ignore[import-untyped]

    rows = [
        r
        for r in records
        if _target_value(r, target) is not None and all(r.get(k) is not None for k in numeric)
    ]
    info: dict[str, Any] = {"n_train": len(rows), "features": numeric + categories}
    if len(rows) < MIN_TRAIN:
        return {
            **info,
            "status": "insufficient_data",
            "reason": f"Only {len(rows)} runs report this outcome with these conditions; "
            f"at least {MIN_TRAIN} are required.",
        }
    levels = {k: sorted({str(r.get(k) or "") for r in rows}) for k in categories}
    matrix = np.array(
        [
            [float(r[k]) for k in numeric]
            + [float(levels[k].index(str(r.get(k) or ""))) for k in categories]
            for r in rows
        ]
    )
    y = np.array([_target_value(r, target) for r in rows], dtype=float)
    mask = [False] * len(numeric) + [True] * len(categories)

    def model() -> Any:
        return HistGradientBoostingRegressor(
            max_depth=3,
            learning_rate=0.08,
            max_iter=200,
            min_samples_leaf=3,
            l2_regularization=1.0,
            categorical_features=mask if any(mask) else None,
            random_state=0,
        )

    residuals, baseline = [], []
    for train, test in KFold(n_splits=5, shuffle=True, random_state=0).split(matrix):
        fitted = model().fit(matrix[train], y[train])
        residuals.extend((y[test] - fitted.predict(matrix[test])).tolist())
        baseline.extend((y[test] - float(np.median(y[train]))).tolist())
    cv_mae = float(np.mean(np.abs(residuals)))
    base_mae = float(np.mean(np.abs(baseline)))
    info.update(
        cv_mae=cv_mae,
        baseline_mae=base_mae,
        residual_band=[float(np.quantile(residuals, 0.1)), float(np.quantile(residuals, 0.9))],
    )
    if cv_mae > BASELINE_RATIO * base_mae:
        return {
            **info,
            "status": "insufficient_data",
            "reason": f"Cross-validated error ({cv_mae:.3g}) does not beat the median "
            f"baseline ({base_mae:.3g}); the conditions do not explain this "
            "outcome well enough in the available data.",
        }
    info.update(
        status="ok",
        estimator=model().fit(matrix, y),
        levels=levels,
        ranges={
            k: [float(matrix[:, i].min()), float(matrix[:, i].max())] for i, k in enumerate(numeric)
        },
    )
    return info


def predict_payload(workspace: Any, body: dict[str, Any]) -> dict[str, Any]:
    target = str(body.get("target") or "")
    if target not in OUTCOMES:
        raise ValueError("Choose a supported outcome")
    raw_inputs = body.get("inputs") or {}
    if not isinstance(raw_inputs, dict):
        raise ValueError("Inputs must be an object")
    numeric = [k for k in FIELDS if raw_inputs.get(k) not in (None, "")]
    categories = [k for k in CATEGORY_FEATURES if raw_inputs.get(k) not in (None, "")]
    inputs: dict[str, Any] = {}
    for key in numeric:
        try:
            inputs[key] = float(raw_inputs[key])
        except (TypeError, ValueError):
            raise ValueError(f"{FIELDS[key]['label']} must be a number") from None
        if not math.isfinite(inputs[key]):
            raise ValueError(f"{FIELDS[key]['label']} must be finite")
    for key in categories:
        inputs[key] = str(raw_inputs[key])[:120]
    if not numeric and not categories:
        raise ValueError("Enter at least one condition")

    records = coverage_payload(workspace)["records"]
    scales = _scales(records, numeric)
    scored = [
        (d, r)
        for r in records
        if (d := _distance(r, inputs, numeric, categories, scales)) is not None
        and _target_value(r, target) is not None
    ]
    scored.sort(key=lambda item: item[0])
    nearest = [{"record": r, "distance": round(d, 3)} for d, r in scored[:5]]

    fingerprint = hashlib.sha256(
        json.dumps(
            [
                target,
                numeric,
                categories,
                [r["id"] for r in records],
                [r.get("outcomes", {}).get(target, {}).get("raw") for r in records],
            ],
            default=str,
        ).encode()
    ).hexdigest()
    fitted = _MODEL_CACHE.get(fingerprint)
    if fitted is None:
        fitted = (
            _fit(records, target, numeric, categories)
            if numeric
            else {
                "status": "insufficient_data",
                "n_train": 0,
                "features": categories,
                "reason": "The model needs at least one numeric condition.",
            }
        )
        _MODEL_CACHE[fingerprint] = fitted

    result: dict[str, Any] = {
        "status": fitted["status"],
        "reason": fitted.get("reason"),
        "prediction": None,
        "interval": None,
        "cv_mae": fitted.get("cv_mae"),
        "n_train": fitted["n_train"],
        "features": fitted["features"],
        "in_domain": False,
    }
    if fitted["status"] == "ok":
        outside: list[str] = [
            FIELDS[k]["label"]
            for k in numeric
            if not fitted["ranges"][k][0] <= inputs[k] <= fitted["ranges"][k][1]
        ]
        unseen = [k for k in categories if inputs[k] not in fitted["levels"][k]]
        if outside or unseen:
            result.update(
                status="insufficient_data",
                reason="Outside the conditions the model has seen: "
                + ", ".join([*outside, *[f"unseen {k}" for k in unseen]])
                + ".",
            )
        else:
            import numpy as np

            row = [inputs[k] for k in numeric] + [
                float(fitted["levels"][k].index(inputs[k])) for k in categories
            ]
            estimate = float(fitted["estimator"].predict(np.array([row]))[0])
            low, high = fitted["residual_band"]
            result.update(
                prediction=estimate, interval=[estimate + low, estimate + high], in_domain=True
            )
    return {
        "target": target,
        "nearest": nearest,
        "model": result,
        "notes": [
            "Statistical estimate from unreviewed candidate runs, not a validated prediction.",
            "The interval spans the 10th–90th percentile of cross-validation errors.",
            "Nearest runs are ranked by standardized distance over the conditions you entered.",
        ],
    }
