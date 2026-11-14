import { expect, test } from "@playwright/test";

import { cells, metric, metricSub, setRange } from "./helpers";

test.describe("Economics explorer", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/economics");
    await expect(page.getByTestId("economics-metrics")).toBeVisible();
  });

  test("the shared summary shows the four headline figures", async ({ page }) => {
    const headline = page.getByTestId("headline");
    await expect(metric(headline, "Net savings at the deployed policy")).toHaveText("₹11,99,620");
    await expect(metricSub(headline, "Net savings at the deployed policy")).toHaveText("39.1% of exposure");
    await expect(metric(headline, "Lift at the top 1% of the queue")).toHaveText("16.2×");
    await expect(metricSub(headline, "Lift at the top 1% of the queue")).toHaveText("precision 14.6%");
    await expect(metric(headline, "Manual-review band")).toHaveText("308 txns");
    await expect(metricSub(headline, "Manual-review band")).toHaveText("18.8× base rate");
    await expect(metricSub(headline, "Test base rate")).toHaveText("407 disputes in 45,246");
  });

  test("the four caveats open from the disclosure link", async ({ page }) => {
    const first = page.getByText("294 of 407 test disputes (72.2%) were raised after the declared 2026-11-01 snapshot");
    await expect(first).toBeHidden();
    await page.getByRole("button", { name: /Four things to read before the rupee figures/ }).click();
    await expect(first).toBeVisible();
    await expect(page.getByText(", the latest on 2027-01-26.")).toBeVisible();
    await expect(page.locator("ol > li")).toHaveCount(4);
  });

  test("defaults: ₹11,99,620, 39.1%, cuts 0.0244 / 0.0824, 3,094 interventions", async ({ page }) => {
    const metrics = page.getByTestId("economics-metrics");
    await expect(metric(metrics, "Net savings (three-band)")).toHaveText("₹11,99,620");
    await expect(metricSub(metrics, "Net savings (three-band)")).toHaveText("39.1% of exposure");
    await expect(metric(metrics, "Allow / step-up cut")).toHaveText("0.0244");
    await expect(metric(metrics, "Allow / step-up cut")).toHaveCSS("color", "rgb(138, 78, 0)");
    await expect(metric(metrics, "Step-up / review cut")).toHaveText("0.0824");
    await expect(metric(metrics, "Step-up / review cut")).toHaveCSS("color", "rgb(158, 32, 25)");
    await expect(metric(metrics, "Interventions")).toHaveText("3,094");
    await expect(metricSub(metrics, "Interventions")).toHaveText("308 review · 2,786 step-up");

    await expect(page.getByText("04_test_predictions.csv (45,246 rows, exact)")).toBeVisible();
    await expect(page.getByTestId("reproduces-line")).toContainText(
      "reproduces the exported policy exactly: ₹11,99,620 at cuts 0.0244 / 0.0824.",
    );
    await expect(page.getByTestId("reproduces-line")).toHaveCSS("color", "rgb(11, 100, 68)");
    await expect(page.getByTestId("not-comparable-line")).toBeHidden();
  });

  test("single threshold at defaults: ₹10,80,993; second cut worth ₹1,18,627", async ({ page }) => {
    await expect(page.getByTestId("single-threshold-line")).toHaveText(
      "A single-threshold policy on the same parameters earns ₹10,80,993. The second cut is worth ₹1,18,627 — the measured justification for two thresholds instead of one.",
    );
  });

  test("abandon rate 0.10: ₹18,11,639; cuts 0.0143 / 0.1460; 41 review · 6,255 step-up", async ({ page }) => {
    await setRange(page.getByLabel("Step-up abandon rate"), 0.1);
    const metrics = page.getByTestId("economics-metrics");
    await expect(metric(metrics, "Net savings (three-band)")).toHaveText("₹18,11,639");
    await expect(metric(metrics, "Allow / step-up cut")).toHaveText("0.0143");
    await expect(metric(metrics, "Step-up / review cut")).toHaveText("0.1460");
    await expect(metricSub(metrics, "Interventions")).toHaveText("41 review · 6,255 step-up");
    await expect(page.getByTestId("reproduces-line")).toBeHidden();
    await expect(page.getByTestId("not-comparable-line")).toBeHidden();
    // The review cut is past the chart's x range; the legend says so.
    await expect(page.getByTestId("chart-legend")).toContainText("step-up / review cut 0.1460 (beyond the chart range)");
    await expect(page.getByTestId("cut-line")).toHaveCount(1);
  });

  test("ops review cost 200: ₹12,83,130; total cost ₹17,45,717; amber line shown", async ({ page }) => {
    await setRange(page.getByLabel("Ops review cost (₹)"), 200);
    const metrics = page.getByTestId("economics-metrics");
    await expect(metric(metrics, "Net savings (three-band)")).toHaveText("₹12,83,130");
    await expect(metric(metrics, "Allow / step-up cut")).toHaveText("0.0244");
    await expect(metric(metrics, "Step-up / review cut")).toHaveText("0.0283");
    await expect(metricSub(metrics, "Interventions")).toHaveText("2,509 review · 585 step-up");
    const amber = page.getByTestId("not-comparable-line");
    await expect(amber).toContainText("not comparable to the default run — compare total cost instead (₹17,45,717 now).");
    await expect(amber).toHaveCSS("color", "rgb(122, 75, 0)");
  });

  test("segment table: wallet first, >10000 last, negative review net in bold red", async ({ page }) => {
    const table = page.getByTestId("segment-table");
    await expect(table).toHaveAttribute("data-source", "frozen");
    const rows = table.locator("tbody tr");
    await expect(rows).toHaveCount(15);

    const wallet = await cells(rows.first());
    expect(wallet.slice(0, 2)).toEqual(["method", "wallet"]);
    expect(wallet[3]).toBe("0.763%"); // the fraction x100; Streamlit used to show 0.008%
    expect(wallet[5]).toBe("₹9,479");
    expect(wallet[6]).toBe("₹47");
    expect(wallet[7]).toBe("−₹300");
    const reviewNet = rows.first().locator("td").nth(7);
    await expect(reviewNet).toHaveCSS("color", "rgb(158, 32, 25)");
    await expect(reviewNet).toHaveCSS("font-weight", "600");

    const big = await cells(rows.last());
    expect(big.slice(0, 2)).toEqual(["amount_bucket", ">10000"]);
    expect([big[3], big[5], big[6]]).toEqual(["3.278%", "₹7,98,514", "₹1,434"]);
    await expect(rows.last().locator("td").nth(7)).toHaveCSS("font-weight", "400");
  });

  test("live segments at defaults are identical to the frozen table", async ({ page }) => {
    const table = page.getByTestId("segment-table");
    const frozen = await table.locator("tbody").innerText();
    const toggle = page.getByRole("switch", { name: /Recompute segments at the current sliders/ });
    await expect(toggle).not.toBeChecked();

    await toggle.check();
    await expect(table).toHaveAttribute("data-source", "live");
    expect(await table.locator("tbody").innerText()).toBe(frozen);

    // And the live table does follow the sliders.
    await setRange(page.getByLabel("Step-up abandon rate"), 0.1);
    await expect(metric(page.getByTestId("economics-metrics"), "Step-up / review cut")).toHaveText("0.1460");
    await expect.poll(async () => table.locator("tbody").innerText()).not.toBe(frozen);
  });

  test("the chart has 0.02 x ticks, at most 7 lakh y ticks, and both cut lines", async ({ page }) => {
    const chart = page.getByTestId("sweep-chart");
    await expect(chart).toBeVisible();
    expect((await chart.boundingBox())!.height).toBe(360);

    expect(await page.getByTestId("x-tick").allTextContents()).toEqual([
      "0.00", "0.02", "0.04", "0.06", "0.08", "0.10", "0.12",
    ]);
    const yTicks = await page.getByTestId("y-tick").allTextContents();
    expect(yTicks.length).toBeLessThanOrEqual(7);
    expect(yTicks).toContain("0");
    for (const tick of yTicks) expect(tick).toMatch(/^(0|−?₹[\d.]+L)$/);

    const lines = page.getByTestId("cut-line");
    await expect(lines).toHaveCount(2);
    await expect(lines.nth(0)).toHaveAttribute("stroke-dasharray", "7 5"); // dashed: allow / step-up
    await expect(lines.nth(1)).toHaveAttribute("stroke-dasharray", "2 4"); // dotted: step-up / review
    await expect(chart.locator("polyline")).toHaveAttribute("stroke-width", "2.5");
    await expect(page.getByTestId("chart-legend").locator("li")).toHaveCount(3);
  });

  test("the frozen sensitivity table opens with its 22 rows", async ({ page }) => {
    const table = page.getByTestId("sensitivity-table");
    await expect(table).toBeHidden();
    await page.getByRole("button", { name: /Frozen sensitivity analysis/ }).click();
    await expect(table.locator("tbody tr")).toHaveCount(22);
    expect(await cells(table.locator("tbody tr").first())).toEqual([
      "step_up_abandon_rate", "0.1", "0.0143", "0.1460", "41", "6,255", "₹18,11,639",
    ]);
  });
});
