async (page) => {
  const assert = (v, m) => {
    if (!v) throw new Error(m);
  };
  await page.getByRole("link", { name: "任务", exact: true }).click();
  await page.getByRole("button", { name: "新建任务", exact: true }).click();
  await page
    .getByRole("textbox", { name: "任务名称", exact: true })
    .fill("合成验收 · 慢请求控制");
  await page
    .getByRole("textbox", { name: "测试目标与成功标准", exact: true })
    .fill("分别验证暂停、继续、结束与指导，不混淆暂停和消息消费。");
  await page
    .getByRole("textbox", {
      name: "批量资产（每行一个网址、域名或 IP）",
      exact: true,
    })
    .fill("http://127.0.0.1:9551/slow\nhttp://127.0.0.1:9551/beta");
  await page
    .getByRole("button", { name: "预览并检查资产", exact: true })
    .click();
  await page.getByText("有效 2 · 重复 0 · 错误 0", { exact: true }).waitFor();
  await page
    .getByRole("spinbutton", { name: "执行时间额度（秒）", exact: true })
    .fill("600");
  await page
    .getByText("高级边界：授权时长与单次请求限制", { exact: true })
    .click();
  await page
    .getByRole("spinbutton", { name: "本轮授权有效期（秒）", exact: true })
    .fill("86400");
  await page
    .getByRole("spinbutton", { name: "单次请求时限（秒）", exact: true })
    .fill("30");
  await page
    .getByRole("button", { name: "保存并规划新一轮", exact: true })
    .click();
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
    .fill("先执行受控慢请求，便于人工暂停");
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
    mode: "explicit basic no model",
    priority: "typed command consumed by real scheduler",
    state: "both approved, zero execution until explicit start",
  };
}
