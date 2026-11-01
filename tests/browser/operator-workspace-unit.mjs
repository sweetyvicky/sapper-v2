import assert from "node:assert/strict";
import { action, modelSummary } from "../../lib/pentest/operator_web/ui.js";
const box = { textContent: "", classList: { add() {}, remove() {} } },
  trigger = { disabled: false };
await action(
  box,
  async () => {
    box.textContent = "";
  },
  trigger,
);
assert.equal(
  box.textContent,
  "操作成功",
  "A form reset after successful save must still acknowledge success",
);
assert.equal(trigger.disabled, false);
assert.equal(
  modelSummary(
    { model_profile_id: null, role_profiles: { Commander: "commander" } },
    [{ id: "commander", name: "实际规划配置" }],
  ).includes("Commander（规划）：实际规划配置"),
  true,
);
assert.equal(
  modelSummary({ model_profile_id: null, role_profiles: { Scout: "scout" } }, [
    { id: "scout", name: "观察模型" },
  ]).includes("基础观察"),
  false,
);
assert.equal(
  modelSummary({ model_profile_id: null, role_profiles: {} }),
  "基础观察（不调用模型）",
);
console.log(
  "PASS: save acknowledgement survives form reset; role-only model modes remain visible",
);
import * as ui from "../../lib/pentest/operator_web/ui.js";
assert.equal(
  typeof ui.roundOptions,
  "function",
  "Older selected rounds must stay in the selector after loading history",
);
const rounds = ui.roundOptions(
  [{ id: "recent", created_at: 1, status: "completed" }],
  "older",
);
assert.deepEqual(
  rounds.map(([id]) => id),
  ["recent", "older"],
);
assert.equal(rounds[1][1].includes("历史轮次"), true);
const many = Array.from({ length: 50 }, (_, i) => ({
  id: "recent-" + i,
  created_at: 1,
  status: "completed",
}));
assert.equal(ui.roundOptions(many, "older").length, 51);
assert.equal(
  ui.roundOptions(many, "older")[0][1].includes("最近第 1 轮"),
  true,
);
console.log(
  "PASS: historical selected round retained outside latest 50; recent ordering labelled honestly",
);

// Focused DOM regressions. These unit-only API stubs exercise the actual views;
// real backend/receipt journeys live in operator-workspace-review-fixes.js.
class TestNode {
  constructor(tag = "#text", text = "") {
    this.tagName = tag.toUpperCase();
    this.children = [];
    this.parentNode = null;
    this.attrs = {};
    this.listeners = {};
    this._text = text;
    this._value = undefined;
    this.disabled = false;
    this.checked = false;
    this.className = "";
    this.classList = {
      add: (c) => {
        this.className += " " + c;
      },
      remove: (c) => {
        this.className = this.className
          .split(" ")
          .filter((x) => x !== c)
          .join(" ");
      },
    };
  }
  setAttribute(k, v) {
    this.attrs[k] = String(v);
    if (k === "disabled") this.disabled = true;
    if (k === "value") this._value = String(v);
    if (k === "id") this.id = v;
  }
  addEventListener(k, fn) {
    (this.listeners[k] ||= []).push(fn);
  }
  async emit(k) {
    for (const fn of this.listeners[k] || []) await fn({ preventDefault() {} });
  }
  append(...nodes) {
    for (const node of nodes) {
      if (node.parentNode)
        node.parentNode.children = node.parentNode.children.filter(
          (n) => n !== node,
        );
      node.parentNode = this;
      this.children.push(node);
    }
  }
  replaceChildren(...nodes) {
    for (const n of this.children) n.parentNode = null;
    this.children = [];
    this._text = "";
    this.append(...nodes);
  }
  get textContent() {
    return this._text + this.children.map((n) => n.textContent).join("");
  }
  set textContent(v) {
    this.replaceChildren();
    this._text = String(v ?? "");
  }
  get options() {
    return this.children.filter((n) => n.tagName === "OPTION");
  }
  get value() {
    if (this.tagName === "SELECT") {
      return this._value === undefined
        ? this.options[0]?.value || ""
        : this.options.some((o) => o.value === this._value)
          ? this._value
          : "";
    }
    return this._value ?? "";
  }
  set value(v) {
    this._value = String(v ?? "");
  }
  contains(node) {
    return node === this || this.children.some((n) => n.contains(node));
  }
  querySelectorAll(selector) {
    return descendants(this).filter((n) => {
      if (selector.startsWith("#")) return n.id === selector.slice(1);
      if (selector.startsWith("."))
        return n.className.split(" ").includes(selector.slice(1));
      if (selector.startsWith("input"))
        return (
          n.tagName === "INPUT" &&
          (!selector.includes(":checked") || n.checked) &&
          (!selector.includes(":not(:disabled)") || !n.disabled)
        );
      return n.tagName === selector.toUpperCase();
    });
  }
  querySelector(s) {
    return this.querySelectorAll(s)[0] || null;
  }
  replaceWith(node) {
    const p = this.parentNode;
    if (p) {
      p.children[p.children.indexOf(this)] = node;
      node.parentNode = p;
      this.parentNode = null;
    }
  }
}
const descendants = (node) =>
  node.children.flatMap((n) => [n, ...descendants(n)]);
globalThis.Node = TestNode;
globalThis.document = {
  createElement: (tag) => new TestNode(tag),
  createTextNode: (text) => new TestNode("#text", text),
  activeElement: null,
};
const root = () => new TestNode("main");
const control = (host, label) =>
  descendants(host).find(
    (n) => n.tagName === "LABEL" && n.children[0]?.textContent === label,
  )?.children[1];
const btn = (host, text) =>
  descendants(host).find(
    (n) => n.tagName === "BUTTON" && n.textContent === text,
  );
const json = (value) => ({ ok: true, json: async () => value });
const failures = [];
async function regression(name, fn) {
  try {
    await fn();
    console.log("PASS: " + name);
  } catch (e) {
    failures.push(name);
    console.error("FAIL: " + name + " — " + e.message);
  }
}
const { taskEditor } = await import(
  "../../lib/pentest/operator_web/task_editor.js"
);
const { findingsView } = await import(
  "../../lib/pentest/operator_web/findings_view.js"
);
const { coverageView } = await import(
  "../../lib/pentest/operator_web/coverage_view.js"
);
const { modelsView } = await import(
  "../../lib/pentest/operator_web/models_view.js"
);
const { runView } = await import("../../lib/pentest/operator_web/run_view.js");
for (const role of ["default", "Scout"])
  await regression(
    "R1 unavailable " + role + " is explicit and save/prepare blocked",
    async () => {
      const host = root(),
        posts = [];
      const data = {
        assets: [{ target: "http://synthetic.invalid/a" }],
        model_profile_id: role === "default" ? "deleted" : "survivor",
        role_profiles: role === "default" ? {} : { Scout: "deleted" },
      };
      globalThis.fetch = async (path, opts) => {
        if (opts.method === "POST") {
          posts.push(path);
          return json({ task: { id: "draft", revision: 2 } });
        }
        return json(
          path === "/api/models"
            ? {
                profiles: [
                  { id: "survivor", name: "Survivor", model: "fixture" },
                ],
              }
            : { task: { data, revision: 1 } },
        );
      };
      await taskEditor(host, "draft", () => {});
      const chosen = control(
        host,
        role === "default" ? "默认模型配置" : "Scout · 观察分析",
      );
      assert.equal(
        chosen.value,
        "deleted",
        "missing saved ID must remain selected",
      );
      assert.ok(
        chosen.options.find((o) => o.value === "deleted")?.disabled,
        "missing option must be unavailable",
      );
      assert.match(host.textContent, /配置已不可用/);
      await btn(host, "保存草稿").emit("click");
      await btn(host, "保存并规划新一轮").emit("click");
      assert.deepEqual(
        posts,
        [],
        "repair is required before writing draft or planning",
      );
      control(host, "运行方式").value = "basic";
      await control(host, "运行方式").emit("change");
      await btn(host, "保存草稿").emit("click");
      assert.equal(posts.length, 1, "explicit basic clears missing choices");
    },
  );
const observation = (id = "fact", valid = true) => ({
  fact_id: id,
  valid,
  evidence: [
    { id: "e-" + id, target: "http://synthetic.invalid/a", finished_at: 1 },
  ],
});
const finding = (status = "candidate") => ({
  id: "case",
  fact_id: "fact",
  title: "Synthetic case",
  target: "http://synthetic.invalid/a",
  status,
  severity: "low",
  description: "Original",
  narrative_revision: 1,
  reviews: [],
  evidence: [],
});
await regression(
  "R2 unfocused forms survive changed snapshots and focused status updates",
  async () => {
    const host = root(),
      view = findingsView(host, "run", async () => {});
    const snapshot = {
      findings: [finding()],
      observations: [observation()],
      review_suggestions: [],
    };
    view.update(snapshot);
    const review = control(host, "复核说明"),
      retest = control(host, "复测指导"),
      actor = control(host, "撤销署名");
    review.value = "unsaved review";
    retest.value = "unsaved retest";
    actor.value = "unsaved invalidation";
    await btn(host, "编辑完整叙述").emit("click");
    const narrative = control(host, "漏洞描述");
    narrative.value = "unsaved narrative";
    document.activeElement = review;
    view.update({
      ...snapshot,
      findings: [finding("stale")],
      observations: [observation("fact", false)],
    });
    assert.ok(
      host
        .querySelectorAll(".badge")
        .some((n) => n.textContent === "证据已失效"),
      "read-only case status refreshes while input focused",
    );
    document.activeElement = null;
    view.update({
      ...snapshot,
      findings: [finding("stale")],
      observations: [observation("fact", false)],
    });
    assert.equal(control(host, "复核说明"), review);
    assert.equal(review.value, "unsaved review");
    assert.equal(control(host, "复测指导"), retest);
    assert.equal(retest.value, "unsaved retest");
    assert.equal(control(host, "撤销署名"), actor);
    assert.equal(actor.value, "unsaved invalidation");
    assert.equal(control(host, "漏洞描述"), narrative);
    assert.equal(narrative.value, "unsaved narrative");
    const evidence = control(host, "复核证据（同目标、较晚、独立回执）");
    assert.equal(
      evidence.value,
      "e-fact",
      "invalid evidence is not silently substituted",
    );
    assert.ok(evidence.options.find((o) => o.value === "e-fact")?.disabled);
  },
);
await regression(
  "R2 review-only form survives tab blur and changed advice",
  async () => {
    const host = root(),
      view = findingsView(host, "run", async () => {}),
      snapshot = {
        findings: [finding()],
        observations: [observation()],
        review_suggestions: [],
      };
    view.update(snapshot);
    const review = control(host, "复核说明");
    review.value = "blurred draft";
    document.activeElement = null;
    view.update({
      ...snapshot,
      review_suggestions: [
        { finding_id: "case", outcome: "inconclusive", note: "Fresh advice" },
      ],
    });
    assert.equal(control(host, "复核说明"), review);
    assert.equal(review.value, "blurred draft");
    assert.match(host.textContent, /Fresh advice/);
  },
);
await regression(
  "R4 open coverage refreshes reasons/assessment/eligibility and retains inputs",
  async () => {
    const host = root(),
      view = coverageView(host, "run", async () => {});
    const cell = {
      asset_id: "asset",
      check_id: "manual",
      state: "covered",
      reasons: [],
    };
    const snapshot = {
      coverage: {
        assets: [{ id: "asset", target: "http://synthetic.invalid/a" }],
        checks: [{ id: "manual", method: "manual" }],
        cells: [cell],
      },
      observations: [observation(), observation("survivor")],
      runtime: { tasks: [] },
    };
    view.update(snapshot);
    await btn(host, "有有效证据").emit("click");
    const actor = control(host, "评估署名"),
      reason = control(host, "评估理由"),
      fact = control(host, "选择事实 fact"),
      survivor = control(host, "选择事实 survivor");
    actor.value = "draft actor";
    reason.value = "draft reason";
    fact.checked = survivor.checked = true;
    view.update({
      ...snapshot,
      coverage: {
        ...snapshot.coverage,
        cells: [
          {
            ...cell,
            state: "evidence_gap",
            reasons: ["backing fact invalid"],
            assessment: {
              actor: "saved actor",
              outcome: "not_applicable",
              note: "saved assessment",
            },
          },
        ],
      },
      observations: [observation("fact", false), observation("survivor")],
      runtime: {
        tasks: [],
        evidence: {
          facts: [
            { id: "fact", valid: false, invalid_reasons: ["fact revoked"] },
            { id: "survivor", valid: true },
          ],
        },
      },
    });
    assert.match(host.textContent, /支撑事实当前无效/);
    assert.match(host.textContent, /saved assessment/);
    assert.equal(control(host, "评估署名"), actor);
    assert.equal(actor.value, "draft actor");
    assert.equal(reason.value, "draft reason");
    assert.ok(control(host, "选择事实 fact").disabled);
    assert.ok(control(host, "选择事实 survivor").checked);
    assert.match(host.textContent, /事实已被主动撤销/);
  },
);
await regression(
  "R5 model delete retains eligibility, success feedback and blocks duplicate",
  async () => {
    const host = root();
    let deletes = 0;
    let release;
    const p = {
      id: "profile",
      provider: "deepseek",
      name: "Disposable",
      base_url: "http://fixture.invalid",
      model: "fixture",
    };
    globalThis.fetch = async (path, opts) => {
      if (opts.method === "POST") {
        deletes++;
        await new Promise((r) => (release = r));
        return json({ deleted: true });
      }
      return json({
        profiles: [p],
        presets: { deepseek: { base_url: "http://fixture.invalid" } },
      });
    };
    await modelsView(host);
    await btn(host, "Disposable · DeepSeek").emit("click");
    const remove = btn(host, "删除此配置");
    const pending = remove.emit("click");
    await Promise.resolve();
    await remove.emit("click");
    assert.equal(deletes, 1);
    release();
    await pending;
    assert.equal(
      remove.disabled,
      true,
      "no selection means Delete remains disabled",
    );
    assert.ok(btn(host, "测试已保存连接").disabled);
    assert.equal(btn(host, "保存模型配置").disabled, false);
    assert.match(host.textContent, /操作成功/);
  },
);
await regression(
  "R3 paused combined approval resumes and partial failure acknowledges persisted approval",
  async () => {
    const host = root(),
      writes = [];
    let reads = 0;
    const snapshot = {
      run: { draft_id: "draft", status: "paused" },
      draft: { assets: [], exclusions: [] },
      plan: {
        revision: 1,
        actions: [
          {
            id: "pending",
            state: "pending",
            target: "http://synthetic.invalid/a",
          },
        ],
      },
      messages: [],
      model_calls: [],
      events: [],
      findings: [],
      observations: [],
      review_suggestions: [],
      coverage: { assets: [], checks: [], cells: [] },
      runtime: { tasks: [] },
    };
    globalThis.fetch = async (path, opts) => {
      if (opts.method === "POST") {
        writes.push(path);
        if (path.endsWith("/resume"))
          return {
            ok: false,
            json: async () => ({
              error: { message: "Synthetic execution failure" },
            }),
          };
        return json({ run: snapshot.run });
      }
      if (path === "/api/models") return json({ profiles: [] });
      if (path === "/api/tasks/draft")
        return json({
          task: { id: "draft", data: { name: "Synthetic" }, revision: 1 },
          runs: [{ id: "run" }],
        });
      reads++;
      return json({ snapshot });
    };
    const dispose = await runView(host, "draft", "run", () => {});
    try {
      const combined = btn(host, "批准选中并继续");
      assert.ok(combined, "paused state must explicitly offer resume");
      const checkbox = host
        .querySelectorAll("input")
        .find((n) => n.value === "pending");
      checkbox.checked = true;
      await combined.emit("click");
      assert.deepEqual(writes, [
        "/api/runs/run/approve",
        "/api/runs/run/resume",
      ]);
      assert.match(host.textContent, /批准已保存/);
      assert.match(host.textContent, /Synthetic execution failure/);
      assert.ok(reads >= 2, "refresh actual state even after partial success");
    } finally {
      dispose();
    }
  },
);
await regression(
  "R4 capture timestamp alone does not detach interactive coverage rows",
  async () => {
    const host = root(),
      view = coverageView(host, "run", async () => {});
    const snapshot = {
      coverage: {
        captured_at: 1,
        assets: [{ id: "asset", target: "http://synthetic.invalid/a" }],
        checks: [{ id: "manual", method: "manual" }],
        cells: [
          { asset_id: "asset", check_id: "manual", state: "not_started" },
        ],
      },
      observations: [],
      runtime: { tasks: [], evidence: { facts: [] } },
    };
    view.update(snapshot);
    const row = btn(host, "未开始");
    view.update({
      ...snapshot,
      coverage: { ...snapshot.coverage, captured_at: 2 },
    });
    assert.equal(
      btn(host, "未开始"),
      row,
      "poll capture time must not replace the live click target",
    );
  },
);
if (failures.length)
  throw new Error(
    `${failures.length} focused regressions failed: ${failures.join("; ")}`,
  );
