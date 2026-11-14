import { type Locator, type Page, expect } from "@playwright/test";

/** Move a range input the way a drag would: set the value, then fire `input`. */
export async function setRange(slider: Locator, value: number) {
  await slider.evaluate((element, next) => {
    const input = element as HTMLInputElement;
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
    setter.call(input, String(next));
    input.dispatchEvent(new Event("input", { bubbles: true }));
  }, value);
}

/** The value of a plain metric, found by its label. */
export function metric(scope: Locator | Page, label: string): Locator {
  return scope.locator("div.label", { hasText: label }).locator("xpath=following-sibling::div[1]");
}

/** The sub-line under a plain metric. */
export function metricSub(scope: Locator | Page, label: string): Locator {
  return scope.locator("div.label", { hasText: label }).locator("xpath=following-sibling::div[2]");
}

export async function scoreDefaultForm(page: Page) {
  await page.goto("/score");
  await page.getByRole("button", { name: "Score transaction" }).click();
  await expect(page.getByTestId("decision-panel")).toBeVisible();
}

/** Cell texts of one table row. */
export async function cells(row: Locator): Promise<string[]> {
  return (await row.locator("td").allTextContents()).map((text) => text.trim());
}
