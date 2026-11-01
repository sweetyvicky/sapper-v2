async (page) => {
  const assert = (v, m) => {
    if (!v) throw new Error(m);
  };
  const text = (n, v) =>
    page.getByRole("textbox", { name: n, exact: true }).fill(v);
  await page.getByRole("link", { name: "任务", exact: true }).click();
  await page.getByRole("button", { name: "新建任务", exact: true }).click();
  await text("任务名称", "合成验收 · 完整操作流程");
  await text(
    "测试目标与成功标准",
    "验证批准边界、人工指导、完整漏洞复核与报告。",
  );
  await page.getByText("补充信息：背景与初始指导", { exact: true }).click();
  await text(
    "背景信息",
    "仅 Docker 回环合成端点；<script>globalThis.SAPPER_XSS=1</script>",
  );
  await text("初始指导", "用 Scout 与 Soldier 执行有界观察。");
  await text(
    "批量资产（每行一个网址、域名或 IP）",
    "http://127.0.0.1:9551/alpha\nhttp://127.0.0.1:9551/beta\nhttp://127.0.0.1:9551/alpha\nbad/path",
  );
  await page.getByRole("button", { name: "预览并检查资产" }).click();
  await page.getByText("有效 2 · 重复 1 · 错误 1", { exact: true }).waitFor();
  await page.getByRole("button", { name: "保存草稿", exact: true }).click();
  await page
    .getByRole("status")
    .filter({ hasText: "请先预览资产，并修正所有错误行后保存" })
    .waitFor();
  await text(
    "批量资产（每行一个网址、域名或 IP）",
    "http://127.0.0.1:9551/alpha\nhttp://127.0.0.1:9551/beta\nhttp://127.0.0.1:9551/slow\nhttp://127.0.0.1:9551/failure",
  );
  await page.getByRole("button", { name: "保存草稿", exact: true }).click();
  assert(
    (await page
      .getByRole("heading", { name: "新建任务", exact: true })
      .count()) === 1,
    "dirty preview cannot save",
  );
  // Real UTF-8 CSV file upload, including a literal multiline note.
  await page
    .getByLabel("上传 UTF-8 CSV 文件", { exact: true })
    .setInputFiles({
      name: "assets.csv",
      mimeType: "text/csv",
      buffer: Buffer.from(
        "target,name,group,notes\nhttp://127.0.0.1:9551/alpha,合成暴露端点,验收,仅合成数据\nhttp://127.0.0.1:9551/beta,第二端点,验收,独立观察\nhttp://127.0.0.1:9551/slow,慢请求,验收,受控屏障\nhttp://127.0.0.1:9551/failure,失败端点,验收,有限503\n",
        "utf8",
      ),
    });
  await page.getByRole("button", { name: "预览并检查资产" }).click();
  await page.getByText("有效 4 · 重复 0 · 错误 0", { exact: true }).waitFor();
  await text("排除范围（每行一个完整来源或网段）", "192.0.2.0/24");
  await page.getByRole("combobox", { name: "运行方式" }).selectOption("model");
  await page
    .getByRole("combobox", { name: "默认模型配置" })
    .selectOption({ label: "模拟模型 · 正常 · fixture-model" });
  await page
    .getByText("高级边界：授权时长与单次请求限制", { exact: true })
    .click();
  for (const [name, value] of [
    ["请求次数", "30"],
    ["预留响应字节额度", "1048576"],
    ["执行时间额度（秒）", "600"],
    ["并行上限", "1"],
    ["模型调用次数", "40"],
    ["本轮授权有效期（秒）", "86400"],
    ["单次请求时限（秒）", "30"],
    ["单次响应最大字节", "8192"],
  ])
    await page.getByRole("spinbutton", { name, exact: true }).fill(value);
  await page.screenshot({
    path: ".superpowers/operator/ui-validation/task-form.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "保存草稿", exact: true }).click();
  await page.getByRole("button", { name: "规划新一轮", exact: true }).waitFor();
  await page.getByRole("button", { name: "编辑草稿", exact: true }).click();
  assert(
    (await page
      .getByRole("textbox", { name: "测试目标与成功标准" })
      .inputValue()) === "验证批准边界、人工指导、完整漏洞复核与报告。",
    "goal persisted",
  );
  assert(
    (await page
      .getByRole("spinbutton", { name: "本轮授权有效期（秒）" })
      .inputValue()) === "86400",
    "expiry persisted",
  );
  await page.getByRole("button", { name: "取消", exact: true }).click();
  await page.getByRole("button", { name: "规划新一轮", exact: true }).click();
  await page
    .getByRole("button", { name: "批准选中并开始", exact: true })
    .waitFor();
  await page
    .getByText("等待批准", { exact: true })
    .first()
    .waitFor({ timeout: 90000 });
  assert(
    (await page.getByRole("checkbox").count()) === 4,
    "four exact pending actions",
  );
  assert(
    !(await page.evaluate(() => globalThis.SAPPER_XSS)),
    "draft markup not executed",
  );
  return {
    taskUrl: page.url(),
    import:
      "2 valid/1 duplicate/1 error blocks save; edit invalidates; UTF8 CSV 4 rows",
    draft: "goal/context/exclusions/budgets/model saved and reopened",
    plan: "four pending real Commander proposals",
  };
}
