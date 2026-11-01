async (page) => {
  const assert = (ok, message) => {
    if (!ok) throw new Error(message);
  };
  const click = (p, text) =>
    p.getByRole("button", { name: text, exact: true }).click();
  const tab = (p, name) => p.getByRole("tab", { name, exact: true }).click();
  const input = (p, name) => p.getByRole("textbox", { name, exact: true });
  const snapshot = (p, id) =>
    p.evaluate(
      async (id) => (await (await fetch("/api/runs/" + id)).json()).snapshot,
      id,
    );
  await page.getByRole("link", { name: "任务", exact: true }).click();
  await click(page, "新建任务");
  await input(page, "任务名称").fill(
    "合成修正 · persistent cases " + Date.now(),
  );
  await input(page, "测试目标与成功标准").fill(
    "Real observed facts, polling preservation and current eligibility.",
  );
  await input(page, "批量资产（每行一个网址、域名或 IP）").fill(
    "http://127.0.0.1:9551/alpha",
  );
  await click(page, "预览并检查资产");
  await page.getByText("有效 1 · 重复 0 · 错误 0", { exact: true }).waitFor();
  await page
    .getByRole("checkbox", { name: "允许 HEAD 响应观察", exact: true })
    .uncheck();
  await page
    .getByText("高级边界：授权时长与单次请求限制", { exact: true })
    .click();
  await page
    .getByRole("spinbutton", { name: "本轮授权有效期（秒）", exact: true })
    .fill("86400");
  await click(page, "保存并规划新一轮");
  await page
    .locator(".topline .badge")
    .filter({ hasText: "等待批准" })
    .waitFor();
  await page.locator(".action-row input:not(:disabled)").check();
  await click(page, "批准选中并开始");
  await page
    .locator(".topline .badge")
    .filter({ hasText: "本批计划完成" })
    .waitFor({ timeout: 90000 });
  const url = page.url(),
    runId = url.split("/").pop();
  let s = await snapshot(page, runId);
  assert(
    s.runtime.tasks.filter((t) => t.receipt_state === "verified").length === 1,
    "one real initial receipt",
  );
  const originalFact = s.observations.find((o) => o.valid).fact_id;
  async function create(p, fact, title) {
    await tab(p, "漏洞");
    await click(p, "从真实观察创建候选漏洞");
    const form = p
      .locator("section.panel")
      .filter({
        has: p.getByRole("heading", { name: "新增候选", exact: true }),
      })
      .last();
    await form
      .getByRole("combobox", { name: "选择有效事实", exact: true })
      .selectOption(fact);
    await form
      .getByRole("textbox", { name: "漏洞标题", exact: true })
      .fill(title);
    await form
      .getByRole("textbox", { name: "报告署名", exact: true })
      .fill("合成报告者");
    for (const name of ["漏洞描述", "影响", "复现步骤", "修复建议"])
      await form
        .getByRole("textbox", { name, exact: true })
        .fill(title + " " + name);
    await form
      .getByRole("button", { name: "保存候选漏洞", exact: true })
      .click();
    await p
      .getByRole("button", { name: new RegExp(title + " · 中 · 候选") })
      .waitFor();
  }
  await create(page, originalFact, "合成修正原始发现");
  await click(page, "请求复测并规划");
  await tab(page, "概览");
  await page.locator(".action-row input:not(:disabled)").waitFor();
  s = await snapshot(page, runId);
  assert(
    s.runtime.tasks.filter((t) => t.receipt_state === "verified").length === 1,
    "no retest before approval",
  );
  await page.locator(".action-row input:not(:disabled)").check();
  await click(page, "批准选中并开始");
  await page
    .locator(".topline .badge")
    .filter({ hasText: "本批计划完成" })
    .waitFor({ timeout: 90000 });
  s = await snapshot(page, runId);
  assert(
    s.runtime.tasks.filter((t) => t.receipt_state === "verified").length === 2,
    "later independent real receipt",
  );
  const independent = s.observations.find(
      (o) => o.valid && o.fact_id !== originalFact,
    ),
    independentEvidence = independent.evidence[0].id;
  const coverage = await page.context().newPage(),
    mutator = await page.context().newPage();
  try {
    await coverage.goto(url);
    await mutator.goto(url);
    await tab(mutator, "漏洞");
    await mutator
      .getByRole("button", { name: /合成修正原始发现 · 中 · 候选/ })
      .waitFor();
    await create(mutator, independent.fact_id, "合成修正独立发现");
    await tab(page, "漏洞");
    await page.getByRole("button", { name: /合成修正原始发现 · 中 ·/ }).click();
    await input(page, "复核署名（与原报告者、事实创建者不同）").fill(
      "合成独立复核者",
    );
    await page
      .getByRole("combobox", {
        name: "复核证据（同目标、较晚、独立回执）",
        exact: true,
      })
      .selectOption(independentEvidence);
    await input(page, "复核说明").fill(
      "Actual independent later receipt review.",
    );
    await click(page, "保存人工复核");
    await page
      .getByRole("button", { name: /合成修正原始发现 · 中 · 已确认/ })
      .waitFor();
    await tab(coverage, "资产与覆盖");
    await coverage
      .locator("#section-coverage tbody tr")
      .filter({ hasText: "人工评估" })
      .getByRole("button")
      .click();
    await input(coverage, "评估署名").fill("合成评估保存者");
    await input(coverage, "评估理由").fill(
      "Fresh saved assessment must appear without reopening.",
    );
    await coverage
      .getByRole("combobox", { name: "评估结果", exact: true })
      .selectOption("completed");
    await coverage
      .getByRole("checkbox", { name: "选择事实 " + originalFact, exact: true })
      .check();
    await click(coverage, "保存评估");
    await coverage
      .getByText("Fresh saved assessment must appear without reopening.", {
        exact: true,
      })
      .waitFor();
    await input(coverage, "评估署名").fill("unsaved coverage actor");
    await input(coverage, "评估理由").fill("unsaved coverage reason");
    await coverage
      .getByRole("checkbox", {
        name: "选择事实 " + independent.fact_id,
        exact: true,
      })
      .check();
    await input(page, "复核说明").fill("unsaved review draft");
    await input(page, "复测指导").fill("unsaved retest draft");
    await page.getByText("撤销失效证据", { exact: true }).click();
    await input(page, "撤销署名").fill("unsaved invalidation actor");
    await input(page, "撤销证据理由").fill("unsaved invalidation reason");
    await click(page, "编辑完整叙述");
    await input(page, "漏洞描述").fill("unsaved narrative text");
    await input(page, "复核说明").focus();
    await input(page, "复核说明").evaluate((n) => n.setSelectionRange(3, 9));
    // Invalidation occurs through another real UI, while this focused case and open
    // coverage form receive actual changed snapshots from the polling service.
    await mutator.getByText("撤销失效证据", { exact: true }).click();
    await input(mutator, "撤销署名").fill("合成证据维护员");
    await input(mutator, "撤销证据理由").fill(
      "Independent receipt intentionally revoked for regression.",
    );
    await click(mutator, "撤销支撑事实");
    await page.waitForFunction(
      (id) =>
        document.querySelector('select option[value="' + id + '"]:disabled') !==
        null,
      independentEvidence,
      { timeout: 15000 },
    );
    await coverage.waitForFunction(
      (id) => document.querySelector('input[value="' + id + '"]')?.disabled,
      independent.fact_id,
      { timeout: 15000 },
    );
    assert(
      (await page
        .getByRole("combobox", {
          name: "复核证据（同目标、较晚、独立回执）",
          exact: true,
        })
        .inputValue()) === independentEvidence,
      "R2 invalid review choice retained, no substitute",
    );
    assert(
      await coverage
        .getByRole("checkbox", {
          name: "选择事实 " + independent.fact_id,
          exact: true,
        })
        .isDisabled(),
      "R4 invalid fact disabled on open cell",
    );
    assert(
      await coverage
        .getByRole("checkbox", {
          name: "选择事实 " + originalFact,
          exact: true,
        })
        .isChecked(),
      "R4 still-valid checked choice retained",
    );
    assert(
      (await coverage.locator("#section-coverage").textContent()).includes(
        "事实已被主动撤销",
      ),
      "R4 current validity explanation shown",
    );
    const focused = await input(page, "复核说明").evaluate((n) => ({
      text: n.value,
      start: n.selectionStart,
      end: n.selectionEnd,
      focused: document.activeElement === n,
    }));
    assert(
      focused.text === "unsaved review draft" &&
        focused.start === 3 &&
        focused.end === 9 &&
        focused.focused,
      "R2 focused dirty text and selection preserved",
    );
    await tab(page, "测试过程");
    // A second changed snapshot arrives while the case is hidden and unfocused.
    await mutator
      .getByRole("button", { name: /合成修正原始发现 · 中 ·/ })
      .click();
    await mutator.getByText("撤销失效证据", { exact: true }).click();
    await input(mutator, "撤销署名").fill("合成证据维护员");
    await input(mutator, "撤销证据理由").fill(
      "Original receipt revoked for current-state refresh.",
    );
    await click(mutator, "撤销支撑事实");
    await coverage
      .getByRole("checkbox", { name: "选择事实 " + originalFact, exact: true })
      .waitFor();
    await coverage.waitForFunction(
      (id) => document.querySelector('input[value="' + id + '"]')?.disabled,
      originalFact,
      { timeout: 15000 },
    );
    await tab(page, "漏洞");
    await page
      .locator("#section-findings .split > div")
      .last()
      .getByText("证据已失效", { exact: true })
      .waitFor();
    for (const [name, value] of [
      ["复核说明", "unsaved review draft"],
      ["复测指导", "unsaved retest draft"],
      ["撤销署名", "unsaved invalidation actor"],
      ["撤销证据理由", "unsaved invalidation reason"],
      ["漏洞描述", "unsaved narrative text"],
    ])
      assert(
        (await input(page, name).inputValue()) === value,
        "R2 hidden-case dirty " + name + " survives polling",
      );
    assert(
      (await input(coverage, "评估署名").inputValue()) ===
        "unsaved coverage actor" &&
        (await input(coverage, "评估理由").inputValue()) ===
          "unsaved coverage reason",
      "R4 assessment dirty inputs survive invalidation",
    );
    assert(
      (await coverage.locator("#section-coverage").textContent()).includes(
        "Fresh saved assessment must appear without reopening.",
      ),
      "R4 saved assessment retained in read-only detail",
    );
    await page.screenshot({
      path: ".superpowers/operator/ui-validation/fix-case-preserved.png",
      fullPage: true,
    });
    await coverage.screenshot({
      path: ".superpowers/operator/ui-validation/fix-coverage-refreshed.png",
      fullPage: true,
    });
    return {
      runId,
      originalFact,
      independentFact: independent.fact_id,
      independentEvidence,
      verifiedReceipts: (await snapshot(page, runId)).runtime.tasks.filter(
        (t) => t.receipt_state === "verified",
      ).length,
      focused,
      checks:
        "R2 focused and hidden dirty forms, fresh stale state, no evidence substitution; R4 saved assessment refresh and validity choices",
    };
  } finally {
    await coverage.close();
    await mutator.close();
  }
}
