async (page) => {
  const assert = (v, m) => {
    if (!v) throw Error(m);
  };
  const draftId = page.url().split("/").pop();
  await page.getByRole("button", { name: "规划新一轮", exact: true }).click();
  await page
    .getByRole("button", { name: "批准选中并开始", exact: true })
    .waitFor();
  await page.locator(".action-row input[type=checkbox]").check();
  await page
    .getByRole("button", { name: "批准选中并开始", exact: true })
    .click();
  await page
    .getByText("本批计划完成", { exact: true })
    .first()
    .waitFor({ timeout: 15000 });
  const runId = page.url().split("/").pop();
  await page.getByRole("tab", { name: "测试过程", exact: true }).click();
  await page
    .getByRole("textbox", { name: "给本轮的人工指导", exact: true })
    .fill("Final correction record-only guidance");
  await page
    .getByRole("button", { name: "发送并重新规划", exact: true })
    .click();
  await page
    .getByRole("status")
    .filter({ hasText: "Recorded only; no Commander model configured." })
    .waitFor();
  const caseId = await page.evaluate(async (id) => {
    const { request } = await import("/api.js");
    const s = (await request("/api/runs/" + id)).snapshot;
    const f = await request("/api/runs/" + id + "/findings", {
      fact_id: s.runtime.evidence.facts[0].id,
      title: "Final synthetic case",
      severity: "info",
      reporter: "fixture-operator",
      description: "D",
      impact: "I",
      reproduction: "R",
      remediation: "M",
      cwe: "",
      operator_note: "",
    });
    return f.finding.id;
  }, runId);
  await page.getByRole("tab", { name: "漏洞", exact: true }).click();
  await page
    .getByRole("button", { name: "请求复测并规划", exact: true })
    .waitFor({ timeout: 10000 });
  await page
    .getByRole("button", { name: "请求复测并规划", exact: true })
    .click();
  await page
    .getByRole("status")
    .filter({ hasText: "New independent retest action is pending approval." })
    .waitFor();
  await page.getByRole("button", { name: "结束本轮", exact: true }).click();
  await page
    .getByText("本轮已结束，不能继续；可规划新一轮。", { exact: true })
    .waitFor();
  const input = page.getByRole("textbox", { name: "复测指导", exact: true });
  await input.fill("Retain failed retest correction");
  await page
    .getByRole("button", { name: "请求复测并规划", exact: true })
    .click();
  await page.getByRole("status").filter({ hasText: "处理失败" }).waitFor();
  assert(
    (await input.inputValue()) === "Retain failed retest correction",
    "failed retest input retained",
  );
  await page.getByRole("tab", { name: "测试过程", exact: true }).click();
  const composer = page.getByRole("textbox", {
    name: "给本轮的人工指导",
    exact: true,
  });
  await composer.fill("Retain cancelled guidance");
  await page
    .getByRole("button", { name: "发送并重新规划", exact: true })
    .click();
  await page.getByRole("status").filter({ hasText: "处理失败" }).waitFor();
  assert(
    (await composer.inputValue()) === "Retain cancelled guidance",
    "failed composer retained",
  );
  return {
    draftId,
    runId,
    caseId,
    proof:
      "real terminal consumed+failed acknowledgements in composer and finding retest, durable IDs/consumer/results, failed inputs retained",
  };
};
