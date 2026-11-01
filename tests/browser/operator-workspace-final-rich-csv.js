async (page) => {
  const assert = (v, m) => {
    if (!v) throw Error(m);
  };
  await page.getByRole("link", { name: "任务", exact: true }).click();
  await page.getByRole("button", { name: "新建任务", exact: true }).click();
  await page
    .getByRole("textbox", { name: "任务名称", exact: true })
    .fill("Final correction · rich CSV");
  await page
    .getByRole("textbox", { name: "测试目标与成功标准", exact: true })
    .fill("Owned synthetic correction proof");
  await page.getByRole("combobox", { name: "导入格式" }).selectOption("csv");
  await page
    .getByRole("textbox", {
      name: "批量资产（每行一个网址、域名或 IP）",
      exact: true,
    })
    .fill(
      'target,name,group,notes\nhttp://127.0.0.1:9551/alpha,Payroll,Finance,"财务, ""notes"""',
    );
  await page
    .getByRole("button", { name: "预览并检查资产", exact: true })
    .click();
  await page.getByText("有效 1 · 重复 0 · 错误 0", { exact: true }).waitFor();
  await page.getByRole("button", { name: "保存草稿", exact: true }).click();
  await page.getByRole("button", { name: "编辑草稿", exact: true }).waitFor();
  const draftId = page.url().split("/").pop();
  await page.getByRole("button", { name: "编辑草稿", exact: true }).click();
  await page
    .getByRole("button", { name: "预览并检查资产", exact: true })
    .click();
  await page.getByText("有效 1 · 重复 0 · 错误 0", { exact: true }).waitFor();
  await page.getByRole("button", { name: "保存草稿", exact: true }).click();
  await page.getByRole("button", { name: "编辑草稿", exact: true }).waitFor();
  const asset = await page.evaluate(
    async (id) =>
      (await (await fetch("/api/tasks/" + id)).json()).task.data.assets[0],
    draftId,
  );
  assert(
    asset.name === "Payroll" &&
      asset.group === "Finance" &&
      asset.notes === '财务, "notes"',
    "CSV retained after UI reopen preview save",
  );
  return {
    draftId,
    proof: "real UI rich CSV save/reopen/repreview/save preserves metadata",
  };
};
