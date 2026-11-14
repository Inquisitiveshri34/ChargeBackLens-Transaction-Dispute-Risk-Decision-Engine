import { expect, test } from "@playwright/test";

/**
 * Behaviour that only matters once the site is hosted: the API may be asleep
 * when a visitor arrives.
 */

test("a request is retried while the API wakes, instead of showing an error", async ({ page }) => {
  let metaCalls = 0;
  await page.route("**/api/meta", async (route) => {
    metaCalls += 1;
    if (metaCalls <= 2) {
      // What a hosting proxy answers while the origin is still starting.
      await route.fulfill({ status: metaCalls === 1 ? 502 : 504, body: "upstream not ready" });
    } else {
      await route.continue();
    }
  });

  await page.goto("/score");
  await expect(page.getByRole("status")).toHaveText("Loading the form…");
  await expect(page.getByRole("button", { name: "Score transaction" })).toBeVisible({ timeout: 15_000 });
  expect(metaCalls).toBe(3);
  // Scoped to the page content: Next.js keeps its own hidden live region outside it.
  await expect(page.locator("main").getByRole("alert")).toHaveCount(0);
});

test("an error the API explains is shown at once, not retried", async ({ page }) => {
  let scoreCalls = 0;
  page.on("request", (request) => {
    if (request.url().endsWith("/api/score")) scoreCalls += 1;
  });
  await page.goto("/score");
  await page.getByLabel("Amount (₹)").fill("0");
  await page.getByRole("button", { name: "Score transaction" }).click();
  await expect(page.locator("form").getByRole("alert")).toContainText("Amount (₹)");
  expect(scoreCalls).toBe(1);
});

for (const path of ["/", "/score", "/queue", "/economics"]) {
  test(`opening ${path} pings the API once so a sleeping one starts waking`, async ({ page }) => {
    const pings: string[] = [];
    page.on("request", (request) => {
      if (new URL(request.url()).pathname === "/api/health") pings.push(request.url());
    });
    await page.goto(path);
    await expect.poll(() => pings.length).toBe(1);
  });
}

test("the proxy passes the API's cache policy through untouched", async ({ request }) => {
  expect((await request.get("/api/meta")).headers()["cache-control"]).toContain("s-maxage=300");
  expect((await request.get("/api/queue")).headers()["cache-control"]).toBe("no-store");
  expect((await request.get("/api/health")).headers()["cache-control"]).toBe("no-store");
});
