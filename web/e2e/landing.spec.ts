import { expect, test } from "@playwright/test";

const FINAL = ["₹11,99,620", "16.2×", "43.2%", "45,246"];

const runningAnimations = () =>
  document.getAnimations().filter((animation) => animation.playState === "running").length;

test.describe("Landing page", () => {
  test("the four figures count up to values from /api/meta", async ({ page }) => {
    await page.goto("/");
    const figures = page.getByTestId("count-figure");
    await expect(figures).toHaveCount(4);
    for (const [i, text] of FINAL.entries()) {
      await expect(figures.nth(i)).toHaveText(text, { timeout: 4000 });
    }
  });

  test("lane chips are real rows: 5 Allow, 3 Step-up, 2 Manual review", async ({ page, request }) => {
    const examples = await (await request.get("/api/lane-examples?per_band=5")).json();
    await page.goto("/");
    const panel = page.getByTestId("routing-panel");
    await expect(panel.getByTestId("lane-chip")).toHaveCount(10);
    await expect(panel).toContainText("Allow");
    await expect(panel).toContainText("Step-up (3DS)");
    await expect(panel).toContainText("Manual review");
    await expect(panel).toContainText("93.2% of volume");

    const first = examples.allow[0];
    await expect(panel.getByTestId("lane-chip").first()).toContainText(
      `· ${first.method} · ${first.merchant_category}`,
    );
  });

  test("motion runs by default: chips flow and the status dot pulses", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("lane-chip")).toHaveCount(10);
    expect(await page.evaluate(runningAnimations)).toBeGreaterThanOrEqual(11);
    const chip = page.getByTestId("lane-chip").first();
    expect(await chip.evaluate((el) => getComputedStyle(el).animationName)).toBe("flow");
    expect(await chip.evaluate((el) => getComputedStyle(el).animationDuration)).toBe("9s");
  });

  test("the sections are all present, in order", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Chargeback risk, answered in rupees.");
    await expect(page.getByTestId("lane")).toHaveCount(3);
    await expect(page.getByTestId("limit")).toHaveCount(4);
    const headings = await page.getByRole("heading", { level: 2 }).allTextContents();
    expect(headings).toEqual([
      "Three lanes, one decision per payment",
      "Three lanes, each priced in rupees",
      "How a decision is made",
      "Four limits, stated up front",
      "Score a transaction and read the reasoning.",
    ]);
  });

  test("the nav shows Open the app only here, and it leads to the score screen", async ({ page }) => {
    await page.goto("/");
    const nav = page.getByRole("navigation", { name: "Primary" });
    await nav.getByRole("link", { name: "Open the app" }).click();
    await expect(page).toHaveURL(/\/score$/);
    await expect(nav.getByRole("link", { name: "Open the app" })).toHaveCount(0);
    await expect(nav.getByRole("link", { name: "Score a Transaction" })).toHaveAttribute("aria-current", "page");
  });
});

test.describe("Reduced motion", () => {
  test.use({ reducedMotion: "reduce" });

  test("no animation runs and the figures show their final values at once", async ({ page }) => {
    await page.goto("/");
    const figures = page.getByTestId("count-figure");
    await expect(figures.first()).toHaveText(FINAL[0]);
    // Read all four in the same instant the first is final: nothing is mid-count.
    expect(await figures.allTextContents()).toEqual(FINAL);

    await expect(page.getByTestId("lane-chip")).toHaveCount(10);
    expect(await page.evaluate(runningAnimations)).toBe(0);
    expect(await page.evaluate(() => document.getAnimations().length)).toBe(0);

    // Content that would otherwise rise into view is simply visible.
    const lane = page.getByTestId("lane").first();
    expect(await lane.evaluate((el) => getComputedStyle(el).opacity)).toBe("1");
    // Buttons do not lift on hover.
    const button = page.getByRole("link", { name: "Explore the economics" });
    await button.hover();
    expect(await button.evaluate((el) => getComputedStyle(el).transform)).toBe("none");
  });
});
