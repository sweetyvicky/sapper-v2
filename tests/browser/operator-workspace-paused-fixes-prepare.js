async (page) => {
  const partial = await page.evaluate(
    () => globalThis.__operatorReviewPartialFailure === true,
  );
  const click = (name) =>
    page.getByRole("button", { name, exact: true }).click();
  await page.getByRole("link", { name: "任务", exact: true }).click();
  await click("新建任务");
  await page
    .getByRole("textbox", { name: "任务名称", exact: true })
    .fill(
      "合成修正 · paused combined " +
        (partial ? "budget failure " : "success ") +
        Date.now(),
    );
  await page
    .getByRole("textbox", { name: "测试目标与成功标准", exact: true })
    .fill(
      "Approve only slow; beta remains pending while paused; explicit combined resumes.",
    );
  await page
    .getByRole("textbox", {
      name: "批量资产（每行一个网址、域名或 IP）",
      exact: true,
    })
    .fill("http://127.0.0.1:9551/slow\nhttp://127.0.0.1:9551/beta");
  await click("预览并检查资产");
  await page.getByText("有效 2 · 重复 0 · 错误 0", { exact: true }).waitFor();
  await page
    .getByRole("checkbox", { name: "允许 HEAD 响应观察", exact: true })
    .uncheck();
  await page
    .getByRole("spinbutton", { name: "请求次数", exact: true })
    .fill(partial ? "1" : "30");
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
  await click("保存并规划新一轮");
  await page
    .locator(".topline .badge")
    .filter({ hasText: "等待批准" })
    .waitFor();
  const slow = page
      .locator(".action-row")
      .filter({ hasText: "http://127.0.0.1:9551/slow" })
      .getByRole("checkbox"),
    id = await slow.inputValue();
  await page.getByRole("tab", { name: "测试过程", exact: true }).click();
  await page
    .getByRole("combobox", { name: "消息类型", exact: true })
    .selectOption("prioritize");
  await page
    .getByRole("textbox", { name: "给本轮的人工指导", exact: true })
    .fill("合成修正：先执行慢请求，beta 留待暂停后明确批准");
  await page
    .getByRole("textbox", { name: "优先动作标识（每行一个）", exact: true })
    .fill(id);
  await click("发送指令");
  await page
    .getByRole("tabpanel", { name: "测试过程" })
    .getByText("已消费", { exact: true })
    .waitFor();
  await page.getByRole("tab", { name: "概览", exact: true }).click();
  await slow.check();
  await click("仅批准选中");
  await page
    .getByRole("button", { name: "开始已批准动作", exact: true })
    .waitFor();
  const s = await page.evaluate(
    async () =>
      (
        await (
          await fetch("/api/runs/" + location.hash.split("/").pop())
        ).json()
      ).snapshot,
  );
  if (
    s.runtime.tasks.length ||
    s.plan.actions.find((a) => a.target.endsWith("/beta")).state !== "pending"
  )
    throw new Error("No target task or beta approval before explicit start");
  return {
    url: page.url(),
    phase: "prepared slow-only approval",
    partialFailure: partial,
    requests: s.budget.limits.requests,
  };
}
