# 测试覆盖工作台

这是受保护 Mock controller 的原生中文只读工作台。四个视图分别显示覆盖矩阵、计划声明的资产关系、实际执行与审计过程、证据与发现。没有模型调用、自动新增漏洞工具、目标浏览器预览或执行按钮。目标地址始终是不可导航的文本。

## 一条命令生成隔离回放

在仓库根目录的 Windows PowerShell 7 执行。Docker Desktop 需要可用，固定镜像应已下载。此命令以 `--network none` 运行，只有容器自己的临时 loopback fixture 会被请求。产物可以直接用 `file://` 打开，无需服务、网络或安装前端依赖。

```powershell
$Image = 'python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159'
New-Item -ItemType Directory -Force ./outputs | Out-Null
docker run --rm --network none --cpus 2 --memory 512m --pids-limit 128 --cap-drop ALL --security-opt no-new-privileges --read-only --tmpfs /tmp:rw,nosuid,nodev,size=128m --mount "type=bind,source=$PWD,target=/src,readonly" --mount "type=bind,source=$PWD/outputs,target=/output" --workdir /src --env PYTHONDONTWRITEBYTECODE=1 $Image python lib/sapper.py pentest dashboard-demo --output /output/coverage-demo.html
Start-Process (Join-Path $PWD 'outputs/coverage-demo.html')
```

成功输出为一行 JSON，含 `accepted:true`、`synthetic:true`、实际 `metrics` 和 `frames`。九帧均来自真实只读 snapshot：未测、无批准阻塞、排队、fixture 等待 Event 时的实际执行中、有效 HTTP 观察、带归属的 synthetic manual assessment、不适用、HTTP 字节边界失败、事实撤销后的覆盖下降。Commander / Scout / Soldier / General 都是真实 controller 角色。演示采用 90 秒范围、60 秒精确批准与有限预算，不永久授权。临时服务、执行线程和状态在退出时清理。

默认打开最后一帧；点击“播放过程”从第一帧开始，或使用上一步、下一步、滑块。每帧显示捕获时间与说明。回放从不轮询网络，数字不由播放器模拟。最终视图仍保留有效完成项、阻塞、失败、证据缺口、不适用和未开始项。

## Windows 持久状态与只读实时查看

当前核心使用 Linux 文件锁，请在 Linux / Docker 中运行。持久化 controller 的绝对根路径绑定在配置中；**Windows 目录从初始化开始就必须挂到 `/state`**。不要把先在 `/tmp/...` 初始化的状态搬到 `/state`；路径不符会明确失败，不提供修改绑定绕过或自动迁移。

下面初始化只创建 controller 和导入计划，不运行任何目标请求。操作员阶段明确允许 `/state` 写入；源码始终只读。

```powershell
$Image = 'python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159'
New-Item -ItemType Directory -Force ./coverage-state | Out-Null
$State = (Resolve-Path ./coverage-state).Path
$OperatorArgs = @('run', '--rm', '--network', 'none', '--cpus', '2', '--memory', '512m', '--pids-limit', '128', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--read-only', '--tmpfs', '/tmp:rw,nosuid,nodev,size=128m', '--mount', "type=bind,source=$PWD,target=/src,readonly", '--mount', "type=bind,source=$State,target=/state", '--workdir', '/src', '--env', 'PYTHONPATH=/src/lib', '--env', 'PYTHONDONTWRITEBYTECODE=1')
docker @OperatorArgs $Image python -c "import json,time; from pentest.cli import initialize; from pentest.policy import Policy; p=json.load(open('examples/pentest/policy.json')); p['expires_at']=time.time()+180; initialize('/state',Policy.from_dict(p)); print('initialized /state')"
docker @OperatorArgs $Image python lib/sapper.py pentest coverage-import --state /state --plan examples/pentest/coverage-plan.json --actor local-operator
docker @OperatorArgs $Image python lib/sapper.py pentest coverage-status --state /state
```

使用专用启动器查看这个状态：

```powershell
./scripts/coverage-console.ps1 -State $State -Port 8765
```

打开控制台输出的完整 `http://127.0.0.1:8765/#...` 地址。`#` 后为每个服务进程随机生成的查看凭据。页面仅保存在内存中，立即从地址栏移除；API 用 `X-Sapper-Viewer` 显式传递，不进入查询、请求日志、localStorage、JSON 下载或 HTML 导出。停止用 Ctrl+C。启动器验证绝对状态目录和端口，创建唯一的普通 dedicated Docker bridge，前台启动固定 Python 3.12 镜像，退出清理自身网络，不删除用户文件。

**边界说明：**Windows 主机只发布 `127.0.0.1:8765:8765`；容器的显式 `--container-listen` 模式监听 `0.0.0.0`，只在检测到 `/.dockerenv` 且非零端口时允许。容器通过普通 bridge 具有网络能力，不能宣称 OS 级出站隔离。它是独立只读显示进程，源码与 `/state` 均只读挂载，无执行入口，也不会请求目标。不要自行改成公开地址发布，Host 检查本身不能保证网络隔离。Docker internal 网络的端口发布问题见 [Moby 维护者说明](https://github.com/moby/moby/discussions/53256)。测试和演示生成仍使用 `--network none`。

原生 Linux 默认模式直接绑定 loopback，支持自动选择空闲端口：

```text
python lib/sapper.py pentest dashboard --state /absolute/existing/state --port 0
```

没有任意 `--host` 参数。只允许 GET `/`、`/app.css`、`/app.js`、`/api/snapshot`；要求精确 `Host: 127.0.0.1:实际端口`，拒绝跨 Origin、缺少凭据的 API、查询、未知路径和写方法。响应使用 no-store、nosniff、no-referrer、限制本地资源与禁止嵌框的 CSP。服务不调用执行器、status/sync/watchdog，也不回收租约或改变 graph / 数据库。

## 操作员计划、人工判定与导出

所有写入只能通过受信任操作员 CLI，姓名是归属信息，不是身份认证。脚本入口和 `PYTHONPATH=lib` 下的 `python -m pentest.cli` 支持同一组命令。

```text
coverage-import --state DIR --plan FILE --actor NAME
coverage-assess --state DIR --asset-id ID --check-id ID --outcome completed|not_applicable --actor NAME --note TEXT [--fact-id ID ...]
coverage-status --state DIR
dashboard --state DIR --port 0 [--container-listen]
dashboard-export --state DIR --output FILE
dashboard-demo --output FILE
```

示例计划 [coverage-plan.json](../examples/pentest/coverage-plan.json) 与既有 [manual.sh](../examples/pentest/manual.sh) 的 loopback fixture 和 `local-observe` 任务 ID 匹配。`manual.sh` 是短期隔离演示，会删除自身临时状态；不要把它当持久项目初始化工具。持久项目的操作员仍须按既有政策验证、精确批准和有限预算执行流程生成真实事实。导入计划不会批准或运行任务。

以下为同一 `/state` 的操作员判定示例。不适用必须写明确理由：

```powershell
docker @OperatorArgs $Image python lib/sapper.py pentest coverage-assess --state /state --asset-id fixture --check-id transaction --outcome not_applicable --actor local-reviewer --note '此静态 fixture 没有交易流程，明确排除此项'
```

完成人工检查需要真实且仍有效、目标完全匹配的观察事实。先从 `coverage-status` 的 `runtime.evidence.facts` 确认 ID，然后使用 `--fact-id 实际ID`，可重复传入多个。只有 HTTP 成功不会自动完成人工安全检查。错误 ID、撤销事实、错误目标、无证据等都失败，不授予批准、预算或发现审阅权。

离线单文件导出命令（将输出挂载显式加入只读查看参数）：

```powershell
New-Item -ItemType Directory -Force ./outputs | Out-Null
$ReadArgs = @('run', '--rm', '--network', 'none', '--cpus', '2', '--memory', '512m', '--pids-limit', '128', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--read-only', '--tmpfs', '/tmp:rw,nosuid,nodev,size=128m', '--mount', "type=bind,source=$PWD,target=/src,readonly", '--mount', "type=bind,source=$State,target=/state,readonly", '--mount', "type=bind,source=$PWD/outputs,target=/output", '--workdir', '/src', '--env', 'PYTHONDONTWRITEBYTECODE=1')
docker @ReadArgs $Image python lib/sapper.py pentest dashboard-export --state /state --output /output/snapshot.html
Start-Process (Join-Path $PWD 'outputs/snapshot.html')
```

HTML 嵌入原生 CSS/JS 和转义后的安全 JSON，使用脚本与样式哈希 CSP，没有外部文件、fetch 要求或凭据。显示“离线快照”及捕获时间，不宣称实时。页面“导出数据”下载当前快照 JSON；回放时导出当前帧。

## 公式与溯源

- 资产覆盖 = 至少有一个有效完成单元格的 included 非 group 资产 / 所有 included 非 group 计划资产。清单内没有测试项的资产仍在资产分母；父节点不继承信用。树上聚合仅用于导航。
- 测试覆盖 = 有效完成单元格 /（当前明确计划配对数 − 操作员明确归属的不适用配对数）。显示 covered / total 与比例，不适用单列。零分母显示“尚无应测项”或“尚无计划资产”，比例为 null。
- `http_get` / `http_head` 只表示有效的匹配 HTTP 观察；`manual` 要求带事实关联的人工完成判定。未列入计划的资产×检查配对显示“未纳入计划”，区别于“不适用”。
- 状态为未开始、排队中、已阻塞、执行中、执行失败、待人工判定、证据失效/缺口、已完成、不适用。选中单元格立即显示阻塞/判定原因、当前和以前尝试、提案文本、事实/回执/证据安全元数据和实际发现审阅状态。
- task_ids 声明顺序有意义，最后一个是当前尝试。旧成功不会覆盖后来的失败/缺口。计划规范化内容一致时导入幂等；内容变更增加修订。人工判定只属于当前修订，变更计划后必须重新判定，旧记录仍留历史。
- HTTP 成功要求现有批准、action/intent/task、receipt、fact、evidence、目标与方法的完整绑定。失效、撤销、过期或损坏的证据会移除完成信用，不能靠旧尝试恢复。发现保持 EvidenceStore 的 candidate / confirmed / rejected / inconclusive / stale 实际状态，覆盖不能自动确认漏洞。
- 审计按稳定 sequence、task ID / receipt ID 关联，不靠数组位置。显示最近 200 条并标明总数与截断；人工判定历史最近 100 条。安全元数据包括来源、方法、时间、peer、状态、字节数/hash、归属和撤销，不包含响应原文或 controller 文件路径。

## 刷新、可用性与限制

实时页在可见且启用自动刷新时每两秒串行请求，不重叠；刷新按钮可手动重试。失败保留上次成功数据，但明显显示“已断开 / 数据可能过期”和上次成功时间。读取损坏状态返回简洁 503 JSON，不返回路径或响应原文。快照和回放完全禁用网络轮询。多个 SQLite 文件独立只读读取，不宣称跨数据库分布式原子快照。

搜索按资产名称/目标，筛选按类型或单元格状态。显示筛选行数/全体行数；全局分母不变。键盘可使用 tabs、展开/折叠、矩阵按钮和回放滑块，Esc 关闭详情并恢复合理焦点。窄屏导航换行，卡片两列，矩阵在容器内横向滚动。目标、恶意标签和 Unicode 以纯文本呈现，不获取站点图标、截图或网页。

状态目录与操作员主机仍是信任根；此界面没有多用户登录、远程 controller、更强管理员篡改抵抗、自动安全结论、浏览器执行或实时 LLM 会话。查看凭据只能读取快照，不能授权任何操作。缺失和损坏的已有来源显式报错，不静默当空计划。只读挂载需要 SQLite sidecar 时应修复读取方式，不把状态改成可写。
