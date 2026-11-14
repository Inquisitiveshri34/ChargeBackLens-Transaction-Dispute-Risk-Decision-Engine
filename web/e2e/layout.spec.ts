import AxeBuilder from "@axe-core/playwright";
import { type Page, expect, test } from "@playwright/test";

/**
 * Responsive and accessibility checks for every screen, plus the screenshots
 * for the side-by-side comparison with the prototype (e2e/screenshots/).
 */

const SCREENS: { name: string; path: string; ready: (page: Page) => Promise<void> }[] = [
  {
    name: "landing",
    path: "/",
    ready: async (page) => {
      await expect(page.getByTestId("lane-chip")).toHaveCount(10);
      await expect(page.getByTestId("count-figure").first()).toHaveText("₹11,99,620");
    },
  },
  {
    name: "score",
    path: "/score",
    ready: async (page) => {
      await page.getByRole("button", { name: "Score transaction" }).click();
      await expect(page.getByTestId("decision-panel")).toBeVisible();
    },
  },
  {
    name: "queue",
    path: "/queue",
    ready: async (page) => {
      await page.getByRole("button", { name: "pay_86bqtrjlsj9hg0" }).click();
      await expect(page.getByTestId("detail-note")).toContainText("Recommended:");
    },
  },
  {
    name: "economics",
    path: "/economics",
    ready: async (page) => {
      await expect(page.getByTestId("sweep-chart")).toBeVisible();
      await expect(page.getByTestId("segment-table")).toBeVisible();
    },
  },
];

const WIDTHS = [1400, 390];

for (const screen of SCREENS) {
  for (const width of WIDTHS) {
    test.describe(`${screen.name} at ${width}px`, () => {
      // Reduced motion so a full-page capture shows every section in place.
      test.use({ viewport: { width, height: 900 }, reducedMotion: "reduce" });

      test("fits the viewport, keeps 44px targets, and passes axe", async ({ page }) => {
        await page.goto(screen.path);
        await screen.ready(page);

        // Wide tables scroll inside their own box; the page itself never does.
        const overflow = await page.evaluate(
          () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
        );
        expect(overflow).toBe(0);

        // Checkboxes are exempt: their 44px label is the target. So is the skip
        // link, which is off-screen until it takes focus.
        const small = await page
          .locator("a:visible:not(.sr-only), button:visible, select:visible, input:visible:not([type=checkbox])")
          .evaluateAll((nodes) =>
            nodes
              .filter((node) => node.getBoundingClientRect().height < 44)
              .map((node) => `${node.tagName} "${(node.textContent || node.getAttribute("aria-label") || "").trim().slice(0, 40)}" ${node.getBoundingClientRect().height}px`),
          );
        expect(small).toEqual([]);
        const labels = await page
          .locator("label:has(input[type=checkbox]):visible")
          .evaluateAll((nodes) => nodes.map((node) => node.getBoundingClientRect().height));
        for (const height of labels) expect(height).toBeGreaterThanOrEqual(44);

        // WCAG 2.1 A and AA, which includes the 4.5:1 text contrast rule.
        const axe = await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
          .analyze();
        expect(
          axe.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(" | ")}`),
        ).toEqual([]);

        await page.evaluate(() => window.scrollTo(0, 0));
        await page.screenshot({
          path: `e2e/screenshots/${screen.name}-${width}.png`,
          fullPage: true,
        });
      });
    });
  }
}

test.describe("navigation bar", () => {
  test("is a dark sticky pill with the active screen as a white pill", async ({ page }) => {
    await page.goto("/queue");
    const nav = page.getByRole("navigation", { name: "Primary" });
    await expect(nav).toHaveCSS("background-color", "rgb(17, 19, 24)");
    await expect(nav).toHaveCSS("border-radius", "30px");
    await expect(nav).toHaveCSS("padding", "8px 10px 8px 22px");
    await expect(nav).toHaveCSS("box-shadow", /rgba\(17, 19, 24, 0\.22\) 0px 12px 32px 0px$/);

    const active = nav.getByRole("link", { name: "Review Queue" });
    await expect(active).toHaveAttribute("aria-current", "page");
    await expect(active).toHaveCSS("background-color", "rgb(255, 255, 255)");
    await expect(active).toHaveCSS("color", "rgb(17, 19, 24)");
    await expect(nav.getByRole("link", { name: "Economics Explorer" })).toHaveCSS("color", "rgb(228, 230, 236)");

    // 14px from the top, and it stays there when the page scrolls.
    expect((await nav.boundingBox())!.y).toBe(14);
    await page.mouse.wheel(0, 600);
    await expect.poll(async () => (await nav.boundingBox())!.y).toBe(14);

    await nav.getByRole("link", { name: "ChargebackLens" }).click();
    await expect(page).toHaveURL(/\/$/);
  });

  test("wraps on a narrow screen without hiding any link", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 800 });
    await page.goto("/score");
    const nav = page.getByRole("navigation", { name: "Primary" });
    for (const name of ["ChargebackLens", "Score a Transaction", "Review Queue", "Economics Explorer"]) {
      await expect(nav.getByRole("link", { name })).toBeVisible();
    }
    const box = (await nav.boundingBox())!;
    expect(box.x).toBe(28);
    expect(box.width).toBe(390 - 56);
  });
});

test.describe("keyboard", () => {
  test("focus shows a 3px indigo ring with a 2px offset", async ({ page }) => {
    await page.goto("/score");
    const amount = page.getByLabel("Amount (₹)");
    await amount.focus();
    await page.keyboard.press("Tab");
    await page.keyboard.press("Shift+Tab"); // arrive by keyboard so :focus-visible applies
    await expect(amount).toBeFocused();
    await expect(amount).toHaveCSS("outline-style", "solid");
    await expect(amount).toHaveCSS("outline-width", "3px");
    await expect(amount).toHaveCSS("outline-color", "rgb(79, 70, 229)");
    await expect(amount).toHaveCSS("outline-offset", "2px");
  });

  test("the whole score flow works from the keyboard", async ({ page }) => {
    await page.goto("/score");
    await page.keyboard.press("Tab");
    await expect(page.getByRole("link", { name: "Skip to content" })).toBeFocused();

    await page.getByLabel("Amount (₹)").focus();
    await page.keyboard.press("Enter"); // Enter in a field submits the form
    await expect(page.getByTestId("probability")).toHaveText("0.46%");

    const disclosure = page.getByRole("button", { name: /The exact feature row sent to the model/ });
    await disclosure.focus();
    await page.keyboard.press("Enter");
    await expect(disclosure).toHaveAttribute("aria-expanded", "true");
    await expect(page.getByTestId("feature-row")).toBeVisible();
  });

  test("queue rows open and close from the keyboard", async ({ page }) => {
    await page.goto("/queue");
    const button = page.getByRole("button", { name: "pay_86bqtrjlsj9hg0" });
    await button.focus();
    await page.keyboard.press("Enter");
    await expect(page.getByTestId("queue-detail")).toBeVisible();
    await expect(button).toHaveAttribute("aria-expanded", "true");
    await page.keyboard.press("Space");
    await expect(page.getByTestId("queue-detail")).toBeHidden();
  });
});

test.describe("no third-party requests", () => {
  for (const screen of SCREENS) {
    test(`${screen.name} loads everything from its own origin`, async ({ page }) => {
      const foreign: string[] = [];
      page.on("request", (request) => {
        const url = new URL(request.url());
        if (!["127.0.0.1", "localhost"].includes(url.hostname) && url.protocol !== "data:") {
          foreign.push(request.url());
        }
      });
      await page.goto(screen.path);
      await screen.ready(page);
      expect(foreign).toEqual([]);
    });
  }
});
