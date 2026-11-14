import { expect, test } from "@playwright/test";

import { scoreDefaultForm } from "./helpers";

test.describe("Score a transaction", () => {
  test("the default form scores 0.46%, Allow, 0.5× base rate", async ({ page }) => {
    await scoreDefaultForm(page);
    await expect(page.getByTestId("probability")).toHaveText("0.46%");
    await expect(page.getByTestId("action-label")).toHaveText("Allow");
    await expect(page.getByTestId("lift")).toHaveText("0.5× base rate");
    await expect(page.getByTestId("decision-panel")).toContainText("Let this payment through.");
    await expect(page.getByTestId("decision-panel")).toHaveAttribute("data-action", "allow");
  });

  test("default drivers, in order, each with its direction in words", async ({ page }) => {
    await scoreDefaultForm(page);
    const rows = page.getByTestId("drivers").locator("li");
    await expect(rows).toHaveCount(5);
    // The build prompt lists +1.870 for the first driver; the Python modules
    // give 1.8724, and where the two disagree the Python modules win.
    const expected = [
      ["transaction amount (Rs 8,500)", "+1.872", "raises risk"],
      ["email domain type = personal", "−1.410", "lowers risk"],
      ["merchant category = travel", "−1.236", "lowers risk"],
      ["payment method = upi", "−1.006", "lowers risk"],
      ["phone verified: yes", "−0.300", "lowers risk"],
    ];
    for (const [i, [label, value, direction]] of expected.entries()) {
      await expect(rows.nth(i)).toContainText(label);
      await expect(rows.nth(i)).toContainText(`${value} ${direction}`);
    }
  });

  test('"Why this band" shows the three costs and both cuts', async ({ page }) => {
    await scoreDefaultForm(page);
    await expect(page.getByTestId("why-this-band")).toHaveText(
      "Why this band · allowing and being wrong costs ₹10,300; a 3DS step-up costs ₹382 in expected abandonment; a human review costs ₹300. Band cuts: 0.0244 / 0.0824.",
    );
  });

  test("the band track puts the cuts at 54.39% and 72.14%", async ({ page }) => {
    await scoreDefaultForm(page);
    const left = (testId: string) =>
      page
        .getByTestId(testId)
        .evaluateAll((nodes) => nodes.map((n) => parseFloat((n as HTMLElement).style.left).toFixed(2)));
    expect(await left("band-cut")).toEqual(["54.39", "72.14"]);
    const [dot] = await left("band-dot");
    expect(Number(dot)).toBeGreaterThan(0);
    expect(Number(dot)).toBeLessThan(54.39); // 0.46% sits in the Allow band
  });

  test("the reviewer note names its source", async ({ page }) => {
    await scoreDefaultForm(page);
    await expect(page.getByTestId("reviewer-note")).toContainText(
      "Scored 0.46% against a 0.90% portfolio base rate (0.5x)",
    );
    await expect(page.getByTestId("note-source")).toContainText(
      "Deterministic template — ANTHROPIC_API_KEY is not set.",
    );
  });

  test("the feature row opens as 26 features in fitted order", async ({ page, request }) => {
    await scoreDefaultForm(page);
    const table = page.getByTestId("feature-row");
    await expect(table).toBeHidden();
    await page.getByRole("button", { name: /The exact feature row sent to the model/ }).click();
    await expect(table.locator("tbody tr")).toHaveCount(26);

    const meta = await (await request.get("/api/meta")).json();
    const fitted = meta.feature_columns.map((c: { name: string }) => c.name);
    expect(await table.locator("tbody tr td:first-child").allTextContents()).toEqual(fitted);
    await expect(table.locator("tbody tr").first()).toContainText("9.047939");
  });

  test("changing an input flags the result as stale but keeps it", async ({ page }) => {
    await scoreDefaultForm(page);
    const stale = page.getByText("Inputs changed since the last score. Score again to refresh the result.");
    await expect(stale).toBeHidden();

    await page.getByLabel("Amount (₹)").fill("60000");
    await expect(stale).toBeVisible();
    await expect(page.getByTestId("probability")).toHaveText("0.46%");

    await page.getByRole("button", { name: "Score transaction" }).click();
    await expect(page.getByTestId("probability")).not.toHaveText("0.46%");
    await expect(stale).toBeHidden();

    // Putting the input back makes the result current again without a rescore.
    await page.getByLabel("Amount (₹)").fill("8500");
    await expect(stale).toBeVisible();
  });

  test("a risky transaction lands in Manual review", async ({ page }) => {
    await page.goto("/score");
    await page.getByLabel("Amount (₹)").fill("60000");
    await page.getByLabel("Method").selectOption("netbanking");
    await page.getByLabel("Email domain type").selectOption("disposable");
    await page.getByLabel("Phone verified").uncheck();
    await page.getByLabel("First transaction on this device").check();
    await page.getByLabel("Has any prior transaction").uncheck();
    await page.getByRole("button", { name: "Score transaction" }).click();
    await expect(page.getByTestId("action-label")).toHaveText("Manual review");
    await expect(page.getByTestId("decision-panel")).toContainText(
      "Hold for a human reviewer before capture.",
    );
  });

  test("changing merchant category resets the four merchant fields", async ({ page, request }) => {
    const meta = await (await request.get("/api/meta")).json();
    const gaming = meta.merchant_defaults.gaming;
    await page.goto("/score");
    await expect(page.getByLabel("Merchant average ticket size (₹)")).toHaveValue(
      String(meta.merchant_defaults.travel.avg_ticket_size),
    );
    await expect(page.getByLabel("Physical goods")).toBeChecked();
    await expect(page.getByLabel("Delivery SLA (days)")).toBeEnabled();

    await page.getByLabel("Merchant category").selectOption("gaming");
    await expect(page.getByLabel("Merchant average ticket size (₹)")).toHaveValue(
      String(gaming.avg_ticket_size),
    );
    await expect(page.getByLabel("Refund window (days)")).toHaveValue(String(gaming.refund_window_days));
    await expect(page.getByLabel("Delivery SLA (days)")).toHaveValue(String(gaming.delivery_sla_days));
    await expect(page.getByLabel("Physical goods")).not.toBeChecked();
    await expect(page.getByLabel("Delivery SLA (days)")).toBeDisabled();
  });

  test("an out-of-range input shows the API's error beside the button", async ({ page }) => {
    await scoreDefaultForm(page);
    await page.getByLabel("Amount (₹)").fill("0");
    await page.getByRole("button", { name: "Score transaction" }).click();
    const alert = page.locator("form").getByRole("alert");
    await expect(alert).toHaveText("Amount (₹): Input should be greater than or equal to 1.");
    await expect(alert).toHaveCSS("color", "rgb(158, 32, 25)");
    await expect(page.getByTestId("probability")).toHaveText("0.46%"); // result not cleared
  });

  test("sliders show their value beside the label", async ({ page }) => {
    await page.goto("/score");
    const row = (label: string) => page.locator("div", { has: page.getByText(label, { exact: true }) }).last();
    await expect(row("Hour of day").locator("output")).toHaveText("22");
    await expect(row("Account age at transaction (days)").locator("output")).toHaveText("450");
    await expect(row("Amount vs own 30-day average").locator("output")).toHaveText("1.0");
    await expect(row("Merchant trailing 90-day dispute rate").locator("output")).toHaveText("0.007");
  });
});
