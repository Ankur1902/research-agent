import { test, expect } from "@playwright/test";
test("register, project, approved demo research, evidence, export and logout", async ({
  page,
}) => {
  await page.goto("/register");
  await page.getByLabel("Your name").fill("Portfolio Analyst");
  await page.getByLabel("Organization").fill("Browser Test Organization");
  await page
    .getByLabel("Email address")
    .fill(`analyst-${Date.now()}@example.com`);
  await page
    .getByLabel("Password", { exact: true })
    .fill("portfolio-password-123");
  await page.getByRole("button", { name: "Create workspace" }).click();
  await expect(page).toHaveURL(/dashboard/);
  await expect(
    page.getByRole("heading", { name: "A clearer view of what matters." }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Projects", exact: true }).click();
  await page.getByRole("button", { name: "New project" }).click();
  await page
    .getByLabel("Name", { exact: true })
    .fill("India EV Market Intelligence");
  await page.getByLabel("Description").fill("Browser-tested project");
  await page
    .getByRole("button", { name: "Create project", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "India EV Market Intelligence" }),
  ).toBeVisible();
  await page.goto("/research/new");
  await page
    .getByLabel("Research question", { exact: true })
    .fill("Demonstrate the evidence-backed research workflow");
  await page
    .getByRole("combobox", { name: "Project", exact: true })
    .selectOption({ label: "India EV Market Intelligence" });
  await page.getByRole("combobox", { name: "Execution mode" }).selectOption("DEMO");
  await page.getByRole("button", { name: "Generate research plan" }).click();
  await expect(
    page.getByRole("button", { name: "Approve & research" }),
  ).toBeVisible({ timeout: 30000 });
  await page.getByRole("button", { name: "Approve & research" }).click();
  await expect(
    page.getByRole("button", { name: "Approve report" }),
  ).toBeVisible({ timeout: 30000 });
  await page.getByRole("button", { name: "[S1]", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText(
    "ResearchOS demo fixture",
  );
  await page.getByRole("button", { name: "Close evidence" }).click();
  await page.getByRole("button", { name: "Approve report" }).click();
  await expect(
    page.getByText("APPROVED REPORT", { exact: true }),
  ).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "PDF", exact: true }).click();
  expect((await download).suggestedFilename()).toMatch(/\.pdf$/);
  await page.getByRole("link", { name: "Agent activity" }).click();
  await expect(page.getByText("SAFE OPERATIONAL TRACE")).toBeVisible();
  await page.goto("/documents");
  await page
    .getByLabel("Choose document")
    .setInputFiles({
      name: "evidence.txt",
      mimeType: "text/plain",
      buffer: Buffer.from(
        "Browser test fixture: evidence is stored with provenance.\n".repeat(1600),
      ),
    });
  await expect(page.getByText("evidence.txt")).toBeVisible();
  await page.goto("/evaluations");
  await page
    .getByRole("button", { name: "Run evaluation", exact: true })
    .click();
  await page.getByLabel("Run name").fill("Browser provenance check");
  await page.getByRole("combobox", { name: "Research report" }).selectOption({ index: 1 });
  await page
    .getByRole("button", { name: "Run evaluation", exact: true })
    .last()
    .click();
  await expect(page.getByText("Browser provenance check")).toBeVisible();
  await page.goto("/settings/models");
  await expect(
    page.getByRole("heading", { name: "Provider configuration" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/login/);
});
