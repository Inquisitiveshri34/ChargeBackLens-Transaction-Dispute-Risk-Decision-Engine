"""POST /api/economics — Tab 3, against the figures notebook 5 exported."""

import pytest

from fmt import cut, pct, rupees


def run(client, base, **overrides):
    response = client.post("/api/economics", json={**base, **overrides})
    assert response.status_code == 200, response.text
    return response.json()


def cuts(body):
    bands = body["bands"]
    return f"{cut(bands['threshold_allow_stepup'])} / {cut(bands['threshold_stepup_review'])}"


def test_defaults_reproduce_the_exported_policy(client, default_economics):
    body = run(client, default_economics)
    bands = body["bands"]
    assert rupees(bands["net_savings_inr"]) == "₹11,99,620"
    assert pct(bands["share_of_exposure"], 1) == "39.1%"
    assert cuts(body) == "0.0244 / 0.0824"
    assert (bands["interventions"], bands["n_review"], bands["n_stepup"]) == (3094, 308, 2786)
    assert body["basis"]["is_exact"] is True
    assert body["at_default"] is True
    assert body["reproduces_export"] is True
    assert body["baseline_shifted"] is False
    assert rupees(body["exported_policy"]["net_savings_inr"]) == "₹11,99,620"


def test_single_threshold_at_defaults(client, default_economics):
    single = run(client, default_economics)["single_threshold"]
    assert rupees(single["net_savings_inr"]) == "₹10,80,993"
    assert rupees(single["second_cut_value_inr"]) == "₹1,18,627"


def test_abandon_rate_010(client, default_economics):
    body = run(client, default_economics, step_up_abandon_rate=0.10)
    assert rupees(body["bands"]["net_savings_inr"]) == "₹18,11,639"
    assert cuts(body) == "0.0143 / 0.1460"
    assert (body["bands"]["n_review"], body["bands"]["n_stepup"]) == (41, 6255)
    assert body["at_default"] is False
    assert body["baseline_shifted"] is False      # abandon rate does not move the baseline


def test_ops_review_cost_200(client, default_economics):
    body = run(client, default_economics, ops_review_cost=200)
    bands = body["bands"]
    assert rupees(bands["net_savings_inr"]) == "₹12,83,130"
    assert cuts(body) == "0.0244 / 0.0283"
    assert (bands["n_review"], bands["n_stepup"]) == (2509, 585)
    assert rupees(bands["total_cost_inr"]) == "₹17,45,717"
    assert body["baseline_shifted"] is True       # the amber "not comparable" line
    assert body["reproduces_export"] is False


def test_dispute_fee_also_shifts_the_baseline(client, default_economics):
    assert run(client, default_economics, dispute_fee=2000)["baseline_shifted"] is True
    assert run(client, default_economics, merchant_margin=0.2)["baseline_shifted"] is False


def test_sweep_has_101_points_and_the_chart_range(client, default_economics):
    body = run(client, default_economics)
    sweep = body["sweep"]
    assert len(sweep) == 101
    thresholds = [point["threshold"] for point in sweep]
    assert thresholds == sorted(thresholds)
    assert max(point["net_savings_inr"] for point in sweep) == body["single_threshold"]["net_savings_inr"]
    assert f"{body['x_max']:.4f}" == "0.1374"


def segment_cells(row):
    return (row["segment_value"], pct(row["dispute_rate"], 3),
            rupees(row["net_savings_at_global_policy"]), rupees(row["savings_per_intervention"]))


def test_frozen_segment_table_first_and_last_rows(client, default_economics):
    segments = run(client, default_economics)["segments"]
    assert segments["source"] == "frozen"
    rows = segments["rows"]
    assert len(rows) == 15
    # dispute_rate is a fraction in the API; x100 gives the 0.763% that the
    # Streamlit table used to show as 0.008%.
    assert segment_cells(rows[0]) == ("wallet", "0.763%", "₹9,479", "₹47")
    assert rupees(rows[0]["review_band_net_inr"]) == "−₹300"
    assert segment_cells(rows[-1]) == (">10000", "3.278%", "₹7,98,514", "₹1,434")
    per_intervention = [r["savings_per_intervention"] for r in rows]
    assert per_intervention == sorted(per_intervention)


def test_live_segments_at_defaults_match_the_frozen_table(client, default_economics):
    frozen = run(client, default_economics)["segments"]["rows"]
    live = run(client, default_economics, live_segments=True)["segments"]
    assert live["source"] == "live"
    assert len(live["rows"]) == len(frozen)
    for frozen_row, live_row in zip(frozen, live["rows"]):
        assert frozen_row.keys() == live_row.keys()
        for key, value in frozen_row.items():
            if isinstance(value, str):
                assert live_row[key] == value
            else:
                assert live_row[key] == pytest.approx(value, rel=1e-9, abs=1e-6), key


def test_live_segments_move_with_the_sliders(client, default_economics):
    frozen = run(client, default_economics)["segments"]["rows"]
    live = run(client, default_economics, step_up_abandon_rate=0.10, live_segments=True)["segments"]["rows"]
    assert [r["n_stepup"] for r in live] != [r["n_stepup"] for r in frozen]


def test_result_is_cached_on_the_parameters_and_the_flag(client, default_economics):
    engine = client.app.state.economics
    body = {**default_economics, "merchant_margin": 0.07, "step_up_abandon_rate": 0.33}
    before = engine.run.cache_info()
    first = client.post("/api/economics", json=body).json()
    second = client.post("/api/economics", json=body).json()
    # 0.07 + float noise from slider arithmetic is the same slider position.
    third = client.post("/api/economics", json={**body, "merchant_margin": 0.07000000000000002}).json()
    client.post("/api/economics", json={**body, "live_segments": True})
    after = engine.run.cache_info()
    assert first == second == third
    assert after.misses - before.misses == 2      # one per flag value
    assert after.hits - before.hits == 2


@pytest.mark.parametrize("field, value", [
    ("dispute_fee", 499), ("dispute_fee", 3001),
    ("ops_review_cost", 99), ("ops_review_cost", 801),
    ("merchant_margin", 0.04), ("merchant_margin", 0.36),
    ("step_up_abandon_rate", 0.04), ("step_up_abandon_rate", 0.51),
])
def test_out_of_range_parameter_is_a_422(client, default_economics, field, value):
    response = client.post("/api/economics", json={**default_economics, field: value})
    assert response.status_code == 422
    assert response.json()["fields"][0]["field"] == field
