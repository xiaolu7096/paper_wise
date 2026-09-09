import { expect, test } from "@playwright/test";
import { join } from "node:path";

async function saveScreenshot(page: import("@playwright/test").Page, name: string) {
  const directory = process.env.PAPERWISE_UI_SCREENSHOT_DIR;
  if (directory) await page.screenshot({ path: join(directory, name), fullPage: true });
}

const authRequiredBody = {
  error: { code: "AUTH_REQUIRED", message: "Authentication is required", details: null },
};

async function mockVisitor(page: import("@playwright/test").Page) {
  await page.route("**/api/auth/me", (route) => route.fulfill({
    status: 401,
    contentType: "application/json",
    body: JSON.stringify(authRequiredBody),
  }));
}

async function mockLogin(page: import("@playwright/test").Page) {
  await page.route("**/api/auth/login", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      user_id: "11111111-1111-4111-8111-111111111111",
      username: "admin",
      role: "admin",
      created_at: "2026-07-15T00:00:00Z",
    }),
  }));
  await page.route("**/api/papers", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ items: [] }),
  }));
  await page.route("**/api/settings/status", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      text_model: { configured: false, base_url: null, model: null, source: null },
      vision_model: { configured: false, base_url: null, model: null, source: null },
    }),
  }));
}

test("shows a useful visitor workspace without protected data requests", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await mockVisitor(page);
  const protectedRequests: string[] = [];
  page.on("request", (request) => {
    const pathname = new URL(request.url()).pathname;
    if (pathname.startsWith("/api/") && !pathname.startsWith("/api/auth/")) {
      protectedRequests.push(pathname);
    }
  });

  await page.goto("/");

  await expect(page.getByRole("dialog", { name: "登录 PaperWise" })).toBeVisible();
  await expect(page.getByLabel("PDF 阅读器")).toContainText("登录后上传并阅读论文");
  await expect(page.getByLabel("全局导航")).toBeVisible();
  await expect(page.getByRole("link", { name: "使用指南" })).toHaveAttribute("href", "/tutorial.html");
  expect(protectedRequests).toEqual([]);
  await saveScreenshot(page, "paperwise-auth-visitor-desktop.png");

  await page.getByRole("button", { name: "关闭登录" }).click();
  await expect(page.getByRole("dialog", { name: "登录 PaperWise" })).toHaveCount(0);
  await page.getByRole("button", { name: "上传 PDF" }).click();
  await expect(page.getByRole("dialog", { name: "登录 PaperWise" })).toBeVisible();
  expect(protectedRequests).toEqual([]);

  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  await expect(page.getByRole("dialog", { name: "登录 PaperWise" })).toBeVisible();
  await saveScreenshot(page, "paperwise-auth-visitor-mobile.png");
});

test("resumes the visitor upload with one file chooser after login", async ({ page }) => {
  await mockVisitor(page);
  await mockLogin(page);
  await page.goto("/");
  await page.getByRole("button", { name: "关闭登录" }).click();
  await page.getByRole("button", { name: "上传 PDF" }).click();
  await page.getByLabel("用户名").fill("admin");
  await page.getByLabel("密码").fill("password123");

  const fileChooser = page.waitForEvent("filechooser");
  await page.getByRole("button", { name: "登录进入" }).click();
  await fileChooser;

  await expect(page.getByRole("dialog", { name: "登录 PaperWise" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "退出登录" })).toBeVisible();
});

test("returns an expired session to a clean visitor workspace", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("button", { name: "退出登录" })).toBeVisible();
  await page.route("**/api/settings/status", (route) => route.fulfill({
    status: 401,
    contentType: "application/json",
    body: JSON.stringify(authRequiredBody),
  }));

  await page.getByRole("button", { name: "API 配置" }).click();

  await expect(page.getByRole("dialog", { name: "登录 PaperWise" })).toContainText("登录已失效，请重新登录");
  await expect(page.getByLabel("PDF 阅读器")).toContainText("登录后上传并阅读论文");
  await expect(page.locator(".topbar-actions").getByRole("button", { name: "登录" })).toBeVisible();
});

test("desktop navigation hides from the edge and releases reader space", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");

  const navigation = page.getByLabel("全局导航");
  const reader = page.getByLabel("PDF 阅读器");
  const toggle = page.getByRole("button", { name: "隐藏左侧导航" });
  await expect(navigation).toBeVisible();
  await expect(toggle).toBeVisible();

  const navigationBox = await navigation.boundingBox();
  const readerBefore = await reader.boundingBox();
  expect(navigationBox?.width).toBeCloseTo(248, 0);
  expect(navigationBox?.x).toBe(0);

  await saveScreenshot(page, "paperwise-ui-desktop-open.png");
  await toggle.click();
  await expect(page.getByRole("button", { name: "展开左侧导航" })).toBeVisible();
  await page.waitForTimeout(220);

  const readerAfter = await reader.boundingBox();
  expect(readerAfter!.width - readerBefore!.width).toBeCloseTo(248, 0);
  expect(await navigation.getAttribute("aria-hidden")).toBe("true");
  await saveScreenshot(page, "paperwise-ui-desktop-hidden.png");
});

test("narrow layout starts with an accessible hidden navigation", async ({ page }) => {
  await page.setViewportSize({ width: 760, height: 900 });
  await page.goto("/");

  const navigation = page.getByLabel("全局导航");
  const toggle = page.getByRole("button", { name: "展开左侧导航" });
  await expect(toggle).toBeVisible();
  expect(await navigation.getAttribute("aria-hidden")).toBe("true");

  await toggle.click();
  await expect(page.getByRole("button", { name: "隐藏左侧导航" })).toBeVisible();
  await expect(navigation).toBeVisible();
  await page.waitForTimeout(220);
  expect((await navigation.boundingBox())?.width).toBeCloseTo(248, 0);
  await saveScreenshot(page, "paperwise-ui-narrow-open.png");
});

test("uses the blue-pink Morandi palette and respects reduced motion", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");

  const tokens = await page.evaluate(() => {
    const styles = getComputedStyle(document.documentElement);
    return {
      primary: styles.getPropertyValue("--color-primary").trim(),
      sky: styles.getPropertyValue("--color-sky").trim(),
      warm: styles.getPropertyValue("--color-warm-soft").trim(),
      accent: styles.getPropertyValue("--color-accent").trim(),
    };
  });
  expect(tokens).toEqual({
    primary: "#214288",
    sky: "#aad3f6",
    warm: "#f0cbc5",
    accent: "#b8778d",
  });

  const library = page.getByRole("button", { name: "论文库" });
  await expect(library).toHaveCSS("color", "rgb(33, 66, 136)");
  await expect(library).toHaveCSS("background-color", "rgb(228, 240, 251)");

  await page.getByRole("button", { name: "API 配置" }).click();
  await expect(page.getByRole("dialog", { name: "模型设置" })).toBeVisible();
  await saveScreenshot(page, "paperwise-ui-settings.png");
  await page.getByRole("button", { name: "关闭设置" }).click();
  await page.getByRole("button", { name: "账号" }).click();
  await expect(page.locator(".account-view h1")).toBeVisible();
  await saveScreenshot(page, "paperwise-ui-account.png");

  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(library).toHaveCSS("transition-duration", "0s");
  await expect(page.locator(".workspace")).toHaveCSS("transition-duration", "0s");
});

test("keeps the target viewport matrix free of horizontal overflow", async ({ page }) => {
  const viewports = [
    { width: 1920, height: 1080, name: "wide" },
    { width: 1280, height: 720, name: "compact" },
    { width: 390, height: 844, name: "mobile-minimum" },
  ];

  for (const viewport of viewports) {
    await page.setViewportSize(viewport);
    await page.goto("/");
    const hasHorizontalOverflow = await page.evaluate(() =>
      document.documentElement.scrollWidth > document.documentElement.clientWidth,
    );
    expect(hasHorizontalOverflow).toBe(false);
    await saveScreenshot(page, `paperwise-ui-${viewport.name}.png`);
  }
});

test("keeps the app fixed while the assistant scrolls independently", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");

  const assistant = page.getByLabel("AI 阅读助手");
  await assistant.evaluate((element) => {
    const fixture = document.createElement("div");
    fixture.dataset.testid = "long-assistant-content";
    fixture.style.height = "1800px";
    element.append(fixture);
  });

  const dimensions = await page.evaluate(() => {
    const panel = document.querySelector<HTMLElement>(".assistant-panel")!;
    return {
      viewportHeight: window.innerHeight,
      documentHeight: document.documentElement.scrollHeight,
      bodyHeight: document.body.scrollHeight,
      panelClientHeight: panel.clientHeight,
      panelScrollHeight: panel.scrollHeight,
      bodyOverflow: getComputedStyle(document.body).overflow,
    };
  });

  expect(dimensions.documentHeight).toBe(dimensions.viewportHeight);
  expect(dimensions.bodyHeight).toBe(dimensions.viewportHeight);
  expect(dimensions.bodyOverflow).toBe("hidden");
  expect(dimensions.panelScrollHeight).toBeGreaterThan(dimensions.panelClientHeight);

  await assistant.evaluate((element) => { element.scrollTop = 300; });
  expect(await assistant.evaluate((element) => element.scrollTop)).toBeGreaterThan(0);
  expect(await page.evaluate(() => window.scrollY)).toBe(0);
});

test("opens the standalone usage guide and returns to the reader", async ({ page }) => {
  await page.goto("/");

  const guideLink = page.getByRole("link", { name: "使用指南" });
  await expect(guideLink).toHaveAttribute("href", "/tutorial.html");
  await guideLink.click();

  await expect(page).toHaveURL(/\/tutorial\.html$/);
  await expect(page.getByRole("heading", { name: "从上传论文到整理笔记" })).toBeVisible();
  await expect(page.locator(".brand img")).toHaveAttribute("src", "./tutorial-assets/paperwise-brand.png");

  const backLink = page.getByRole("link", { name: "返回 PaperWise 阅读器" });
  await expect(backLink).toHaveAttribute("href", "/");
  await backLink.click();

  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("link", { name: "使用指南" })).toBeVisible();
});
