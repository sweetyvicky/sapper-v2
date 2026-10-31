# ARTEX 参考研究与独立实现决策

日期：2026-11-01。用户希望参考 ARTEX 的实现思路，服务日常渗透工作，尤其是可视化测试过程、资产覆盖与测试覆盖。此次只借鉴数据关系和交互组织方式；不复制其源码、界面代码、图标、截图或其他资源到 Sapper。

原 `Autumn-27/ARTEX` 地址实际返回 404。本次通过公开备份 `jaykwok/ARTEX` 读取原版 v0.3.15 的固定提交 [`e6ec56999175509551a1e43a3ee3b053d0941bd9`](https://github.com/jaykwok/ARTEX/tree/e6ec56999175509551a1e43a3ee3b053d0941bd9)，不混用备份仓库后续修改。

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

自动完成仅用于明确的 HTTP GET/HEAD 观察项，需要匹配目标、工具、任务、真实成功回执和仍有效的观察事实。访问控制、输入校验等日常安全检查使用人工判定型计划项，不能由一次普通 HTTP 成功响应自动完成。人工完成需要有效且目标匹配的事实依据。当前不新增实际漏洞检测器或真实模型适配器。

计划修订、结果依据及人工排除均留记录。视图说明自身是实时数据还是某时刻的快照，所有百分比均展示分子、分母及计算口径；不把覆盖率解释为资产安全证明。
