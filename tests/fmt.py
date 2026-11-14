"""
The display rules the acceptance numbers are written in, so a test can assert
"₹11,99,620" rather than a float. Python's round() is half-to-even, which is the
rule the front end has to match.
"""


def rupees(value: float) -> str:
    """Indian grouping with a true minus sign: -300 -> −₹300, 1199620.19 -> ₹11,99,620."""
    whole = round(abs(float(value)))
    digits = str(whole)
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        digits = ",".join(groups + [tail])
    return f"{'−' if value < 0 else ''}₹{digits}"


def pct(fraction: float, decimals: int = 2) -> str:
    return f"{fraction * 100:.{decimals}f}%"


def cut(threshold: float) -> str:
    return f"{threshold:.4f}"


def signed3(value: float) -> str:
    return f"{'−' if value < 0 else '+'}{abs(value):.3f}"
