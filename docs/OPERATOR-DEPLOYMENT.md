# Windows 本地操作工作台

打开工作台 → 模型设置 → 新建任务 → 审核计划 → 测试过程 → 漏洞与报告。

工作台保存任务草稿、运行、审批、证据、模型配置和密钥。启动和刷新不会自动准备任务、连接模型、请求目标或重放历史操作。需要 Windows 11、PowerShell 7、启用 Linux 容器的 Docker Desktop，以及已完整提交的项目副本。

## 启动和日常使用

在项目目录打开 PowerShell，运行：

```powershell
& ./scripts/operator-workspace.ps1 -Action Start
```

首次安装会捕获当前已提交代码，随后打开浏览器。默认只发布到本机 `http://127.0.0.1:8765/`。端口被占用时会拒绝启动，不停止任何现有服务。已运行安装上的 Start 保持原版本；状态会显示实际安装的提交与 tree。

```powershell
& ./scripts/operator-workspace.ps1 -Action Status
& ./scripts/operator-workspace.ps1 -Action Open
& ./scripts/operator-workspace.ps1 -Action Stop
```

关闭浏览器不会停止工作台。Open 用当前进程的私有入口重新打开页面；普通刷新使用会话 Cookie。重启后旧会话失效，重新执行 Open。`-NoBrowser` 适合自动检查：不会打开浏览器，也不会打印秘密入口。

默认安装目录在项目外的同级 `work/operator-workspace`。自定义时必须使用专用绝对目录：

```powershell
& ./scripts/operator-workspace.ps1 -Action Start -HomeDirectory 'C:\your-work\operator-workspace' -Port 8877
```

后续所有命令使用同一 HomeDirectory。Status、Open、Stop 以已安装版本为准，无需当前 Git HEAD 与它相同。停止后再次 Start 会安装当前干净、已提交的代码，并沿用相同的 state/models 目录；历史源代码和部署记录保留。替换前先完整捕获并验证候选源代码；源代码不支持、归档或校验失败时保留上一安装的资源和记录，修正代码后可正常查看、停止或重试。运行中的 Start 不升级。不要自行修改快照或部署记录，完整性/归属不符会拒绝继续。

## 模型与任务

模型设置中选择 DeepSeek、GLM、LongCat 或自定义兼容 HTTPS 地址，输入自己的模型名和密钥并保存。保存不会连接提供方；只有显式连接测试或使用模型的任务操作才发送请求。密钥保存在私有 models 目录的独立文件中，不在环境变量、启动参数、公开状态或源代码快照中。密钥为本地明文，须按凭据保护备份。

新建任务时填写名称、目标、资产和限制，可先保存草稿。准备计划会解析授权范围；审核明确动作后才能执行。暂停、取消和重启不退还已消耗额度。模型建议不是人工确认；当前批次完成也不表示全部资产评估完成。参见 [服务说明](OPERATOR-SERVICE.md)、[模型说明](MODEL-CONFIGURATION.md)及 [HTTP 接口](OPERATOR-API.md)。

## 保存与边界

安装目录具有以下稳定结构：

| 路径 | 内容 |
| --- | --- |
| state | 持久草稿、运行、审批、证据与额度 |
| models | 配置和独立密钥文件 |
| releases | 每次启动捕获的 Git 提交快照及 SHA256 文件清单 |
| runtime | 私有当前入口、历史日志、历史部署元数据 |
| deployment.json | 当前资源 ID、名字、归属标签、版本及生命周期状态 |

首次写入前限制整个安装目录 Windows ACL，仅当前用户、SYSTEM 和 Administrators 可访问；每次操作检查 ACL 和目录链接。已有非空未知目录、junction/symlink、异常 ACL、源代码变动和 Docker 资源归属不符都会拒绝操作。不要将安装目录放入共享目录、公共同步目录或仓库；勿公开 runtime 或 deployment.json。脚本不读取密钥正文。

Python 使用固定摘要的 Linux 镜像，根文件系统和代码挂载只读，仅 state/models 可写，另有受限 /tmp tmpfs。容器使用独立普通 bridge、2 CPU、1 GiB 内存、128 进程上限、移除 capabilities 和禁止提权；无 Docker socket、特权或 host 网络。主机端口只绑定 127.0.0.1。普通 bridge 允许用户选定的 HTTPS 提供方和已批准目标请求；范围/审批/额度由软件执行，这不是整个系统的网络出口隔离，也不是防御已控制主机或解释器的攻击者。

## 停止、故障和升级

Stop 验证记录的精确 ID、名称、标签、网络、挂载、入口及资源限制，仅操作自己的资源。它允许 **300 秒**完成当前有界调用与存储排空，并显示 stop_pending。文件系统阻塞可能超出正常调用时限；停止未完成、退出非零或强停会明确记录 `stop_incomplete_or_forced`，不能当作干净关闭。Status 发现进程未经已记录的干净 Stop 而退出时，记录 `unexpected_exit`、退出码及 OOM 标记并返回失败；即使退出码为 0，也不会沿用 ready 或声称是正常停止。正常 Stop 后的 Status 仍成功返回 `stopped_clean`。

遇到异常退出时，先运行 Status，检查私有日志中必要的错误，处理故障原因，再有意识地执行恢复：

```powershell
& ./scripts/operator-workspace.ps1 -Action Status
& ./scripts/operator-workspace.ps1 -Action Start -AcknowledgePreviousFailure
& ./scripts/operator-workspace.ps1 -Action Open
```

自定义安装时继续带同一 HomeDirectory 和所需 Port。该确认选项只用于已有、已停止且需要处理的失败；不会强杀运行中的实例、修改密钥、删除任务或自动执行历史工作。失败退出仍保存在 `lastFailure` 和历史部署记录中，记录观察时间、原提交/资源、退出码、OOM 标记及确认时间；上一关闭不会改称干净。无需手工编辑可信记录或删除 state/models。所有状态保留，异常重启仍遵守 needs_attention/uncertain、不自动重放规则；恢复后仍需查看任务状态、对账并显式决定后续动作。

就绪检查包含真实页面、bootstrap 会话交换及认证后的任务/模型读取；仅 Docker 显示 running 不算就绪。就绪失败保留资源与私有诊断，Status 会报错。检查时只查看状态和日志中必要的错误，勿复制其中秘密入口。脚本不会在失败后自动删除数据、强杀或重放。候选源代码验证完成后，移除旧资源与创建新资源并非原子操作；此后 Docker 删除/创建失败或进程中断仍可能留下缺失资源的部分部署。该边界不属于源代码捕获失败的保留保证：保留 deployment.json、候选快照和历史记录，由熟悉 Docker 的维护者核验归属后处理；不应绕过校验或删除 state/models。

旧 8765 查看器的替换应先在另一专用目录、空闲端口验证新的已提交版本，再核验旧资源归属、保留旧源代码/运行/元数据后停止旧查看器。最终切换失败时，用保留的旧精确资源与元数据恢复它；不能删除旧状态。脚本自身不会接管或停止旧查看器。

## 验证

```powershell
& ./tests/browser/operator-deployment-tests.ps1
# 仅使用专用验收目录和空闲端口；会保存明确标识的合成草稿及不调用提供方的合成密钥。
& ./tests/browser/operator-deployment-tests.ps1 -Integration -HomeDirectory 'C:\your-work\operator-workspace-acceptance' -Port 8877
# 每次使用全新的专用目录；在隔离副本中建立测试提交，不移动当前分支。
& ./tests/browser/operator-deployment-tests.ps1 -Regression Source -HomeDirectory 'C:\your-work\correction-source' -Port 8879
& ./tests/browser/operator-deployment-tests.ps1 -Regression Exit -HomeDirectory 'C:\your-work\correction-exit' -Port 8879
node tests/browser/operator-workspace-unit.mjs
```

集成检查验证真实生命周期、重复 Start、不泄漏入口、快照篡改拒绝、错误资源 ID 拒绝、端口冲突、重启持久化。Source 回归验证干净但不支持的已提交源代码被拒绝后，旧安装仍可管理并重试；Exit 仅强停刚创建的自有合成实例，验证真实 exit 137 的状态、明确确认恢复、失败记录和数据保留。它没有模拟或声称验证真实内存耗尽。所有检查不连接真实提供方、不准备或执行目标任务。验收数据不能复制进全新的生产目录。前端标准库测试在独立 Node 24.10.0 CI job 中运行；Python 3.12/3.13 的离线矩阵保持独立。
