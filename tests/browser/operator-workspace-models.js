async (page) => {
  const assert = (v, m) => {
    if (!v) throw new Error(m);
  };
  const fill = (name, value) =>
    page.getByRole("textbox", { name, exact: true }).fill(value);
  await page.getByRole("link", { name: "模型设置", exact: true }).click();
  await page.getByRole("combobox", { name: "服务商预设" }).selectOption("glm");
  assert(
    (await page
      .getByRole("textbox", { name: "服务地址", exact: true })
      .inputValue()) === "https://open.bigmodel.cn/api/paas/v4",
    "GLM preset",
  );
  await page
    .getByRole("combobox", { name: "服务商预设" })
    .selectOption("longcat");
  assert(
    (await page
      .getByRole("textbox", { name: "服务地址", exact: true })
      .inputValue()) === "https://api.longcat.chat/openai/v1",
    "LongCat preset",
  );
  await page
    .getByRole("combobox", { name: "服务商预设" })
    .selectOption("custom");
  await fill("配置名称", "模拟模型 · 正常");
  await fill("服务地址", "http://127.0.0.1:9552/good");
  await fill("模型名称", "fixture-model");
  await fill("访问密钥", "sapper-browser-synthetic-key-only");
  if (!(await page.getByText("高级调用设置", { exact: true }).evaluate(e => e.parentElement.open))) await page.getByText("高级调用设置", { exact: true }).click();
  await page.getByRole("spinbutton", { name: "调用时限（秒）" }).fill("5");
  await page.getByRole("button", { name: "保存模型配置", exact: true }).click();
  await page
    .getByText("已保存密钥；留空可复用同地址密钥", { exact: true })
    .waitFor();
  assert(
    (await page.getByRole("textbox", { name: "访问密钥" }).inputValue()) === "",
    "password cleared after save",
  );
  await page.getByRole("button", { name: "测试已保存连接" }).click();
  await page.getByRole("status").filter({ hasText: "连接成功" }).waitFor();
  await page.getByRole("button", { name: "新增模型配置", exact: true }).click();
  await page
    .getByRole("combobox", { name: "服务商预设" })
    .selectOption("custom");
  await fill("配置名称", "模拟模型 · 失败");
  await fill("服务地址", "http://127.0.0.1:9552/bad");
  await fill("模型名称", "fixture-model");
  await fill("访问密钥", "sapper-browser-synthetic-key-only");
  if (!(await page.getByText("高级调用设置", { exact: true }).evaluate(e => e.parentElement.open))) await page.getByText("高级调用设置", { exact: true }).click();
  await page.getByRole("spinbutton", { name: "调用时限（秒）" }).fill("5");
  await page.getByRole("button", { name: "保存模型配置", exact: true }).click();
  await page
    .getByText("已保存密钥；留空可复用同地址密钥", { exact: true })
    .waitFor();
  await page.getByRole("button", { name: "测试已保存连接" }).click();
  await page
    .getByRole("status")
    .filter({ hasText: /失败|不可用/ })
    .waitFor();
  assert(
    !(await page.locator("body").textContent()).includes(
      "sapper-browser-synthetic-key-only",
    ),
    "key not rendered",
  );
  await page
    .getByRole("button", {
      name: "模拟模型 · 正常 · 自定义兼容服务",
      exact: true,
    })
    .click();
  assert(
    (await page.getByRole("textbox", { name: "访问密钥" }).inputValue()) === "",
    "switch clears key",
  );
  await page.reload();
  await page
    .getByRole("button", {
      name: "模拟模型 · 正常 · 自定义兼容服务",
      exact: true,
    })
    .click();
  assert(
    (await page.getByRole("textbox", { name: "访问密钥" }).inputValue()) === "",
    "reload/edit blank password",
  );
  assert(
    (await page.evaluate(
      () =>
        Object.keys(localStorage).length + Object.keys(sessionStorage).length,
    )) === 0,
    "no browser storage",
  );
  await page.screenshot({
    path: ".superpowers/operator/ui-validation/model-settings.png",
    fullPage: true,
  });
  return {
    presets: "DeepSeek/GLM/LongCat/custom editable",
    profiles: 2,
    tests: "good success + bad safe failure",
    password: "blank after save/switch/reload",
    storage: "empty",
  };
}
