"""explain._describe — the label a reviewer reads for each driver."""

import numpy as np

import explain as ex


def test_categorical_raw_value_without_a_level_is_named_not_floated():
    """Tab 2 passes the row's own value with level=None; a string must not reach float()."""
    assert ex._describe("email_domain_type", None, "disposable") == "email domain type = disposable"
    assert ex._describe("method", None, "netbanking") == "payment method = netbanking"
    assert ex._describe("merchant_category", float("nan"), "travel") == "merchant category = travel"


def test_numeric_and_flag_values_keep_their_formats():
    assert ex._describe("log_amount", None, np.log1p(59930.61)) == "transaction amount (Rs 59,931)"
    assert ex._describe("phone_verified", None, 0) == "phone verified: no"
    assert ex._describe("has_prior_history", None, 1.0) == "has prior transaction history: yes"
    assert ex._describe("retry_count", None, 2) == "failed auth attempts before success = 2"
    assert ex._describe("method", "upi", "upi") == "payment method = upi"
    assert ex._describe("retry_count", None, None) == "failed auth attempts before success"
