async (page) => {
  await page
    .getByRole("button", { name: "开始已批准动作", exact: true })
    .click();
  await page.getByRole("button", { name: "暂停", exact: true }).click();
  await page.getByText("正在等待本次操作结束后暂停", { exact: true }).waitFor();
  await page.screenshot({
    path: ".superpowers/operator/ui-validation/pause-requested.png",
  });
  return { state: "pause_requested; bounded inflight operation outstanding" };
}
