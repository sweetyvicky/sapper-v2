async (page) => {
  const assert = (v, m) => {
    if (!v) throw new Error(m);
  };
  const slow = page
    .locator(".action-row")
    .filter({ hasText: "GET http://127.0.0.1:9551/slow" })
    .getByRole("checkbox");
  await slow.check();
  await page
    .getByRole("button", { name: "批准选中并开始", exact: true })
    .click();
  const runId = new URL(page.url()).hash.split("/").pop();
  await page.evaluate(async (id) => {
    const deadline = Date.now() + 5000;
    do {
      const { snapshot } = await (await fetch("/api/runs/" + id)).json();
      if (
        snapshot.run.status === "running" &&
        snapshot.runtime.tasks.some(
          (task) =>
            task.state === "running" &&
            task.proposal.action.target === "http://127.0.0.1:9551/slow",
        )
      ) return;
      await new Promise((resolve) => setTimeout(resolve, 100));
    } while (Date.now() < deadline);
    throw new Error("slow task did not enter running state before guidance");
  }, runId);
  await page.getByRole("tab", { name: "测试过程", exact: true }).click();
  await page
    .getByRole("textbox", { name: "给本轮的人工指导", exact: true })
    .fill(
      "验收指导唯一标记 UI_GUIDANCE_20261101：请新增 /guided 路径观察，保持现有边界。",
    );
  await page
    .getByRole("button", { name: "发送并重新规划", exact: true })
    .click();
  await page
    .getByRole("status")
    .filter({
      hasText:
        /^已排队（尚未消费）：[0-9a-f]{32} · 消费者：.+ · 结果：.+。新动作仍须另行批准。/,
    })
    .waitFor();
  await page
    .getByRole("tabpanel", { name: "测试过程" })
    .getByText("已排队（尚未消费）", { exact: true })
    .waitFor();
  const input = page.getByRole("textbox", {
    name: "给本轮的人工指导",
    exact: true,
  });
  await input.fill("还没发送的草稿：保持这个输入");
  await input.press("Home");
  await input.press("ArrowRight");
  const before = await input.evaluate((e) => ({
    start: e.selectionStart,
    end: e.selectionEnd,
  }));
  await page.waitForTimeout(2600);
  assert(
    (await input.inputValue()) === "还没发送的草稿：保持这个输入",
    "composer persists polling",
  );
  assert(
    (await input.evaluate((e) => e.selectionStart)) === before.start,
    "caret persists polling",
  );
  await page.screenshot({
    path: ".superpowers/operator/ui-validation/active-guidance.png",
    fullPage: true,
  });
  return {
    queue: "queued receipt, not consumed while request inflight",
    composer: "text/caret preserved over >=2 polls",
    url: page.url(),
  };
}
