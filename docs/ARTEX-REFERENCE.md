# ARTEX 参考研究与独立实现决策

日期：2026-11-01。用户希望参考 ARTEX 的实现思路，服务日常渗透工作，尤其是可视化测试过程、资产覆盖与测试覆盖。此次只借鉴数据关系和交互组织方式；不复制其源码、界面代码、图标、截图或其他资源到 Sapper。

原 `Autumn-27/ARTEX` 地址实际返回 404。上一轮覆盖视图通过公开备份 `jaykwok/ARTEX` 读取原版 v0.3.15 的固定提交 [`e6ec56999175509551a1e43a3ee3b053d0941bd9`](https://github.com/jaykwok/ARTEX/tree/e6ec56999175509551a1e43a3ee3b053d0941bd9)，当时未研究备份仓库后续的任务操作流程。

| 研究位置 | 从源码确认的思路 | 在 Sapper 中的独立实现 |
|---|---|---|
| [`db/task_scope.go`](https://github.com/jaykwok/ARTEX/blob/e6ec56999175509551a1e43a3ee3b053d0941bd9/db/task_scope.go) | 任务范围确定资产分母，关联事实的资产计入粗略已测数；分母为零时比例为空 | 显式、可版本化的资产与测试计划；空分母显示“尚无计划”，不显示 100% |
| [`db/task_assets_context.go`](https://github.com/jaykwok/ARTEX/blob/e6ec56999175509551a1e43a3ee3b053d0941bd9/db/task_assets_context.go) | 当前任务与直接来源任务的范围、锚点共同构成覆盖视图 | 本轮只展示一个 Campaign；任务必须显式绑定计划单元，按有效回执/事实重新计算，避免仅按文本匹配 |
| [`db/exploration.go`](https://github.com/jaykwok/ARTEX/blob/e6ec56999175509551a1e43a3ee3b053d0941bd9/db/exploration.go) 的 AssetRefs | 一个资产可以下钻到关联意图、事实和发现 | 点击矩阵单元或资产，查看任务、执行回执、证据有效性和复核状态 |
| [`coverage-graph-tab.tsx`](https://github.com/jaykwok/ARTEX/blob/e6ec56999175509551a1e43a3ee3b053d0941bd9/web/src/app/(main)/function/tasks/detail/_tabs/coverage-graph-tab.tsx) | 按类型展示层级关系、已测高亮、大分支折叠，以及资产详情抽屉 | 原生 HTML/CSS/JavaScript 的可折叠资产树、覆盖矩阵和详情面板，沿用 Sapper 数据而非重建 Go/Next.js 技术栈 |
| [`transcript.tsx`](https://github.com/jaykwok/ARTEX/blob/e6ec56999175509551a1e43a3ee3b053d0941bd9/web/src/components/transcript.tsx) | 按工具调用标识配对执行与结果，按角色和时间组织过程 | 以现有任务 ID、回执 ID、审计序列关联执行过程，展示角色、时间、结果与阻塞原因 |
| [`detail/page.tsx`](https://github.com/jaykwok/ARTEX/blob/e6ec56999175509551a1e43a3ee3b053d0941bd9/web/src/app/(main)/function/tasks/detail/page.tsx) | 周期刷新任务、统计，分标签浏览过程与覆盖 | 本地工作台自动刷新，连接中断明确提示并标记旧数据；可导出离线快照与真实隔离演示回放 |

## 日常工作中的覆盖口径

资产覆盖：当前计划内至少有一个有效完成测试单元的资产 / 当前计划内资产。组织节点不参与分母，单个子节点完成不会自动把父资产算作已覆盖。

测试覆盖：当前计划中有效完成的“资产 × 检查项”单元 / 应测单元。人工标记不适用需要身份归属和原因，单独显示并从应测分母排除。未纳入计划、未开始、排队/阻塞、运行中、失败、待人工判定、证据失效都不计为完成。

自动完成仅用于明确的 HTTP GET/HEAD 观察项，需要匹配目标、工具、任务、真实成功回执和仍有效的观察事实。访问控制、输入校验等日常安全检查使用人工判定型计划项，不能由一次普通 HTTP 成功响应自动完成。人工完成需要有效且目标匹配的事实依据。这是此前只读覆盖视图的能力边界；下述操作工作台迭代另行接入模型配置和受控任务流程。

计划修订、结果依据及人工排除均留记录。视图说明自身是实时数据还是某时刻的快照，所有百分比均展示分子、分母及计算口径；不把覆盖率解释为资产安全证明。


## 操作工作台：补充研究二开版本

用户指出此前只读视图缺少任务输入、过程交互、漏洞详情和报告。本轮重新审查了三个公开二开版本的相关源码，未运行参考应用，也未读取本机 ARTEX 的密钥或业务数据。

主要参考为 [jaykwok/ARTEX 固定提交 25c34ee](https://github.com/jaykwok/ARTEX/tree/25c34eeb4f96072b11b66d54c8d3c001a3662673)。这是对具体交互实现的选择，不是对整个项目质量或运行效果的认证。

| 操作 | 核实的参考实现 | Sapper 的设计要求 |
|---|---|---|
| 下发任务 | [任务表单与提交参数](https://github.com/jaykwok/ARTEX/blob/25c34eeb4f96072b11b66d54c8d3c001a3662673/web/src/app/%28main%29/function/tasks/page.tsx#L3061)：目标、描述、模型配置、资产集合 | 单独的任务创建入口；批量资产解析预览；目标、补充信息与硬约束分别保存 |
| 批量资产 | [资产页](https://github.com/jaykwok/ARTEX/blob/25c34eeb4f96072b11b66d54c8d3c001a3662673/web/src/app/%28main%29/function/tasks/detail/_tabs/assets-tab.tsx#L283)解析多行范围并提交结构化数组 | 展示合法、重复与错误行；保存草稿不发起目标请求；进入执行前展示明确计划 |
| 运行中补充 | [人工续接处理](https://github.com/jaykwok/ARTEX/blob/25c34eeb4f96072b11b66d54c8d3c001a3662673/server/intent_intervention.go#L29)及 [工作单元消费](https://github.com/jaykwok/ARTEX/blob/25c34eeb4f96072b11b66d54c8d3c001a3662673/agent/worker.go#L507) | 消息先持久化，再记录实际消费者；接收成功与模型已消费分别显示 |
| 漏洞详情 | [发现详情页](https://github.com/jaykwok/ARTEX/blob/25c34eeb4f96072b11b66d54c8d3c001a3662673/web/src/app/%28main%29/function/findings/detail/page.tsx#L149)将证据、报告、复测与状态分开 | 每个候选发现可打开完整说明、影响、复现步骤、修复建议、证据及独立复核历史 |
| 复测 | [证据快照与复测结果契约](https://github.com/jaykwok/ARTEX/blob/25c34eeb4f96072b11b66d54c8d3c001a3662673/server/finding_retests.go#L144) | 新执行保留原始证据；未复现、失败与已确认分别记录；不自动确认模型声称的漏洞 |
| 成果 | [报告预览](https://github.com/jaykwok/ARTEX/blob/25c34eeb4f96072b11b66d54c8d3c001a3662673/web/src/app/%28main%29/function/tasks/detail/_tabs/report-tab.tsx#L15)和 [导出范围](https://github.com/jaykwok/ARTEX/blob/25c34eeb4f96072b11b66d54c8d3c001a3662673/server/server.go#L2077) | 任务报告入口、可见错误、完整漏洞内容与覆盖缺口；本轮采用 HTML、Markdown、JSON |
| 模型配置 | [模型配置记录](https://github.com/jaykwok/ARTEX/blob/25c34eeb4f96072b11b66d54c8d3c001a3662673/db/config.go#L14)和 [Provider 构造](https://github.com/jaykwok/ARTEX/blob/25c34eeb4f96072b11b66d54c8d3c001a3662673/agent/provider.go#L253) | 用户在本机界面保存多个模型配置；任务选择配置；密钥与公开元数据分开，模型输出只作为待验证数据 |

另外核查 [bdg9412/artex-ko-plus 80695c6](https://github.com/bdg9412/artex-ko-plus/tree/80695c642adc9fc6959ccddf999a5d6b91b87cd6) 与 [panda0x123/artex-ymh 48adc7f](https://github.com/panda0x123/artex-ymh/tree/48adc7f1d8f62cbc47e658c9a2b47d6f63ca6cb1)。所查人工输入与复测流程主要沿用共同实现；没有证据表明其相关流程比上述主要参考更完善，因此没有按星数或宣传文字排名。

参考代码中有两个不能照搬的假设：人工消息的内存交接不等于重启后仍可保证送达；后续轮次注入的文字约束不等于程序强制范围。Sapper 的消息消费记录与执行策略必须独立持久化，模型不能自行批准或扩大范围。ARTEX 是调用已配置模型服务的应用，也不能据此推断它自身提供可供复用的模型 API。
