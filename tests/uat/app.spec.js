const { test, expect } = require("@playwright/test");

async function signIn(page, username, password = "Password123!", institution = "jbs") {
  await page.goto("/login/");
  await page.getByLabel("Institution / faculty").fill(institution);
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
}

test("operations health is protected and login validation is generic", async ({ page }) => {
  const health = await page.request.get("/ops/health/", { maxRedirects: 0 });
  expect(health.status()).toBe(302);
  expect(health.headers().location).toContain("/login/?next=/ops/health/");

  await page.goto("/login/");
  await expect(page.getByText("Your institution or faculty administrator provides this code.")).toBeVisible();
  await signIn(page, "demo_student", "Password123!", "wrong-institution");
  await expect(page).toHaveURL(/\/login\/$/);
  await expect(page.getByText("Check your institution code and sign-in details.")).toBeVisible();
});

test("student selects multiple modules and opens a module-scoped chat", async ({ page }) => {
  await signIn(page, "demo_student");
  await expect(page).toHaveURL(/\/dashboard\/$/);

  await page.getByRole("link", { name: "Module settings" }).click();
  await expect(page.getByRole("heading", { name: "Your modules", level: 2 })).toBeVisible();
  const modules = page.locator('input[name="modules"]');
  await expect(modules).toHaveCount(2);
  for (let index = 0; index < 2; index += 1) await modules.nth(index).uncheck();
  for (let index = 0; index < 2; index += 1) await modules.nth(index).check();
  const saveClick = page.getByRole("button", { name: "Save module settings" }).click();
  await expect(page.getByText("Saving your modules…")).toBeVisible();
  await saveClick;
  await expect(page).toHaveURL(/\/dashboard\/$/);
  await expect(page.getByText("Your module settings have been updated.")).toBeVisible();

  await page.getByRole("link", { name: "Chatbot", exact: true }).click();
  await expect(page.getByRole("button", { name: /Choose a module/ })).toBeVisible();
  await page.getByRole("button", { name: /Choose a module/ }).click();
  await page.getByRole("link", { name: "Systems Thinking Foundations" }).click();
  await expect(page.getByRole("button", { name: /Systems Thinking Foundations/ })).toBeVisible();
  await expect(page.getByText("Answers come only from the selected module's indexed library.")).toBeVisible();

  await page.getByPlaceholder(/Ask a question about your module/).fill("What is a balancing feedback loop?");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(page.locator(".conversation-turn--student").last()).toContainText("balancing feedback loop");
  await expect(page.locator(".conversation-turn--bot").last()).toBeVisible({ timeout: 60_000 });
  await expect(page.locator(".conversation-turn--bot .conversation-copy").last()).not.toBeEmpty();
});

test("lecturer sees curation controls but cannot use student module settings", async ({ page }) => {
  await signIn(page, "demo_lecturer");
  await expect(page).toHaveURL(/\/dashboard\/$/);
  await expect(page.getByRole("link", { name: "Manage material" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Module settings" })).toHaveCount(0);

  await page.goto("/accounts/settings/modules/");
  await expect(page).toHaveURL(/\/accounts\/profile\/$/);
  await expect(page.getByText("Module selection is available to student accounts.")).toBeVisible();
});

test("institution admin has overview and user-management access", async ({ page }) => {
  await signIn(page, "uat_admin");
  await expect(page).toHaveURL(/\/dashboard\/$/);
  await expect(page.getByRole("link", { name: "Departments & modules" })).toBeVisible();
  await page.getByRole("link", { name: "User management" }).click();
  await expect(page).toHaveURL(/\/manage\/users\/$/);
  await expect(page.getByText("@demo_student", { exact: true })).toBeVisible();
  await expect(page.getByText("@demo_lecturer", { exact: true })).toBeVisible();
});
