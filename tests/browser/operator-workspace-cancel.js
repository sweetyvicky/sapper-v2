async (page) => {
  await page
    .getByRole("button", { name: "开始已批准动作", exact: true })
    .click();
  await page.getByRole("button", { name: "结束本轮", exact: true }).click();
  await page.getByText("正在等待本次操作结束后结束", { exact: true }).waitFor();
  return "cancel_requested while bounded request outstanding";
}
