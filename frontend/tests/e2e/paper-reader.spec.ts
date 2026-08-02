import { expect, test } from "@playwright/test";

const FIRST_PDF = "JVBERi0xLjcKJcK1wrYKJSBXcml0dGVuIGJ5IE11UERGIDEuMjkuMAoKMSAwIG9iago8PC9UeXBlL0NhdGFsb2cvUGFnZXMgMiAwIFIvSW5mbzw8L1Byb2R1Y2VyKE11UERGIDEuMjkuMCk+Pj4+CmVuZG9iagoKMiAwIG9iago8PC9UeXBlL1BhZ2VzL0NvdW50IDEvS2lkc1s0IDAgUl0+PgplbmRvYmoKCjMgMCBvYmoKPDwvRm9udDw8L2hlbHYgNSAwIFI+Pj4+CmVuZG9iagoKNCAwIG9iago8PC9UeXBlL1BhZ2UvTWVkaWFCb3hbMCAwIDU5NSA4NDJdL1JvdGF0ZSAwL1Jlc291cmNlcyAzIDAgUi9QYXJlbnQgMiAwIFIvQ29udGVudHNbNiAwIFJdPj4KZW5kb2JqCgo1IDAgb2JqCjw8L1R5cGUvRm9udC9TdWJ0eXBlL1R5cGUxL0Jhc2VGb250L0hlbHZldGljYS9FbmNvZGluZy9XaW5BbnNpRW5jb2Rpbmc+PgplbmRvYmoKCjYgMCBvYmoKPDwvTGVuZ3RoIDc0Pj4Kc3RyZWFtCgpxCkJUCjEgMCAwIDEgNzIgNzcwIFRtCi9oZWx2IDExIFRmIFs8NTA2MTcwNjU3MjU3Njk3MzY1MjA0NTMyNDU+XVRKCkVUClEKCmVuZHN0cmVhbQplbmRvYmoKCnhyZWYKMCA3CjAwMDAwMDAwMDAgNjU1MzUgZiAKMDAwMDAwMDA0MiAwMDAwMCBuIAowMDAwMDAwMTIwIDAwMDAwIG4gCjAwMDAwMDAxNzIgMDAwMDAgbiAKMDAwMDAwMDIxMyAwMDAwMCBuIAowMDAwMDAwMzIwIDAwMDAwIG4gCjAwMDAwMDA0MDkgMDAwMDAgbiAKCnRyYWlsZXIKPDwvU2l6ZSA3L1Jvb3QgMSAwIFIvSURbPDNCMDkxRkMyODI2REMzOEJDMzhFQzJBRjI3MURDM0JEPjw5MDBBMUQ0NjJGRDJDRUJFRTcyNjRGMjVFMDYyRDA3Rj5dPj4Kc3RhcnR4cmVmCjUzMgolJUVPRgo=";
const SECOND_PDF = "JVBERi0xLjcKJcK1wrYKJSBXcml0dGVuIGJ5IE11UERGIDEuMjkuMAoKMSAwIG9iago8PC9UeXBlL0NhdGFsb2cvUGFnZXMgMiAwIFIvSW5mbzw8L1Byb2R1Y2VyKE11UERGIDEuMjkuMCk+Pj4+CmVuZG9iagoKMiAwIG9iago8PC9UeXBlL1BhZ2VzL0NvdW50IDEvS2lkc1s0IDAgUl0+PgplbmRvYmoKCjMgMCBvYmoKPDwvRm9udDw8L2hlbHYgNSAwIFI+Pj4+CmVuZG9iagoKNCAwIG9iago8PC9UeXBlL1BhZ2UvTWVkaWFCb3hbMCAwIDU5NSA4NDJdL1JvdGF0ZSAwL1Jlc291cmNlcyAzIDAgUi9QYXJlbnQgMiAwIFIvQ29udGVudHNbNiAwIFJdPj4KZW5kb2JqCgo1IDAgb2JqCjw8L1R5cGUvRm9udC9TdWJ0eXBlL1R5cGUxL0Jhc2VGb250L0hlbHZldGljYS9FbmNvZGluZy9XaW5BbnNpRW5jb2Rpbmc+PgplbmRvYmoKCjYgMCBvYmoKPDwvTGVuZ3RoIDgwPj4Kc3RyZWFtCgpxCkJUCjEgMCAwIDEgNzIgNzcwIFRtCi9oZWx2IDExIFRmIFs8NTM2NTYzNmY2ZTY0MjA0NTMyNDUyMDUwNjE3MDY1NzI+XVRKCkVUClEKCmVuZHN0cmVhbQplbmRvYmoKCnhyZWYKMCA3CjAwMDAwMDAwMDAgNjU1MzUgZiAKMDAwMDAwMDA0MiAwMDAwMCBuIAowMDAwMDAxMjAgMDAwMDAgbiAKMDAwMDAwMDE3MiAwMDAwIG4gCjAwMDAwMDIxMyAwMDAwIG4gCjAwMDAwMDMyMCAwMDAwMCBuIAowMDAwMDA0MDkgMDAwMDAgbiAKCnRyYWlsZXIKPDwvU2l6ZSA3L1Jvb3QgMSAwIFIvSURbPDczQzNBMTE3MUEyNTIzNDZDMzg3NUZDM0I1QzNCNUMzPjxDOEUyMTVERUU3MkE0NkQ2MUZGRTQ3QkQ5OEJBNDg5Nz5dPj4Kc3RhcnR4cmVmCjUzOAolJUVPRgo=";

function rotatedCropFixture() {
  const stream = "BT /F1 18 Tf 100 400 Td (Rotated crop text) Tj ET";
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Count 1 /Kids [3 0 R] >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 800] /CropBox [50 100 550 700] /Rotate 90 /UserUnit 2 /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    `<< /Length ${Buffer.byteLength(stream)} >>\nstream\n${stream}\nendstream`,
  ];
  let pdf = "%PDF-1.7\n";
  const offsets = [0];
  for (const [index, object] of objects.entries()) {
    offsets.push(Buffer.byteLength(pdf));
    pdf += `${index + 1} 0 obj\n${object}\nendobj\n`;
  }
  const xref = Buffer.byteLength(pdf);
  pdf += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  pdf += offsets.slice(1).map((offset) => `${String(offset).padStart(10, "0")} 00000 n \n`).join("");
  pdf += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return Buffer.from(pdf);
}

test("uploads, reads, switches, and restores local papers", async ({ page }) => {
  const suffix = Date.now();
  const firstName = `first-${suffix}.pdf`;
  const secondName = `second-${suffix}.pdf`;
  await page.goto("/");

  const input = page.getByLabel("选择 PDF 文件");
  await input.setInputFiles({
    name: firstName,
    mimeType: "application/pdf",
    buffer: Buffer.from(FIRST_PDF, "base64"),
  });
  await expect(page.locator("canvas").first()).toBeVisible();
  await expect(page.getByText("100%", { exact: true })).toBeVisible();
  const firstImage = await page.locator("canvas").first().evaluate((canvas) => canvas.toDataURL());
  expect(firstImage.length).toBeGreaterThan(100);

  await page.getByRole("button", { name: "放大" }).click();
  await expect(page.getByText("125%", { exact: true })).toBeVisible();
  await expect(page.getByLabel("当前页")).toHaveValue("1");

  await input.setInputFiles({
    name: secondName,
    mimeType: "application/pdf",
    buffer: Buffer.from(SECOND_PDF, "base64"),
  });
  await expect(page.locator(".reader-title")).toHaveText(secondName);
  const secondImage = await page.locator("canvas").first().evaluate((canvas) => canvas.toDataURL());
  expect(secondImage).not.toBe(firstImage);

  await page.getByRole("button", { name: `打开 ${firstName}` }).click();
  await expect(page.locator(".reader-title")).toHaveText(firstName);
  await page.getByRole("button", { name: `打开 ${secondName}` }).click();
  await expect(page.locator(".reader-title")).toHaveText(secondName);

  await page.reload();
  await expect(page.getByRole("button", { name: `打开 ${firstName}` })).toBeVisible();
  await expect(page.getByRole("button", { name: `打开 ${secondName}` })).toBeVisible();
  await expect(page.locator("canvas").first()).toBeVisible();

  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: `删除 ${firstName}` }).click();
  await expect(page.getByRole("button", { name: `打开 ${firstName}` })).toHaveCount(0);
  await expect(page.locator(".reader-title")).toHaveText(secondName);

  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: `删除 ${secondName}` }).click();
  await expect(page.getByLabel("PDF 阅读器").getByText("尚未添加论文")).toBeVisible();

  await input.setInputFiles({
    name: firstName,
    mimeType: "application/pdf",
    buffer: Buffer.from(FIRST_PDF, "base64"),
  });
  await expect(page.locator("canvas").first()).toBeVisible();
  await expect(page.locator(".reader-title")).toHaveText(firstName);
});

test("aligns a rotated cropped page with a non-default user unit", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("选择 PDF 文件").setInputFiles({
    name: `geometry-${Date.now()}.pdf`,
    mimeType: "application/pdf",
    buffer: rotatedCropFixture(),
  });

  const paper = page.locator(".pdf-page").first();
  await expect(paper.locator(".textLayer span")).toContainText("Rotated crop text");
  await expect(paper.locator(".textLayer")).toHaveAttribute("data-main-rotation", "90");
  expect(await paper.evaluate((element) => element.style.getPropertyValue("--user-unit"))).toBe("2");

  const sizeDifference = await paper.evaluate((element) => {
    const canvas = element.querySelector("canvas")!.getBoundingClientRect();
    const textLayer = element.querySelector(".textLayer")!.getBoundingClientRect();
    return {
      width: Math.abs(canvas.width - textLayer.width),
      height: Math.abs(canvas.height - textLayer.height),
    };
  });
  expect(sizeDifference.width).toBeLessThanOrEqual(0.05);
  expect(sizeDifference.height).toBeLessThanOrEqual(0.05);
});
