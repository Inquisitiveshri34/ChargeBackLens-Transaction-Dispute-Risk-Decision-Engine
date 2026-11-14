"""
api/artifacts.py — everything the API reads from disk, loaded once at startup.

Nothing here computes a model number. It calls the loaders in app/scoring.py and
app/economics.py and holds the results, so a request never touches the disk.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

# Importable because api/__init__.py has already put app/ on sys.path.
import economics as ec
import scoring as sc


@dataclass(frozen=True)
class Artifacts:
    model: object
    contract: dict
    feature_columns: list[str]
    numeric_cols: list[str]
    categorical_cols: list[str]
    params: dict[str, float]
    card: dict[str, str]
    bands: pd.DataFrame
    segments: pd.DataFrame            # frozen table, sorted as Tab 3 shows it
    sensitivity: pd.DataFrame
    censoring: pd.Series
    deployed: pd.Series               # the is_deployed row of 05_model_comparison.csv
    importances: pd.DataFrame
    coefficients: pd.DataFrame
    queue: pd.DataFrame               # scored sample, highest risk first
    queue_by_id: pd.DataFrame
    basis_df: pd.DataFrame
    basis_weights: np.ndarray
    basis_label: str
    basis_exact: bool
    score_x_max: float                # 0.999 quantile of the score, Tab 3's x range

    @property
    def base_rate(self) -> float:
        return float(self.deployed["base_rate"])

    @property
    def default_cost_params(self) -> dict[str, float]:
        return {k: self.params[k] for k in ec.COST_PARAM_KEYS}


def _check_categorical_levels(coefficients: pd.DataFrame, categorical_cols: list[str]) -> None:
    """
    The form's option lists come from scoring.CATEGORICAL_LEVELS. Compare them
    with the levels the fitted model actually has a coefficient for, so a level
    the encoder has never seen cannot be offered as a valid input.
    """
    if set(sc.CATEGORICAL_LEVELS) != set(categorical_cols):
        raise sc.ArtifactError(
            f"scoring.CATEGORICAL_LEVELS covers {sorted(sc.CATEGORICAL_LEVELS)} but "
            f"04_feature_columns.csv lists {sorted(categorical_cols)} as categorical"
        )
    terms = coefficients["term"].astype(str)
    for col in categorical_cols:
        prefix = f"cat__{col}_"
        fitted = {t[len(prefix):] for t in terms if t.startswith(prefix)}
        declared = set(sc.CATEGORICAL_LEVELS[col])
        if fitted != declared:
            raise sc.ArtifactError(
                f"levels of `{col}` differ: scoring.CATEGORICAL_LEVELS has {sorted(declared)}, "
                f"04_model_coefficients.csv has {sorted(fitted)}"
            )
    if set(sc.MERCHANT_DEFAULTS) != set(sc.CATEGORICAL_LEVELS["merchant_category"]):
        raise sc.ArtifactError("scoring.MERCHANT_DEFAULTS does not cover every merchant category")


def load_artifacts() -> Artifacts:
    """
    Load the model and every CSV, then run the contract check.

    Raises scoring.ArtifactError if anything is missing, stale or inconsistent.
    The caller lets that propagate, which stops the server from starting.
    """
    model = sc.load_model()
    feature_columns, numeric_cols, categorical_cols = sc.load_feature_columns()
    contract = sc.assert_model_contract(model, feature_columns)

    coefficients = sc.load_model_coefficients()
    _check_categorical_levels(coefficients, categorical_cols)

    comparison = sc.load_model_comparison()
    deployed = comparison[comparison["is_deployed"].astype(bool)]
    if len(deployed) != 1:
        raise sc.ArtifactError(
            f"05_model_comparison.csv has {len(deployed)} rows marked is_deployed, expected 1")

    sample = sc.load_scored_sample()
    if sample["payment_id"].duplicated().any():
        raise sc.ArtifactError("05_scored_test_sample.csv has duplicate payment_id values")
    queue = sample.sort_values("proba_calibrated", ascending=False).reset_index(drop=True)

    basis_df, basis_weights, basis_label, basis_exact = ec.load_economics_basis()

    return Artifacts(
        model=model,
        contract=contract,
        feature_columns=feature_columns,
        numeric_cols=numeric_cols,
        categorical_cols=categorical_cols,
        params=sc.load_economics_params(),
        card=sc.load_model_card(),
        bands=sc.load_policy_bands(),
        segments=sc.load_segment_economics().sort_values("savings_per_intervention")
                                            .reset_index(drop=True),
        sensitivity=sc.load_sensitivity(),
        censoring=sc.load_censoring_audit(),
        deployed=deployed.iloc[0],
        importances=sc.load_feature_importances(),
        coefficients=coefficients,
        queue=queue,
        queue_by_id=queue.set_index("payment_id", drop=False),
        basis_df=basis_df,
        basis_weights=basis_weights,
        basis_label=basis_label,
        basis_exact=basis_exact,
        score_x_max=float(np.quantile(basis_df["proba_calibrated"], 0.999)),
    )
