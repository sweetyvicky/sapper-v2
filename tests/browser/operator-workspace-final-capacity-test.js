async (page) => {
  const assert = (v, m) => {
    if (!v) throw Error(m);
  };
  const runs = await page.evaluate(async () => {
    const { request } = await import("/api.js");
    for (const id of window.finalCapacityRuns) {
      const s = (await request("/api/runs/" + id)).snapshot;
      await request("/api/runs/" + id + "/approve", {
        plan_revision: s.plan.revision,
        action_ids: [s.plan.actions[0].id],
        actor: "final-capacity-fixture",
      });
      await request("/api/runs/" + id + "/start", {});
    }
    return window.finalCapacityRuns;
  });
  for (const id of runs)
    await page.waitForFunction(
      async (id) => {
        const s = (await (await fetch("/api/runs/" + id)).json()).snapshot;
        return (
          s.run.status === "running" &&
          s.runtime.tasks.some((t) => t.state === "running")
        );
      },
      id,
      { timeout: 5000 },
    );
  await page
    .getByRole("button", { name: "保存并规划新一轮", exact: true })
    .click();
  await page
    .getByRole("status")
    .filter({ hasText: "草稿已保存" })
    .waitFor({ timeout: 5000 });
  assert(
    (
      await page
        .getByRole("status")
        .filter({ hasText: "草稿已保存" })
        .textContent()
    ).includes("规划失败"),
    "new draft partial success",
  );
  await page
    .getByRole("textbox", { name: "任务名称", exact: true })
    .fill("Final capacity partial-success edited");
  await page.getByRole("button", { name: "保存草稿", exact: true }).click();
  await page.getByRole("button", { name: "编辑草稿", exact: true }).waitFor();
  const draftId = page.url().split("/").pop();
  await page.getByRole("button", { name: "编辑草稿", exact: true }).click();
  await page
    .getByRole("button", { name: "保存并规划新一轮", exact: true })
    .click();
  await page
    .getByRole("status")
    .filter({ hasText: "草稿已保存" })
    .waitFor({ timeout: 5000 });
  await page.getByRole("button", { name: "保存草稿", exact: true }).click();
  await page.getByRole("button", { name: "编辑草稿", exact: true }).waitFor();
  const result = await page.evaluate(async (id) => {
    const { request } = await import("/api.js");
    const t = (await request("/api/tasks/" + id)).task;
    const tasks = (await request("/api/tasks")).tasks;
    return {
      revision: t.revision,
      matches: tasks.filter((t) =>
        t.name.startsWith("Final capacity partial-success"),
      ).length,
      runs: (await request("/api/tasks/" + id + "/runs")).runs.length,
    };
  }, draftId);
  assert(
    result.revision === 4 && result.matches === 1 && result.runs === 0,
    "new and existing retries persist correct revision without duplicates or unmanaged runs",
  );
  return {
    draftId,
    holders: runs,
    ...result,
    proof:
      "real two-active capacity rejection; new/existing save succeeded, plan failed, retry saved correct identity/revision; no duplicate draft/run",
  };
};
