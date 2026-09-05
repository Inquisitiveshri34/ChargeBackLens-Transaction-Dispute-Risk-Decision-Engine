def generate_reviewer_note(
    transaction,
    probability,
    action,
    drivers,
):
    """
    Generate a deterministic reviewer note.

    This function is intentionally isolated from the
    model and policy logic.

    An LLM can later replace this function without
    changing scoring or economics.
    """

    risk_pct = probability * 100

    if action == "allow":

        opening = (
            f"The transaction has a relatively low "
            f"predicted dispute probability ({risk_pct:.2f}%)."
        )

        recommendation = (
            "No additional intervention is recommended."
        )

    elif action == "step_up":

        opening = (
            f"The transaction has a moderate predicted "
            f"dispute probability ({risk_pct:.2f}%)."
        )

        recommendation = (
            "A step-up control is recommended before completion."
        )

    else:

        opening = (
            f"The transaction has a high predicted "
            f"dispute probability ({risk_pct:.2f}%)."
        )

        recommendation = (
            "Manual review is recommended before completion."
        )

    driver_text = " ".join(
        [
            f"{i + 1}. {driver}"
            for i, driver in enumerate(drivers[:3])
        ]
    )

    return (
        f"{opening} "
        f"{recommendation} "
        f"Key signals: {driver_text}"
    )