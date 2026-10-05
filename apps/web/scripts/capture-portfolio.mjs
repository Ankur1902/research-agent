import { chromium } from "playwright";
import fs from "node:fs/promises";
import { fileURLToPath } from "node:url";

const output = new URL("../../../docs/portfolio/", import.meta.url);
await fs.mkdir(output, { recursive: true });
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1050 } });
page.setDefaultTimeout(30000);
const shot = async (name) => {
  await page.evaluate(() => document.fonts.ready);
  await page.mouse.move(0, 0);
  await page.screenshot({ path: fileURLToPath(new URL(name, output)), fullPage: true });
};
try {
  await page.goto("http://localhost:3000/register");
  await page.getByLabel("Your name").fill("Portfolio Analyst");
  await page.getByLabel("Organization").fill("DEMO · Research Studio");
  await page.getByLabel("Email address").fill(`portfolio-${Date.now()}@example.com`);
  await page.getByLabel("Password", { exact: true }).fill("portfolio-demo-password-123");
  await page.getByRole("button", { name: "Create workspace" }).click();
  await page.waitForURL("**/dashboard");
  await page.getByRole("link", { name: "Projects", exact: true }).click();
  await page.getByRole("button", { name: "New project" }).click();
  await page.getByLabel("Name", { exact: true }).fill("Evidence-backed Research Demo");
  await page.getByLabel("Description").fill("A guided demonstration of planning, approval, evidence provenance, and operational traces.");
  await page.getByRole("button", { name: "Create project", exact: true }).click();
  await page.getByRole("heading", { name: "Evidence-backed Research Demo" }).waitFor();
  await page.goto("http://localhost:3000/research/new");
  await page.getByLabel("Research question", { exact: true }).fill("Demonstrate the evidence-backed research workflow");
  await page.getByRole("combobox", { name: "Project", exact: true }).selectOption({ label: "Evidence-backed Research Demo" });
  await page.getByRole("combobox", { name: "Execution mode" }).selectOption("DEMO");
  await shot("02-research-setup.png");
  await page.getByRole("button", { name: "Generate research plan" }).click();
  await page.getByRole("button", { name: "Approve & research" }).waitFor();
  await shot("03-plan-approval.png");
  await page.getByRole("button", { name: "Approve & research" }).click();
  await page.getByRole("button", { name: "Approve report" }).waitFor();
  await page.getByRole("button", { name: "Approve report" }).click();
  await page.getByText("APPROVED REPORT", { exact: true }).waitFor();
  await shot("04-approved-report.png");
  await page.getByRole("button", { name: "[S1]", exact: true }).click();
  await page.getByRole("dialog").waitFor();
  await shot("05-source-evidence.png");
  await page.getByRole("button", { name: "Close evidence" }).click();
  await page.getByRole("link", { name: "Agent activity" }).click();
  await page.getByText("SAFE OPERATIONAL TRACE").waitFor();
  await shot("06-agent-activity.png");
  await page.goto("http://localhost:3000/dashboard");
  await page.getByRole("heading", { name: "A clearer view of what matters." }).waitFor();
  await page.getByText("Demonstrate the evidence-backed research workflow", { exact: true }).first().waitFor();
  await shot("01-dashboard.png");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForFunction(() => document.querySelector(".sidebar").getBoundingClientRect().right <= 0);
  await shot("07-mobile-dashboard.png");
  console.log("Saved seven portfolio screenshots in docs/portfolio.");
} finally {
  await browser.close();
}
