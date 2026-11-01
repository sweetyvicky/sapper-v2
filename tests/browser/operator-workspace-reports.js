async (page) => {
  const assert = (v, m) => {
    if (!v) throw new Error(m);
  };
  await page.getByRole("tab", { name: "报告", exact: true }).click();
  const frame = page.frameLocator('iframe[title="本轮报告预览"]');
  await frame.locator("body").filter({ hasText: "合成验收" }).waitFor();
  const text = await frame.locator("body").textContent();
  for (const marker of [
    "验证批准边界",
    "合成叙述",
    "仅用于合成验收",
    "后续独立同目标回执",
    "stale",
    "UI_GUIDANCE_20261101",
  ])
    assert(text.includes(marker), "report content " + marker);
  assert(
    (await frame.locator("script").count()) === 0,
    "preview contains no executable scripts",
  );
  assert((await frame.locator("img").count()) === 0, "injected image escaped");
  const files = [];
  for (const [name, extension] of [
    ["HTML", "html"],
    ["Markdown", "md"],
    ["JSON", "json"],
  ]) {
    const event = page.waitForEvent("download");
    await page.getByRole("link", { name: "下载 " + name, exact: true }).click();
    const download = await event;
    const path =
      ".superpowers/operator/ui-validation/downloads/report." + extension;
    await download.saveAs(path);
    files.push(path);
  }
  await page.screenshot({
    path: ".superpowers/operator/ui-validation/report-preview.png",
    fullPage: true,
  });
  return {
    preview:
      "authenticated same-origin sandbox; full narratives/coverage/review/stop reason/guidance; malicious markup escaped",
    downloads: files,
  };
}
