async (page) => {
  const assert = (ok, message) => {
    if (!ok) throw new Error(message);
  };
  const click = (name) =>
    page.getByRole("button", { name, exact: true }).click();
  await page.getByRole("link", { name: "任务", exact: true }).click();
  await click("新建任务");
  await page
    .getByRole("textbox", { name: "任务名称", exact: true })
    .fill("合成修正 · actual expiry " + Date.now());
  await page
    .getByRole("textbox", { name: "测试目标与成功标准", exact: true })
    .fill("Keep open coverage inputs through real 60-second policy expiry.");
  await page
    .getByRole("textbox", {
      name: "批量资产（每行一个网址、域名或 IP）",
      exact: true,
    })
    .fill("http://127.0.0.1:9551/beta");
  await click("预览并检查资产");
  await page.getByText("有效 1 · 重复 0 · 错误 0", { exact: true }).waitFor();
  await page
    .getByRole("checkbox", { name: "允许 HEAD 响应观察", exact: true })
    .uncheck();
  await page
    .getByText("高级边界：授权时长与单次请求限制", { exact: true })
    .click();
  await page
    .getByRole("spinbutton", { name: "本轮授权有效期（秒）", exact: true })
    .fill("60");
  await click("保存并规划新一轮");
  await page
    .locator(".topline .badge")
    .filter({ hasText: "等待批准" })
    .waitFor();
  await page.locator(".action-row input:not(:disabled)").check();
  await click("批准选中并开始");
  await page
    .locator(".topline .badge")
    .filter({ hasText: "本批计划完成" })
    .waitFor({ timeout: 90000 });
  const read = () =>
    page.evaluate(
      async () =>
        (
          await (
            await fetch("/api/runs/" + location.hash.split("/").pop())
          ).json()
        ).snapshot,
    );
  const before = await read(),
    fact = before.observations.find((o) => o.valid).fact_id;
  await page.getByRole("tab", { name: "资产与覆盖", exact: true }).click();
  await page
    .locator("#section-coverage tbody tr")
    .filter({ hasText: "人工评估" })
    .getByRole("button")
    .click();
  await page
    .getByRole("textbox", { name: "评估署名", exact: true })
    .fill("expiry draft actor");
  const reason = page.getByRole("textbox", { name: "评估理由", exact: true });
  await reason.fill("expiry unsaved reason");
  await page
    .getByRole("combobox", { name: "评估结果", exact: true })
    .selectOption("completed");
  await page
    .getByRole("checkbox", { name: "选择事实 " + fact, exact: true })
    .check();
  await reason.focus();
  await reason.evaluate((n) => n.setSelectionRange(2, 8));
  await page.waitForFunction(
    (id) => document.querySelector('input[value="' + id + '"]')?.disabled,
    fact,
    { timeout: 75000 },
  );
  const after = await read(),
    input = await reason.evaluate((n) => ({
      value: n.value,
      start: n.selectionStart,
      end: n.selectionEnd,
      focused: document.activeElement === n,
    }));
  assert(
    input.value === "expiry unsaved reason" &&
      input.start === 2 &&
      input.end === 8 &&
      input.focused,
    "dirty reason and selection survive real expiry",
  );
  assert(
    (await page
      .getByRole("textbox", { name: "评估署名", exact: true })
      .inputValue()) === "expiry draft actor",
    "actor preserved",
  );
  assert(
    (await page.locator("#section-coverage").textContent()).includes(
      "授权已到期",
    ),
    "actual expiry reason refreshed in open detail",
  );
  assert(
    after.observations.find((o) => o.fact_id === fact).valid === false,
    "actual service fact expired",
  );
  assert(
    after.runtime.tasks.filter((t) => t.receipt_state === "verified").length ===
      1,
    "historical receipt retained, no new execution",
  );
  await click("保存评估");
  await page
    .getByText("人工完成评估须明确选择当前有效的匹配事实；失效事实不能使用。", {
      exact: true,
    })
    .waitFor();
  return {
    runId: after.run.id,
    fact,
    expiresAt: after.policy.expires_at,
    input,
    verifiedReceipts: 1,
    check:
      "open cell refreshed at actual policy expiry without losing dirty assessment",
  };
}
