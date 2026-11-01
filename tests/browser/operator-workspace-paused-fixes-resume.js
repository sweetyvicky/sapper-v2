async (page) => {
  const assert = (ok, message) => {
    if (!ok) throw new Error(message);
  };
  await page
    .locator(".topline .badge")
    .filter({ hasText: "已暂停" })
    .waitFor({ timeout: 90000 });
  const read = () =>
    page.evaluate(
      async () =>
        (
          await (
            await fetch("/api/runs/" + location.hash.split("/").pop())
          ).json()
        ).snapshot,
    );
  const before = await read(),
    partial = before.budget.limits.requests === 1;
  const beta = before.plan.actions.find((a) => a.target.endsWith("/beta"));
  assert(
    before.runtime.tasks.filter((t) => t.receipt_state === "verified")
      .length === 1,
    "only slow receipt before combined approval",
  );
  assert(
    beta.state === "pending",
    "beta still unapproved before explicit combined",
  );
  assert(
    await page
      .getByRole("button", { name: "开始已批准动作", exact: true })
      .isHidden(),
    "paused cannot offer start",
  );
  const combined = page.getByRole("button", {
    name: "批准选中并继续",
    exact: true,
  });
  assert(
    await combined.isEnabled(),
    "paused explicitly offers legal combined resume",
  );
  await page
    .locator(".action-row")
    .filter({ hasText: "http://127.0.0.1:9551/beta" })
    .getByRole("checkbox")
    .check();
  const responses = [];
  page.on("response", (r) => {
    if (
      r.request().method() === "POST" &&
      /\/(approve|start|resume)$/.test(r.url())
    )
      responses.push({ path: new URL(r.url()).pathname, status: r.status() });
  });
  await combined.click();
  if (partial) {
    await page.getByText(/批准已保存；继续失败：/).waitFor();
    await page
      .locator(".action-row")
      .filter({ hasText: "http://127.0.0.1:9551/beta" })
      .getByText("已批准", { exact: true })
      .waitFor();
    const after = await read();
    assert(
      after.run.status === "paused",
      "refresh shows real paused state after budget failure",
    );
    assert(
      after.plan.actions.find((a) => a.id === beta.id).state === "approved",
      "approval persisted despite execution failure",
    );
    assert(
      after.runtime.tasks.length === 1,
      "failed resume caused no beta dispatch",
    );
    assert(
      await combined.isEnabled(),
      "legal inactive control restored after failure",
    );
    return {
      runId: after.run.id,
      phase: "partial success acknowledged",
      status: after.run.status,
      beta: "approved; no execution",
      responses,
    };
  }
  await page
    .locator(".topline .badge")
    .filter({ hasText: "本批计划完成" })
    .waitFor({ timeout: 90000 });
  const after = await read();
  assert(
    after.runtime.tasks.filter((t) => t.receipt_state === "verified").length ===
      2,
    "slow and beta execute exactly once",
  );
  assert(
    responses.some((r) => r.path.endsWith("/approve")) &&
      responses.some((r) => r.path.endsWith("/resume")) &&
      !responses.some((r) => r.path.endsWith("/start")),
    "combined paused action approves then resumes only",
  );
  return {
    runId: after.run.id,
    phase: "combined resume completed",
    verifiedReceipts: 2,
    responses,
  };
}
