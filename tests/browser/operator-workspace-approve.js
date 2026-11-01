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
  const pending = page.getByRole("checkbox").filter({ visible: true });
  for (const cb of await page.getByRole("checkbox").all())
    if (await cb.isEnabled()) await cb.check();
  await page.getByRole("button", { name: "仅批准选中", exact: true }).click();
  await page
    .getByRole("button", { name: "开始已批准动作", exact: true })
    .waitFor();
  return {
    guidance: "actual consumed consumer; new path pending before approval",
    approval: "standalone approval; no implicit start",
    url: page.url(),
  };
}
