async (page) => {
  await page
    .getByRole("button", { name: "开始已批准动作", exact: true })
    .click();
  await page.getByRole("button", { name: "暂停", exact: true }).click();
  await page
    .locator(".topline .badge")
    .filter({ hasText: "正在等待本次操作结束后暂停" })
    .waitFor();
  return {
    url: page.url(),
    phase: "pause_requested; release owned slow barrier next",
  };
}
