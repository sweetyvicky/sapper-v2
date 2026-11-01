async (page) => {
  const assert = (v, m) => {
    if (!v) throw new Error(m);
  };
  await page.getByRole("tab", { name: "测试过程", exact: true }).click();
  await page
    .getByRole("tabpanel", { name: "测试过程" })
    .getByText("已消费", { exact: true })
    .waitFor();
  const msg = page
    .getByRole("tabpanel", { name: "测试过程" })
    .locator("article")
    .filter({ hasText: "UI_GUIDANCE_20261101" })
    .first();
  assert((await msg.textContent()).includes("消费者"), "actual consumer shown");
  await page.getByRole("tab", { name: "概览", exact: true }).click();
  const guided = page
    .locator(".action-row")
    .filter({ hasText: "GET http://127.0.0.1:9551/guided" });
  assert(
    (await guided.textContent()).includes("待批准"),
    "new guided path pending",
  );
  const runId = new URL(page.url()).hash.split("/").pop();
  const plan = await page.evaluate(async (id) => {
    const deadline = Date.now() + 10000;
    do {
      const { snapshot: s } = await (await fetch("/api/runs/" + id)).json();
      if (
        ["awaiting_approval", "ready", "completed"].includes(s.run.status) &&
        s.plan?.actions.some((a) => a.state === "pending")
      ) return {
        revision: s.plan.revision,
        rowCount: s.plan.actions.length,
        pendingIds: s.plan.actions.filter((a) => a.state === "pending").map((a) => a.id),
      };
      await new Promise((resolve) => setTimeout(resolve, 100));
    } while (Date.now() < deadline);
    throw new Error("current plan did not become available for precise approval");
  }, runId);
  await page.waitForFunction(
    (count) => document.querySelectorAll('.action-row input[type="checkbox"]').length === count,
    plan.rowCount,
    { timeout: 10000 },
  );
  await page.waitForFunction(
    (ids) => ids.every((id) => {
      const cb = document.querySelector('.action-row input[type="checkbox"][value="' + id + '"]');
      return cb && !cb.disabled;
    }),
    plan.pendingIds,
    { timeout: 10000 },
  );
  for (const id of plan.pendingIds) {
    const cb = page.locator('.action-row input[type="checkbox"][value="' + id + '"]');
    await cb.waitFor({ state: "visible" });
    assert(await cb.isEnabled(), "pending action enabled for approval");
    await cb.check();
    assert(await cb.isChecked(), "intended pending action selected before approval");
  }
  assert(
    (await page.locator('.action-row input[type="checkbox"]:checked:not(:disabled)').count()) === plan.pendingIds.length,
    "all and only intended pending actions selected",
  );
  await page.getByRole("button", { name: "仅批准选中", exact: true }).click();
  await page
    .getByRole("button", { name: "开始已批准动作", exact: true })
    .waitFor();
  return {
    guidance: "actual consumed consumer; new path pending before approval",
    approval: "standalone approval; no implicit start",
    planRevision: plan.revision,
    rowCount: plan.rowCount,
    selectedCount: plan.pendingIds.length,
    url: page.url(),
  };
}
