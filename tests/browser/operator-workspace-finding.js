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
  await page
    .getByText("本批计划完成", { exact: true })
    .first()
    .waitFor({ timeout: 90000 });
  await page.getByRole("tab", { name: "漏洞", exact: true }).click();
  let s = await snapshot();
  const finding = s.findings[0];
  assert(finding, "real model candidate exists");
  await page.getByRole("button", { name: "编辑完整叙述", exact: true }).click();
  for (const [name, value] of [
    [
      "漏洞描述",
      "合成叙述：响应中存在训练暴露标记。<script>globalThis.SAPPER_XSS=2</script>",
    ],
    ["影响", "仅用于合成验收；验证完整影响说明。"],
    ["复现步骤", "1. 批准精确 GET。\n2. 检查真实回执与内容摘录。"],
    ["修复建议", "移除训练标记并使用新的独立回执复核。"],
    ["操作备注（可选）", "恶意标签应显示为文字 <img src=x onerror=alert(1)>"],
  ])
    await page.getByRole("textbox", { name, exact: true }).fill(value);
  await page.getByRole("button", { name: "保存叙述", exact: true }).click();
  await page
    .getByText("仅用于合成验收；验证完整影响说明。", { exact: true })
    .waitFor();
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
    .selectOption(finding.evidence[0].id);
  await page
    .getByRole("textbox", { name: "复核说明", exact: true })
    .fill("尝试同证据，应明确拒绝");
  await page.getByRole("button", { name: "保存人工复核", exact: true }).click();
  await page
    .locator("section")
    .filter({
      has: page.getByRole("heading", { name: "人工复核", exact: true }),
    })
    .getByRole("status")
    .filter({ hasText: /无效|不允许/ })
    .waitFor();
  await page
    .getByRole("button", { name: "请求复测并规划", exact: true })
    .click();
  await page.getByRole("tab", { name: "概览", exact: true }).click();
  await page
    .locator(".action-row")
    .filter({ hasText: "General" })
    .getByRole("checkbox")
    .waitFor();
  const general = page
    .locator(".action-row")
    .filter({ hasText: "General" })
    .getByRole("checkbox");
  await general.check();
  return {
    sameEvidence: "rejected visibly",
    narrative: "full prose edited and saved; malicious markup literal",
    findingId: finding.id,
    runId,
    retest: "General exact target pending; not yet approved",
  };
}
