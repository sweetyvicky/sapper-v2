async (page) => {
  const runs = await page.evaluate(async () => {
    const { request } = await import("/api.js");
    const assets = (
      await request("/api/assets/preview", {
        text: "http://127.0.0.1:9551/slow",
        format: "lines",
      })
    ).preview.assets;
    const t = (
      await request("/api/tasks", {
        data: {
          name: "Final capacity holders",
          goal: "Hold two owned synthetic slots",
          assets,
          allowed_tools: ["http_get"],
          max_request_seconds: 30,
          budgets: { seconds: 120 },
        },
      })
    ).task;
    const ids = [];
    for (let i = 0; i < 2; i++)
      ids.push(
        (
          await request("/api/tasks/" + t.id + "/runs", {
            expected_revision: t.revision,
          })
        ).run.id,
      );
    return ids;
  });
  for (const id of runs)
    await page.evaluate(async (id) => {
      const deadline = Date.now() + 30000;
      do {
        const { snapshot } = await (await fetch("/api/runs/" + id)).json();
        if (snapshot.run.status === "awaiting_approval") return;
        await new Promise((resolve) => setTimeout(resolve, 100));
      } while (Date.now() < deadline);
      throw new Error("capacity holder did not reach awaiting_approval");
    }, id);
  await page.getByRole("link", { name: "任务", exact: true }).click();
  await page.getByRole("button", { name: "新建任务", exact: true }).click();
  await page
    .getByRole("textbox", { name: "任务名称", exact: true })
    .fill("Final capacity partial-success");
  await page
    .getByRole("textbox", { name: "测试目标与成功标准", exact: true })
    .fill("Retain successful saves after real capacity rejection");
  await page
    .getByRole("textbox", {
      name: "批量资产（每行一个网址、域名或 IP）",
      exact: true,
    })
    .fill("http://127.0.0.1:9551/alpha");
  await page
    .getByRole("button", { name: "预览并检查资产", exact: true })
    .click();
  await page.getByText("有效 1 · 重复 0 · 错误 0", { exact: true }).waitFor();
  await page.evaluate((ids) => {
    window.finalCapacityRuns = ids;
  }, runs);
  return {
    runs,
    proof:
      "two separate prepared basic runs; new editor ready, no target execution yet",
  };
}
