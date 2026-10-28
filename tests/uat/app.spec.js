const { test, expect } = require("@playwright/test");
const pendingUsername = `uat_pending_${Date.now()}`;

async function signIn(page, username, password = "Password123!", institution = "jbs") {
  await page.goto("/login/");
  await page.getByLabel("Institution / faculty").fill(institution);
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  const skipTutorial = page.getByRole("button", { name: "Skip tutorial" });
  if (await skipTutorial.isVisible().catch(() => false)) await skipTutorial.click();
  const questionnaireClose = page.getByRole("button", { name: "Close questionnaire" });
  if (await questionnaireClose.isVisible().catch(() => false)) await questionnaireClose.click();
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
  await expect(page.getByRole("heading", { name: "Your modules", level: 1 })).toBeVisible();
  const modules = page.locator('input[name="modules"]');
  await expect(modules).toHaveCount(2);
  for (let index = 0; index < 2; index += 1) await modules.nth(index).setChecked(false, { force: true });
  for (let index = 0; index < 2; index += 1) await modules.nth(index).setChecked(true, { force: true });
  const saveClick = page.getByRole("button", { name: "Save and continue" }).click();
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
  const workspaceOverflow = await page.locator(".chat-workspace").evaluate((element) => ({
    clientWidth: element.clientWidth,
    scrollWidth: element.scrollWidth,
  }));
  expect(workspaceOverflow.scrollWidth).toBeLessThanOrEqual(workspaceOverflow.clientWidth + 1);
  const additionalPanel = page.locator("#additional-material-panel");
  if (await additionalPanel.isVisible()) {
    await expect(additionalPanel).toHaveCSS("border-left-color", "rgb(190, 216, 245)");
  }
});

test("lecturer sees curation controls but cannot use student module settings", async ({ page }) => {
  await signIn(page, "demo_lecturer");
  await expect(page).toHaveURL(/\/dashboard\/$/);
  await expect(page.getByRole("link", { name: "Manage material" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Topic management" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Add course / module" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Module settings" })).toHaveCount(0);

  await page.goto("/accounts/settings/modules/");
  await expect(page).toHaveURL(/\/accounts\/profile\/$/);
  await expect(page.getByText("Module selection is available to student accounts.")).toBeVisible();
});

test("lecturer application remains pending without module controls", async ({ page }) => {
  await page.goto("/institutions/join-lecturer/");
  await expect(page.getByRole("heading", { name: "Apply for lecturer access" })).toBeVisible();
  await expect(page.getByText("No email is sent when you apply.")).toBeVisible();
  await page.getByLabel("Institution / faculty code").fill("jbs");
  await expect(page.locator('input[name="courses"]')).toHaveCount(0);
  await page.getByLabel("Username").fill(pendingUsername);
  await page.getByLabel("First name").fill("Pending");
  await page.getByLabel("Last name").fill("Lecturer");
  await page.getByLabel("Email", { exact: true }).fill(`${pendingUsername}@example.com`);
  await page.getByRole("button", { name: "Submit for activation" }).click();
  await expect(page).toHaveURL(/\/login\/$/);
  await expect(page.getByText(/No email is sent until your institution administrator approves/)).toBeVisible();
});

test("institution admin has overview and user-management access", async ({ page }) => {
  await signIn(page, "uat_admin");
  await expect(page).toHaveURL(/\/dashboard\/$/);
  await page.getByRole("link", { name: "Add course / module" }).click();
  await expect(page).toHaveURL(/\/institutions\/course-management\/#module-form$/);
  await expect(page.getByRole("heading", { name: "Course management" })).toBeVisible();
  await expect(page.getByText("Current login code")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Add module" })).toBeVisible();
  await page.getByRole("navigation").getByRole("link", { name: "User management" }).click();
  await expect(page).toHaveURL(/\/manage\/users\/$/);
  await expect(page.getByText("@demo_student", { exact: true })).toBeVisible();
  await expect(page.getByText("@demo_lecturer", { exact: true })).toBeVisible();
  await page.getByRole("navigation").getByRole("link", { name: "Manage material" }).click();
  await expect(page.locator("th", { hasText: "Uploaded by" })).toBeVisible();
  const pageOverflow = await page.evaluate(() => ({ client: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }));
  expect(pageOverflow.scroll).toBeLessThanOrEqual(pageOverflow.client + 1);
});

test("first login presents a role-specific tutorial that can be replayed", async ({ page }) => {
  await page.goto("/login/");
  await page.getByLabel("Institution / faculty").fill("jbs");
  await page.getByLabel("Username").fill("uat_admin");
  await page.getByLabel("Password").fill("Password123!");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("dialog", { name: "Your dashboard" })).toBeVisible();
  await expect(page.getByText(/Step 1 of 9/)).toBeVisible();
  await page.getByRole("button", { name: "Skip tutorial" }).click();
  await expect(page.getByRole("button", { name: "Replay tutorial" })).toBeVisible();
});
