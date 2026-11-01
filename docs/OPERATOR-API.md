# 本地操作工作区 HTTP API v1

此适配层只调用 [受保护服务](OPERATOR-SERVICE.md)、[数据接口](OPERATOR-DATA.md)和现有模型配置接口。没有任意方法调用、文件上传、文件读取、命令执行或数据库修改路由。运行状态、证据、预算和审批以服务返回的完整记录为准。当前批次 `completed` 不代表安全评估或委托验收完成；`engagement_complete` 始终为 false。

## 启动与身份

在 Linux / Linux Docker 中运行，标准库即可：

```text
PYTHONPATH=lib python -m pentest.workspace --root /state/operator --models-root /state/models --port 8766
```

根路径和可选模型目录必须为绝对路径；模型目录默认在工作区的 models 下。默认只监听 127.0.0.1；端口默认 0，由系统分配。`--container-listen` 仅在检测到 Docker 且端口非零时允许监听容器 0.0.0.0。部署必须只发布主机 `127.0.0.1:端口:端口`，不能把 Host 检查当作网络隔离。启动和 GET 均不访问模型、DNS 或目标。旧只读 dashboard 不变。

启动只输出一次带随机片段的 `http://127.0.0.1:端口/#片段` 地址。此地址只属于当前进程的本地操作身份，不是多人账号系统。不要把真实片段、密钥或 Cookie 放进报告、查询参数、命令历史、浏览器存储或其他日志。关闭普通请求日志、框架错误日志及原始异常输出。

所有请求必须恰好有一个 `Host: 127.0.0.1:端口`。任何出现的 Origin 必须恰好等于 `http://127.0.0.1:端口`；POST 必须带此 Origin。无 CORS、OPTIONS 授权或 Authorization 登录方式。

| 方法 / 路径 | 请求 | 200 响应 |
|---|---|---|
| POST /api/session | `{token:string}`，片段中的 bootstrap token | `{csrf_token:string,ready:true}`，设置会话 Cookie |
| GET /api/session | 有效 Cookie | `{csrf_token:string,ready:true}` |

Cookie 名为 `sapper_operator_端口`，值为进程随机凭据，属性 `Path=/; HttpOnly; SameSite=Strict`。本地 HTTP 不设置 Secure。一个 Cookie 头可以包含其他端口的不同 Cookie；重复 Cookie 名、重复 Cookie 头或其他安全头歧义均拒绝。POST /api/session 只接受有效 bootstrap token，不要求既有 Cookie/CSRF；其余 API 需要 Cookie，且 POST 还需要 `X-Sapper-CSRF: csrf_token`，常量时间比较。Cookie、CSRF、bootstrap 在重启后全部失效；普通刷新通过 GET /api/session 恢复 CSRF，不需要再次取得片段。

前端初始化示例（示例只传递当前页面已有的片段，不包含真实凭据）：

```javascript
const token = location.hash.slice(1);
history.replaceState(null, '', location.pathname);
const response = await fetch('/api/session', token ? {
  method: 'POST', headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({token})
} : {});
const session = await response.json(); // 检查 response.ok 后将 CSRF 仅保存在内存
```

## 公共请求与错误规则

POST 使用 `application/json` 或 `application/json; charset=utf-8`，明确 Content-Length，严格 UTF-8 对象。每个完整请求体最多 **1,048,576 字节**，包括 JSON 包装和转义；此限制比底层草稿的 4MiB 限制更严格。拒绝重复 JSON 键、NaN/Infinity、浮点溢出、未配对代理项、超过 64 层的嵌套和非对象顶层。缺字段、未知字段和结构错误在副作用前拒绝；语义/状态约束仍由受保护服务验证。布尔值不能充当版本号或分页整数。

拒绝重复 Host/Origin/Authorization/CSRF/Cookie/Content-Type/Content-Length/Transfer-Encoding，拒绝任何 Transfer-Encoding、Authorization、方法覆盖头。只接受原始 origin-form 路径；不接受绝对 URL、重复斜线、点路径、反斜线、百分号编码、片段或尾随路由别名。查询键不能重复或未知，不做 URL 解码或宽松数字转换。GET 不接受非空请求体。仅支持以下明确列出的 GET/POST，其他方法返回 405。错误响应固定：

```json
{"error":{"code":"conflict","message":"当前状态或版本不允许此操作，请刷新后重试"}}
```

正常分类：400 请求格式/字段、403 会话/来源/CSRF、404 缺失记录/路由、405 方法、408 接收超时、409 状态/版本/预算、413 体积、415 媒体类型、422 内容语义/模型配置、503 存储/连接/忙碌/关闭中。代码为 `invalid_request`、`access_denied`、`not_found`、`method_not_allowed`、`receive_timeout`、`conflict`、`payload_too_large`、`unsupported_media_type`、`invalid`、`unavailable`；可进一步为安全的 `budget`、`key_required`、`invalid_endpoint`、`invalid_profile`、`invalid_fields`、`timeout`、`profile_changed`。message 是固定中文说明，不携带原始异常、地址、响应体或密钥。连续滴流到接收期限的连接可能直接关闭而无 JSON 响应。线程额度耗尽返回相同错误包装的 503，并关闭连接。

所有响应 no-store、nosniff、no-referrer。普通页面/API CSP 为 default-src none、script/style/connect/frame-src self，无内联脚本、eval、远程资源、表单或外部嵌入祖先权限。

## 模型

| 方法 / 路径 | 精确请求对象 | 响应 |
|---|---|---|
| GET /api/models | 无查询 | `{profiles:[publicProfile],presets:{deepseek,glm,longcat,custom}}` |
| GET /api/models/{profile_id} | 无查询 | `{profile:publicProfile}` |
| POST /api/models | `{profile,profile_id?}` | `{profile:publicProfile}` |
| POST /api/models/{profile_id}/delete | `{}` | `{deleted:true}` |
| POST /api/models/{profile_id}/test | `{}` | `{test:{status:"ok",latency_ms,usage}}` |

profile_id 必须为规范小写带连字符 UUID。profile 必须包含 name、provider、base_url、model，可选 api_key、timeout_seconds、max_output_tokens；不接受其他字段。完整边界见 [模型配置](MODEL-CONFIGURATION.md)。公开记录只有元数据和 has_key，不返回保存的密钥。缺省/空 key 只允许复用同一 provider 和规范服务地址的旧 key；地址或提供方改变必须重新输入 key。save/list/get/delete 不调用提供方。只有明确 test POST 发起最小 `Reply OK.` 请求，不返回提供方正文；配置错误或连接失败不会切换提供方、重试或伪造成功。

## 资产、草稿与准备

| 方法 / 路径 | 精确请求对象 / 查询 | 响应 |
|---|---|---|
| POST /api/assets/preview | `{text:string,format:"lines"\|"csv"}` | `{preview:{assets,errors,duplicates,counts}}` |
| GET /api/tasks | `limit=50&offset=0`，limit 1..100、offset 0..1000000 | `{tasks:[draftSummary]}` |
| POST /api/tasks | `{data:draftData}` | `{task:draftRecord}` |
| GET /api/tasks/{task_id} | 无查询 | `{task:draftRecord,runs:[runSummary]}` |
| GET /api/tasks/{task_id}/runs | `limit=50&offset=0`，同上分页边界 | `{runs:[runSummary]}` |
| POST /api/tasks/{task_id} | `{data:draftData,expected_revision:positiveInteger}` | `{task:draftRecord}` |
| POST /api/tasks/{task_id}/runs | `{expected_revision:positiveInteger}` | **202** `{run:fullRunRecord}` |

分页数字是规范十进制，不接受 +、前导零（单独 0 除外）、小数、空值或百分号转义。draftRecord/data/summary 与解析结果使用 [数据接口](OPERATOR-DATA.md)的原始完整形状；task detail 的 runs 最多为最新 100 个摘要，更早记录通过 GET /api/tasks/{task_id}/runs 分页读取，该路由先检查草稿存在。task/run/finding/fact 标识均为小写 32 位 UUIDhex。草稿保存不是准备；prepare 的 202 只表示异步记录/作业已创建。前端应轮询 snapshot。预览错误逐行显示，不能默默丢弃错误资产。解析、保存及 GET 不创建 campaign、解析 DNS 或发起目标请求。

只解析资产的安全示例：

```javascript
await fetch('/api/assets/preview', {
  method: 'POST', headers: {'Content-Type':'application/json', 'X-Sapper-CSRF':session.csrf_token},
  body: JSON.stringify({text:'https://example.invalid/', format:'lines'})
});
```

## 运行、消息、覆盖与发现

以下前缀 `R` 为 `/api/runs/{run_id}`；每个 JSON 成功响应均为 200，prepare 除外。所有对象拒绝未知字段。完整记录形状和状态解释见 [服务接口](OPERATOR-SERVICE.md)。

| 方法 / 路径 | 精确请求对象 | 响应 |
|---|---|---|
| GET R | 无查询 | `{snapshot:publicSnapshot}` |
| POST R/approve | `{plan_revision:positiveInteger,action_ids:[UUIDhex],actor:string}` | `{run:fullRunRecord}` |
| POST R/start、R/pause、R/resume、R/cancel | `{}` | `{run:fullRunRecord}` |
| POST R/messages | `{request_id:UUIDhex,kind,text,action_ids?,finding_id?}` | `{message:messageRecord}` |
| POST R/coverage/assess | `{asset_id,check_id,outcome,actor,note,fact_ids:[UUIDhex]}` | `{assessment:assessmentRecord}` |
| POST R/findings | `{fact_id,title,severity,reporter,description,impact,reproduction,remediation,cwe,operator_note}` | `{finding:fullCase}` |
| GET R/findings/{finding_id} | 无查询 | `{finding:fullCase}` |
| POST R/findings/{finding_id}/narrative | `{data:narrativeData,expected_revision:positiveInteger\|null}` | `{finding:fullCase}` |
| POST R/findings/{finding_id}/review | `{reviewer,evidence_id,outcome,note}` | `{finding:fullCase}` |
| POST R/facts/{fact_id}/invalidate | `{actor,reason}` | `{affected_fact_ids:[UUIDhex]}` |

approve 接受 1..500 个唯一 UUIDhex；只批准所显示的 plan_revision 和 action_ids，actor 非空 <=160 字符。start/resume 均不自动批准。运行中的 pause/cancel 先返回 requested 状态，当前有界操作结束后才完成。过期/预算不会因重试、暂停、取消或恢复返还。

消息 kind 只能为 guidance/prioritize/retest，request_id 提供幂等性，text 为非空 <=4000 字符。guidance 不带动作或发现；prioritize 需要 1..100 个动作且无发现；retest 需要 finding_id 且动作列表为空。可选项默认 action_ids=[]、finding_id=null。记录分别为 queued/consumed/failed，consumer/result 表示实际消费者或仅记录，无权批准目标。模型失败后，修正对应 profile 并明确 resume；已完成目标不会重复。失败 guidance 需要新的 request_id，不能把旧失败消息当成已发给模型。

coverage outcome 只能为 completed/not_applicable，必须遵守人工检查及证据匹配约束。创建发现要求全部十个字段，cwe/operator_note 可为空；只产生 candidate。narrativeData 只包含 description/impact/reproduction/remediation（必填）和 cwe/operator_note（可选，默认空）。expected_revision=null 仅修复原本缺失的叙述；正常编辑要求当前版本。review outcome 为 confirmed/rejected/inconclusive，要求独立的复核署名/标识（必须不同于原报告者及事实创建者；本地单会话不验证第二个人的身份）、较晚独立回执且目标匹配。模型建议不自动确认。撤销事实会使依赖失效、发现 stale，报告也立即反映当前有效性。

## 报告和打包静态资源

`GET R/report?format=html|markdown|json&download=1`：format 默认 html，download 默认 1，且只能为 0/1。仅 html 允许 download=0（认证后的内联预览）。返回原始 UTF-8 报告文本，MIME 分别 text/html、text/markdown、application/json；固定文件名 `run-<UUIDhex>.html|md|json`，不用任务名或调用者文件名。下载设置 attachment，预览设置 inline。GET 绝不运行分析、执行、审批或目标请求。

报告 Header CSP 只有 `base-uri 'none'; form-action 'none'; frame-ancestors 'self'`（预览）或 `'none'`（下载）。底层报告自己的 meta CSP 仍生效；原始报告字节完整保留，未来可信静态 CSS 哈希不会被额外 default-src/style-src Header 覆盖。不使用 unsafe-inline。预览 iframe 使用 sandbox，不允许脚本、表单或弹窗；仅在同源认证加载确需时允许 allow-same-origin。

无会话可读取的页面仅为固定打包的 `/`、`/app.css`、`/app.js`、`/api.js`、`/task_editor.js`、`/run_view.js`、`/models_view.js`、`/findings_view.js`。它们映射到独立 operator_web 包目录的确定文件名，没有参数驱动的路径。UI 尚未打包时根页面明确显示 backend ready；其余缺失文件返回 404，不提供占位工作流。所有任务、模型、报告、会话状态 API 仍需认证。

## 线程、关闭和所有权

最多 8 个请求线程；超过额度即 503/关闭连接，不排出无限线程。每个连接只处理一个请求。接收时限为从 handler 建立起的 **整体 10 秒**（头和正文合计），不是可被滴流延长的空闲时限；侧效应前再次检查期限。每个请求最多一个有界计时器，finish 取消并等待其退出。响应 socket 也有 10 秒超时。Provider test 服从现有完整调用时限（配置最大 120 秒，另有本地配置读取）；不自动重试。

同步写入通过单独 gate：包括模型 save/delete、草稿 save 和全部会写入的 Workspace 方法。gate 获取最多等待 35 秒；队列请求拿到 gate 后再次检查 closing。网络调用不在 gate 内，服务异步作业保留其自身所有权。关闭首先停止 admission 和 listener；等待已经进入的唯一同步写入，再调用 Workspace.close，随后等待仍归 HTTP 所有的读请求/连接测试/响应线程。监听线程自己请求关闭时由独立关闭线程处理，避免 shutdown 自等待。

close gate 和写排空 gate 都有 35 秒等待期限。写排空超时会明确报关闭未完成，**不调用 Workspace.close、不释放 root flock**，可待本地写入结束后再次 close。Workspace.close 请求引擎暂停并保留其 135 秒作业 join 约束；此前状态读取/写入仍受本地存储等待影响，不能宣称关闭瞬时完成或总计只需 135 秒。随后 HTTP handler join 使用一个共享 140 秒期限，连接测试与引擎等待重叠，不能声称尚未完成的连接测试已终止。正常 close 返回时已没有 HTTP handler；工厂拥有 Workspace 时也已没有引擎作业。

没有将文件系统卡顿伪装成硬实时总期限。Workspace SQLite 单次等待最多 30 秒、模型配置 SQLite 5 秒；多个服务状态事务及不受控文件系统可能延长过程。建议部署使用保守 **300 秒**停止宽限期并检查退出结果；超时强停不能标为 clean，重启沿用 needs_attention/uncertain、不自动重放的既有恢复规则。可信注入实现若违反界限也可能导致关闭未完成；保留所有权并报告，不在后台遗留可写 handler 后声称成功。

Python 测试工厂为 `create_server(root=None, port=0, *, models_root=None, container_listen=False, workspace=None, owns_workspace=False)`。给 root 时创建且拥有 Workspace；给 workspace 时禁止同时给 root/models_root，默认由调用者拥有，只有显式 owns_workspace=True 才关闭它。两种形式都拥有 listener/handlers，close/server_close 等价且可重复；注入参数不是 CLI 选项。端口绑定失败会释放工厂新建且拥有的 Workspace。SIGINT/SIGTERM 停止监听、完成上述关闭；bootstrap URL 不重复输出。
