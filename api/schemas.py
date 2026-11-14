"""
api/schemas.py — request bodies, validated to the same ranges as the form.

The ranges are the ones on the Streamlit widgets in app/streamlit_app.py. A
value outside them is a 422 with the field named, not a silently clipped input.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import (BaseModel, BeforeValidator, ConfigDict, Field, NaiveDatetime,
                      ValidationInfo, field_validator)

import scoring as sc


class ScoreRequest(BaseModel):
    """
    The 23 inputs scoring.build_feature_row() takes. The form's Date and Hour of
    day arrive combined as `created_at` (for example 2026-09-15T22:00:00), with
    no timezone, because the model reads the hour exactly as entered.
    """

    model_config = ConfigDict(extra="forbid")

    # Transaction
    amount: float = Field(ge=1, le=500_000)
    method: str
    merchant_category: str
    created_at: NaiveDatetime
    retry_count: int = Field(ge=0, le=10)
    checkout_latency_ms: int = Field(ge=0, le=30_000)

    # Customer & merchant
    merchant_avg_ticket_size: float = Field(ge=1)
    email_domain_type: str
    phone_verified: bool
    account_age_days_at_txn: int = Field(ge=0, le=2_500)
    is_first_txn_for_device: bool
    is_foreign_bin: bool
    is_physical_goods: bool
    refund_window_days: int = Field(ge=0, le=60)
    delivery_sla_days: int = Field(ge=0, le=30)

    # Trailing history (manual override)
    txns_last_24h: int = Field(ge=0, le=5)
    txns_last_7d: int = Field(ge=0, le=10)
    distinct_devices_30d: int = Field(ge=0, le=6)
    prior_disputes_before_this_txn: int = Field(ge=0, le=5)
    has_prior_history: bool
    ip_state_changed_from_prev_txn: bool
    amount_vs_own_avg: float = Field(ge=0.1, le=10)
    merchant_dispute_rate_trailing_90d: float = Field(ge=0.001, le=0.030)

    @field_validator("method", "merchant_category", "email_domain_type")
    @classmethod
    def _known_level(cls, value: str, info: ValidationInfo) -> str:
        allowed = sc.CATEGORICAL_LEVELS[info.field_name]
        if value not in allowed:
            raise ValueError(f"must be one of: {', '.join(allowed)}")
        return value

    def to_form(self) -> dict:
        """Same shapes Tab 1 hands to build_feature_row (floats and ints as there)."""
        return {
            "amount": self.amount,
            "created_at": self.created_at,
            "merchant_avg_ticket_size": self.merchant_avg_ticket_size,
            "retry_count": self.retry_count,
            "checkout_latency_ms": self.checkout_latency_ms,
            "is_foreign_bin": self.is_foreign_bin,
            "is_first_txn_for_device": self.is_first_txn_for_device,
            "account_age_days_at_txn": self.account_age_days_at_txn,
            "refund_window_days": self.refund_window_days,
            "delivery_sla_days": self.delivery_sla_days,
            "is_physical_goods": self.is_physical_goods,
            "phone_verified": self.phone_verified,
            "method": self.method,
            "merchant_category": self.merchant_category,
            "email_domain_type": self.email_domain_type,
            "txns_last_24h": float(self.txns_last_24h),
            "txns_last_7d": float(self.txns_last_7d),
            "distinct_devices_30d": float(self.distinct_devices_30d),
            "prior_disputes_before_this_txn": self.prior_disputes_before_this_txn,
            "amount_vs_own_avg": self.amount_vs_own_avg,
            "has_prior_history": int(self.has_prior_history),
            "ip_state_changed_from_prev_txn": int(self.ip_state_changed_from_prev_txn),
            "merchant_dispute_rate_trailing_90d": self.merchant_dispute_rate_trailing_90d,
        }


def _round6(value):
    """
    Slider arithmetic in a browser can send 0.35000000000000003 for 0.35. Round
    before the range check so that is neither a spurious 422 nor a second cache
    entry for the same slider position.
    """
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return round(float(value), 6)
    return value


SliderFloat = Annotated[float, BeforeValidator(_round6)]


class EconomicsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dispute_fee: SliderFloat = Field(ge=500, le=3_000)
    ops_review_cost: SliderFloat = Field(ge=100, le=800)
    merchant_margin: SliderFloat = Field(ge=0.05, le=0.35)
    step_up_abandon_rate: SliderFloat = Field(ge=0.05, le=0.50)
    live_segments: bool = False
