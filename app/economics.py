def format_inr(value):
    """
    Format a numeric value as Indian rupees.
    """

    value = float(value)

    if abs(value) >= 1_00_00_000:
        return f"₹{value / 1_00_00_000:.2f} Cr"

    if abs(value) >= 1_00_000:
        return f"₹{value / 1_00_000:.2f} L"

    return f"₹{value:,.0f}"


def calculate_transaction_economics(
    probability,
    amount,
    action,
    params,
):
    """
    Calculate expected transaction-level economics.

    This is a decision-support calculation only.
    It does not change model probability.
    """

    dispute_fee = float(
        params["dispute_fee"]
    )

    review_cost = float(
        params["ops_review_cost"]
    )

    merchant_margin = float(
        params["merchant_margin"]
    )

    abandon_rate = float(
        params["step_up_abandon_rate"]
    )

    expected_dispute_loss = (
        probability * dispute_fee
    )

    if action == "allow":

        intervention_cost = 0.0

        expected_net_value = (
            -expected_dispute_loss
        )

    elif action == "step_up":

        intervention_cost = (
            abandon_rate
            * merchant_margin
            * amount
        )

        expected_net_value = (
            -expected_dispute_loss
            - intervention_cost
        )

    elif action == "manual_review":

        intervention_cost = review_cost

        expected_net_value = (
            -expected_dispute_loss
            - intervention_cost
        )

    else:

        intervention_cost = 0.0
        expected_net_value = (
            -expected_dispute_loss
        )

    return {
        "expected_dispute_loss":
            expected_dispute_loss,

        "intervention_cost":
            intervention_cost,

        "expected_net_value":
            expected_net_value,
    }


def calculate_policy_economics(
    df,
    params,
):
    """
    Aggregate transaction-level economics.

    Expects:
        proba_calibrated
        amount
        recommended_action
    """

    if df.empty:
        return {
            "expected_dispute_loss": 0.0,
            "intervention_cost": 0.0,
            "expected_net_value": 0.0,
        }

    results = []

    for _, row in df.iterrows():

        results.append(
            calculate_transaction_economics(
                probability=row[
                    "proba_calibrated"
                ],
                amount=row["amount"],
                action=row[
                    "recommended_action"
                ],
                params=params,
            )
        )

    result_df = pd.DataFrame(results)

    return {
        "expected_dispute_loss":
            result_df[
                "expected_dispute_loss"
            ].sum(),

        "intervention_cost":
            result_df[
                "intervention_cost"
            ].sum(),

        "expected_net_value":
            result_df[
                "expected_net_value"
            ].sum(),
    }