import { expect, test } from "@playwright/test";

import { cells, metric, setRange } from "./helpers";

const TOP_ROW = "pay_86bqtrjlsj9hg0";

test.describe("Review queue", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/queue");
    await expect(page.getByTestId("queue-table")).toBeVisible();
  });

  test("at 5% the slice is 250 transactions, 51 disputes, 20.40%, ₹5,08,255", async ({ page }) => {
    await expect(page.locator("output")).toHaveText("5.00");
    const metrics = page.getByTestId("queue-metrics");
    await expect(metric(metrics, "Transactions in slice")).toHaveText("250");
    await expect(metric(metrics, "Disputes caught")).toHaveText("51");
    await expect(metric(metrics, "Precision within slice")).toHaveText("20.40%");
    await expect(metric(metrics, "Exposure in slice")).toHaveText("₹5,08,255");
    await expect(page.getByTestId("queue-table").locator("tbody tr")).toHaveCount(250);
  });

  test("the top row is pay_86bqtrjlsj9hg0 at 33.44%, manual_review", async ({ page }) => {
    const first = page.getByTestId("queue-table").locator("tbody tr").first();
    expect(await cells(first)).toEqual([
      TOP_ROW,
      "2026-08-10 19:15",
      "₹59,931",
      "netbanking",
      "travel",
      "33.44%",
      "100.00",
      "manual_review",
      "Disputed",
    ]);
    await expect(first.locator("strong")).toHaveCSS("color", "rgb(158, 32, 25)");
  });

  test("selecting the top row opens its detail without error, and again closes it", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("response", (response) => {
      if (response.status() >= 400) errors.push(`${response.status()} ${response.url()}`);
    });

    const row = page.getByTestId("queue-table").locator("tbody tr").first();
    const detail = page.getByTestId("queue-detail");
    await expect(detail).toBeHidden();

    await page.getByRole("button", { name: TOP_ROW }).click();
    await expect(detail).toBeVisible();
    await expect(row).toHaveCSS("background-color", "rgb(240, 241, 245)");
    await expect(page.getByTestId("detail-payment-id")).toHaveText(TOP_ROW);
    await expect(page.getByTestId("detail-action")).toHaveText("Manual review");
    await expect(page.getByTestId("detail-probability")).toHaveText("33.44%");
    await expect(detail).toContainText("37.2× base rate");
    await expect(page.getByTestId("detail-amount")).toHaveText("₹59,931");
    await expect(page.getByTestId("detail-note")).toContainText(
      "driven mainly by transaction amount (Rs 59,931) and email domain type = disposable.",
    );
    await expect(detail).toContainText("Same note generator as Tab 1 — one code path, not a duplicate. Template fallback.");
    await expect(detail).toHaveAttribute("data-action", "manual_review");

    // The panel sits above the table.
    const panelBox = (await detail.boundingBox())!;
    const tableBox = (await page.getByTestId("queue-table").boundingBox())!;
    expect(panelBox.y + panelBox.height).toBeLessThanOrEqual(tableBox.y);

    await page.getByRole("button", { name: TOP_ROW }).click();
    await expect(detail).toBeHidden();
    expect(errors).toEqual([]);
  });

  test("moving the slider changes the slice and clears the selection", async ({ page }) => {
    await page.getByRole("button", { name: TOP_ROW }).click();
    await expect(page.getByTestId("queue-detail")).toBeVisible();

    await setRange(page.getByLabel("Work down the top k% of the queue"), 0.5);
    await expect(page.locator("output")).toHaveText("0.50");
    await expect(page.getByTestId("queue-detail")).toBeHidden();
    await expect(metric(page.getByTestId("queue-metrics"), "Transactions in slice")).toHaveText("25");
    await expect(page.getByTestId("queue-table").locator("tbody tr")).toHaveCount(25);
  });

  test("the action cell is a dot plus the raw action text", async ({ page }) => {
    await setRange(page.getByLabel("Work down the top k% of the queue"), 25);
    const table = page.getByTestId("queue-table");
    await expect(table.locator("tbody tr")).toHaveCount(1250);
    for (const action of ["manual_review", "step_up", "allow"]) {
      await expect(table.locator("tbody tr", { hasText: action }).first()).toBeVisible();
    }
    await expect(table.locator("tbody tr", { hasText: /No$/ }).first().locator("td").last()).toHaveText("No");
  });

  test("the header stays in view while the rows scroll inside a 620px box", async ({ page }) => {
    const box = page.getByRole("region", { name: "Queue rows" });
    expect((await box.boundingBox())!.height).toBeLessThanOrEqual(620);
    const header = page.getByTestId("queue-table").locator("thead th").first();
    const before = (await header.boundingBox())!.y;
    await box.evaluate((element) => (element.scrollTop = 2000));
    expect((await header.boundingBox())!.y).toBeCloseTo(before, 0);
  });
});
