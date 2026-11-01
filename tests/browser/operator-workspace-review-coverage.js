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
  await page.getByRole("tab", { name: "漏洞", exact: true }).click();
  await page
    .getByRole("button", { name: /Synthetic exposure marker · 低 · 候选/ })
    .click();
  let s = await snapshot(),
    f = s.findings[0];
  assert(
    f.status === "candidate" && s.review_suggestions.length === 1,
    "advice remains unapplied candidate",
  );
  await page
    .getByRole("textbox", {
      name: "复核署名（与原报告者、事实创建者不同）",
      exact: true,
    })
    .fill("人工复核署名甲");
  await page
    .getByRole("combobox", {
      name: "复核证据（同目标、较晚、独立回执）",
      exact: true,
    })
    .selectOption(s.review_suggestions[0].evidence_id);
  await page
    .getByRole("textbox", { name: "复核说明", exact: true })
    .fill("后续独立同目标回执仍有合成标记，人工记录确认。");
  await page.getByRole("button", { name: "保存人工复核", exact: true }).click();
  await page
    .getByRole("button", { name: /Synthetic exposure marker · 低 · 已确认/ })
    .waitFor();
  await page
    .getByRole("button", { name: /Synthetic exposure marker · 低 · 已确认/ })
    .click();
  assert(
    !(await page.evaluate(
      () => globalThis.SAPPER_XSS || window.syntheticInjected,
    )),
    "markup never executed",
  );
  await page.screenshot({
    path: ".superpowers/operator/ui-validation/finding-detail.png",
    fullPage: true,
  });
  await page.getByRole("tab", { name: "资产与覆盖", exact: true }).click();
  const metrics = await page.getByLabel("当前有效覆盖指标").textContent();
  assert(
    metrics.includes("5 / 5") && metrics.includes("5 / 15"),
    "counts and denominators",
  );
  await page
    .getByRole("searchbox", { name: "搜索资产", exact: true })
    .fill("/beta");
  assert(
    (await page.locator("#section-coverage tbody tr").count()) === 3,
    "asset search",
  );
  assert(
    (await page.getByLabel("当前有效覆盖指标").textContent()) === metrics,
    "filter retains global denominator",
  );
  const row = page
    .locator("#section-coverage tbody tr")
    .filter({ hasText: "人工评估" });
  await row.getByRole("button").click();
  await page
    .getByRole("textbox", { name: "评估署名", exact: true })
    .fill("覆盖评估员");
  await page
    .getByRole("textbox", { name: "评估理由", exact: true })
    .fill("合成fixture此项不适用，单独排除");
  await page.getByRole("button", { name: "保存评估", exact: true }).click();
  await page
    .getByRole("combobox", { name: "检查状态", exact: true })
    .selectOption("not_applicable");
  await page.getByRole("searchbox", { name: "搜索资产", exact: true }).fill("");
  await page.getByRole("button", { name: "不适用", exact: true }).waitFor();
  await page.screenshot({
    path: ".superpowers/operator/ui-validation/coverage.png",
    fullPage: true,
  });
  return {
    review: "later independent receipt manually confirmed; history visible",
    markup: "literal safe text",
    coverage:
      "5/5 assets,5/15 checks, filtered global denominator; beta manual N/A saved with actor/reason",
  };
}
