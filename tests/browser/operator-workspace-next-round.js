async (page) => {
  await page.getByRole("button", { name: "规划新一轮", exact: true }).click();
  await page
    .getByText("等待批准", { exact: true })
    .first()
    .waitFor({ timeout: 90000 });
  const slowId = await page
    .locator(".action-row")
    .filter({ hasText: "http://127.0.0.1:9551/slow" })
    .getByRole("checkbox")
    .inputValue();
  await page.getByRole("tab", { name: "测试过程", exact: true }).click();
  await page
    .getByRole("combobox", { name: "消息类型", exact: true })
    .selectOption("prioritize");
  await page
    .getByRole("textbox", { name: "给本轮的人工指导", exact: true })
    .fill("先慢请求，再后续动作；验证取消阻止未来工作");
  await page
    .getByRole("textbox", { name: "优先动作标识（每行一个）", exact: true })
    .fill(slowId);
  await page.getByRole("button", { name: "发送指令", exact: true }).click();
  await page
    .getByRole("tabpanel", { name: "测试过程" })
    .getByText("已消费", { exact: true })
    .waitFor();
  await page.getByRole("tab", { name: "概览", exact: true }).click();
  for (const cb of await page.getByRole("checkbox").all())
    if (await cb.isEnabled()) await cb.check();
  await page.getByRole("button", { name: "仅批准选中", exact: true }).click();
  await page
    .getByRole("button", { name: "开始已批准动作", exact: true })
    .waitFor();
  return {
    url: page.url(),
    round: "new frozen round, old records retained, new independent budget",
    state: "approved, not started",
  };
}
