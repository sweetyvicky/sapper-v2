async (page) => {
  const assert = (v, m) => {
    if (!v) throw new Error(m);
  };
  const runId = page.url().split("/").pop();
  const snapshot = () =>
    page.evaluate(
      async (id) => (await (await fetch("/api/runs/" + id)).json()).snapshot,
      runId,
    );
  let s = await snapshot();
  const original = s.findings[0],
    originalFact = original.fact_id;
  await page.getByRole("tab", { name: "资产与覆盖", exact: true }).click();
  await page
    .getByRole("combobox", { name: "检查状态", exact: true })
    .selectOption("");
  await page
    .getByRole("searchbox", { name: "搜索资产", exact: true })
    .fill("/alpha");
  await page
    .locator("#section-coverage tbody tr")
    .filter({ hasText: "人工评估" })
    .getByRole("button")
    .click();
  await page
    .getByRole("combobox", { name: "评估结果", exact: true })
    .selectOption("completed");
  await page
    .getByRole("textbox", { name: "评估署名", exact: true })
    .fill("覆盖评估员");
  await page
    .getByRole("textbox", { name: "评估理由", exact: true })
    .fill("基于原始回执完成人工合成评估");
  await page
    .getByRole("checkbox", { name: "选择事实 " + originalFact, exact: true })
    .check();
  await page.getByRole("button", { name: "保存评估", exact: true }).click();
  await page
    .getByRole("status")
    .filter({ hasText: "操作成功" })
    .last()
    .waitFor();
  await page.getByRole("tab", { name: "漏洞", exact: true }).click();
  await page
    .getByRole("button", { name: /Synthetic exposure marker · 低 · 已确认/ })
    .click();
  await page.getByText("撤销失效证据", { exact: true }).click();
  await page
    .getByRole("textbox", { name: "撤销署名", exact: true })
    .fill("证据维护员");
  await page
    .getByRole("textbox", { name: "撤销证据理由", exact: true })
    .fill("合成验收主动撤销原始事实，不等于漏洞已修复");
  await page.getByRole("button", { name: "撤销支撑事实", exact: true }).click();
  await page
    .getByRole("button", {
      name: /Synthetic exposure marker · 低 · 证据已失效/,
    })
    .waitFor();
  s = await snapshot();
  assert(
    s.findings[0].status === "stale" &&
      s.findings[0].reviews[0].outcome === "confirmed",
    "stale preserves historical confirmation",
  );
  const later = s.observations.find(
    (o) =>
      o.valid &&
      o.evidence.some((e) => e.target === "http://127.0.0.1:9551/alpha"),
  );
  assert(later, "independent retest still valid");
  await page
    .getByRole("button", { name: "从真实观察创建候选漏洞", exact: true })
    .click();
  await page
    .getByRole("combobox", { name: "选择有效事实", exact: true })
    .selectOption(later.fact_id);
  await page
    .getByRole("textbox", { name: "漏洞标题", exact: true })
    .fill("人工候选 · 独立复测回执");
  await page
    .getByRole("textbox", { name: "报告署名", exact: true })
    .fill("本地报告员");
  for (const n of ["漏洞描述", "影响", "复现步骤", "修复建议"])
    await page
      .getByRole("textbox", { name: n, exact: true })
      .fill("合成候选完整说明：" + n);
  await page.getByRole("button", { name: "保存候选漏洞", exact: true }).click();
  await page
    .getByRole("button", { name: /人工候选 · 独立复测回执 · 中 · 候选/ })
    .waitFor();
  await page
    .getByRole("button", { name: /人工候选 · 独立复测回执 · 中 · 候选/ })
    .click();
  await page.getByText("撤销失效证据", { exact: true }).click();
  await page
    .getByRole("textbox", { name: "撤销署名", exact: true })
    .fill("证据维护员");
  await page
    .getByRole("textbox", { name: "撤销证据理由", exact: true })
    .fill("撤销剩余alpha复测事实，验证覆盖撤回");
  await page.getByRole("button", { name: "撤销支撑事实", exact: true }).click();
  await page
    .getByRole("button", { name: /人工候选 · 独立复测回执 · 中 · 证据已失效/ })
    .waitFor();
  s = await snapshot();
  assert(
    s.coverage.metrics.assets.covered === 4,
    "alpha valid coverage withdrawn",
  );
  assert(
    s.runtime.tasks.filter((t) => t.receipt_state === "verified").length === 6,
    "historical six receipts retained",
  );
  await page.getByRole("tab", { name: "资产与覆盖", exact: true }).click();
  await page.getByRole("searchbox", { name: "搜索资产", exact: true }).fill("");
  await page.screenshot({
    path: ".superpowers/operator/ui-validation/coverage-stale.png",
    fullPage: true,
  });
  return {
    manualAssessment: "completed with valid matching fact",
    creation: "full manual candidate saved from real retest fact",
    invalidation:
      "both alpha facts revoked; 4/5 current coverage, six historical receipts; review stays confirmed historically; findings stale",
  };
}
