async (page) => {
  const assert = (ok, message) => {
    if (!ok) throw new Error(message);
  };
  const suffix = Date.now();
  const profiles = {};
  const click = (text) =>
    page.getByRole("button", { name: text, exact: true }).click();
  async function model(name) {
    await page.getByRole("link", { name: "模型设置", exact: true }).click();
    await click("新增模型配置");
    await page
      .getByRole("textbox", { name: "配置名称", exact: true })
      .fill(name);
    await page
      .getByRole("combobox", { name: "服务商预设", exact: true })
      .selectOption("custom");
    await page
      .getByRole("textbox", { name: "服务地址", exact: true })
      .fill("http://127.0.0.1:9552/good");
    await page
      .getByRole("textbox", { name: "模型名称", exact: true })
      .fill("fixture-model");
    await page
      .getByRole("textbox", { name: "访问密钥", exact: true })
      .fill("synthetic-review-fixes-only");
    await click("保存模型配置");
    await page.getByText("操作成功", { exact: true }).waitFor();
    const saved = await page.evaluate(
      async () => (await (await fetch("/api/models")).json()).profiles,
    );
    profiles[name] = saved.find((p) => p.name === name).id;
    assert(
      (await page
        .getByRole("textbox", { name: "访问密钥", exact: true })
        .inputValue()) === "",
      "saved key field cleared",
    );
  }
  const survivor = "合成修正 · surviving " + suffix,
    deleted = "合成修正 · deleted " + suffix;
  await model(survivor);
  await model(deleted);
  const drafts = [];
  for (const role of ["default", "Scout"]) {
    await page.getByRole("link", { name: "任务", exact: true }).click();
    await click("新建任务");
    await page
      .getByRole("textbox", { name: "任务名称", exact: true })
      .fill("合成修正缺失配置 " + role + " " + suffix);
    await page
      .getByRole("textbox", { name: "测试目标与成功标准", exact: true })
      .fill(
        "Only repair a deleted explicit profile; never silently change provider.",
      );
    await page
      .getByRole("textbox", {
        name: "批量资产（每行一个网址、域名或 IP）",
        exact: true,
      })
      .fill("http://127.0.0.1:9551/alpha");
    await click("预览并检查资产");
    await page.getByText("有效 1 · 重复 0 · 错误 0", { exact: true }).waitFor();
    await page
      .getByRole("combobox", { name: "运行方式", exact: true })
      .selectOption("model");
    await page
      .getByRole("combobox", { name: "默认模型配置", exact: true })
      .selectOption(profiles[role === "default" ? deleted : survivor]);
    if (role === "Scout") {
      await page.getByText("高级：分别选择角色模型", { exact: true }).click();
      await page
        .getByRole("combobox", { name: "Scout · 观察分析", exact: true })
        .selectOption(profiles[deleted]);
    }
    await click("保存草稿");
    await page.getByRole("button", { name: "编辑草稿", exact: true }).waitFor();
    drafts.push({ role, url: page.url(), id: page.url().split("/").pop() });
  }
  await page.getByRole("link", { name: "模型设置", exact: true }).click();
  await click(deleted + " · 自定义兼容服务");
  await click("删除此配置");
  await page.getByText("操作成功", { exact: true }).waitFor();
  assert(
    await page
      .getByRole("button", { name: "删除此配置", exact: true })
      .isDisabled(),
    "R5 Delete remains disabled after selected profile reset",
  );
  assert(
    await page
      .getByRole("button", { name: "测试已保存连接", exact: true })
      .isDisabled(),
    "R5 Test stays ineligible without profile",
  );
  assert(
    await page
      .getByRole("button", { name: "保存模型配置", exact: true })
      .isEnabled(),
    "R5 Save retains eligibility",
  );
  const results = [];
  for (const draft of drafts) {
    await page.goto(draft.url);
    await click("编辑草稿");
    const choice = page.getByRole("combobox", {
      name: draft.role === "default" ? "默认模型配置" : "Scout · 观察分析",
      exact: true,
    });
    if (draft.role === "Scout")
      await page.getByText("高级：分别选择角色模型", { exact: true }).click();
    assert(
      (await choice.inputValue()) === profiles[deleted],
      "R1 missing ID remains selected",
    );
    assert(
      (await choice.locator("option:checked").getAttribute("disabled")) !==
        null,
      "R1 missing selection visible unavailable",
    );
    const before = await page.evaluate(
      async (id) => (await (await fetch("/api/tasks/" + id)).json()).task,
      draft.id,
    );
    await page
      .getByRole("textbox", { name: "测试目标与成功标准", exact: true })
      .fill("Unrelated edited goal must not clear explicit provider");
    await click("保存草稿");
    await click("保存并规划新一轮");
    const after = await page.evaluate(
      async (id) => (await (await fetch("/api/tasks/" + id)).json()).task,
      draft.id,
    );
    assert(
      before.revision === after.revision,
      "R1 writes blocked until explicit repair",
    );
    assert(
      draft.role === "default"
        ? after.data.model_profile_id === profiles[deleted]
        : after.data.role_profiles.Scout === profiles[deleted],
      "R1 original persisted ID unchanged",
    );
    assert(
      (await page.locator("main").textContent()).includes("配置已不可用"),
      "R1 repair feedback visible",
    );
    if (draft.role === "default")
      await page
        .getByRole("combobox", { name: "运行方式", exact: true })
        .selectOption("basic");
    else await choice.selectOption("");
    await click("保存草稿");
    await page.getByRole("button", { name: "编辑草稿", exact: true }).waitFor();
    const repaired = await page.evaluate(
      async (id) => (await (await fetch("/api/tasks/" + id)).json()).task,
      draft.id,
    );
    assert(
      draft.role === "default"
        ? repaired.data.model_profile_id === null
        : repaired.data.model_profile_id === profiles[survivor] &&
            !repaired.data.role_profiles.Scout,
      "R1 deliberate repair saved, surviving default preserved",
    );
    results.push({
      role: draft.role,
      id: draft.id,
      revision: repaired.revision,
    });
  }
  return {
    checks: "R1 default/role repair and R5 delete eligibility",
    drafts: results,
    deletedProfile: profiles[deleted],
    survivingProfile: profiles[survivor],
  };
}
