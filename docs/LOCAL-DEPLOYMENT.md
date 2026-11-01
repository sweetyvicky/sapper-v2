# Windows 本地受保护 Mock 军团部署

这里部署的是已实现的受保护 Mock 控制器。Commander 是确定性的可信控制器；Scout、Soldier、General 是执行已批准、受限 HTTP 观察的逻辑角色，不是真实模型智能体。Watchdog 只恢复丢失的空闲角色，不会创建工作或授予权限。目前不支持真实模型军团、模型 API 调用或竞赛模式。

使用 Windows 11、PowerShell 7 和 Docker Desktop 的 Linux 容器模式。在仓库目录执行（部署文件必须先提交到 Git）：

```powershell
$deployment = Join-Path (Get-Location).Path 'work/local-legion'
pwsh -NoProfile -File scripts/local-legion.ps1 -Action Start -HomeDirectory $deployment -Port 8765
pwsh -NoProfile -File scripts/local-legion.ps1 -Action Status -HomeDirectory $deployment
pwsh -NoProfile -File scripts/local-legion.ps1 -Action Open -HomeDirectory $deployment
pwsh -NoProfile -File scripts/local-legion.ps1 -Action Stop -HomeDirectory $deployment
pwsh -NoProfile -File scripts/local-legion.ps1 -Action Start -HomeDirectory $deployment
pwsh -NoProfile -File scripts/local-legion.ps1 -Action Replay -HomeDirectory $deployment -Port 8765
```

`-HomeDirectory` 必须是专用目录的绝对路径。自动化时给 Start/Open/Replay 加 `-NoBrowser`。Start 可重复执行，只等待查看器就绪；有限演练在后台运行约二十秒。Status 显示容器实际状态、退出码、源代码提交/tree 和保留目录。Start 成功表示查看器就绪，不表示演练已经完成：请检查 Status 以及 `artifacts/summary.json`。成功演练明确记录 `exercise_complete=true`、`engagement_complete=false`，未批准工作仍然阻塞。这不是项目验收，也不表示发现真实漏洞。

Open 从当前查看器自身日志读取带片段凭据的完整 URL。这个完整地址应保密，不应发布到 GitHub 或报告。Status 不显示凭据。查看器只有读取功能，没有执行接口。它使用独立的普通 bridge 网络，具有网络能力；Windows 端口只发布在回环地址，不能宣称查看器被禁止出网。

Stop 只删除 ID、完整名称、owner 标签及 run 标签均匹配的本部署资源。全部状态、产物及本地诊断日志保留（日志可能含私密地址）。演练退出后仍可 Stop/Status/Open。Stop 后 Start 打开原有状态的查看器，不重跑已经消费的演练。Replay 只停止当前自有实例，创建新的运行、策略、账本及预算，不重置旧预算，不覆盖旧记录。演练即使中断也算已启动，需要 Replay 才能重新演练。不会注册系统自启动。

`deployment.json` 记录当前运行，`owner.txt` 是持久资源归属标记；文件锁串行化管理操作。`releases/<commit>/` 只从 Git 已提交源代码提取。`runs/<run-id>/source.json` 记录提交、tree 及固定镜像。每次运行有独立的 `state/` 和 `artifacts/`，后者包括 `summary.json`、安全快照 `status.json` 和由实际记录生成的独立 `coverage-demo.html`。请保留部署目录及归属信息，以便安全管理；它是可信操作员控制的存储。

全部容器限制为 2 CPU、512 MiB 内存、128 PID，移除全部 capabilities，启用 no-new-privileges；根文件系统和源代码只读，`/tmp` 为 128 MiB tmpfs。固定镜像：`python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159`。不挂载 Docker socket，不使用 host network。prepare/exercise 使用 `--network none`，仅专用 `/state` 和 `/artifacts` 可写。查看器以只读方式挂载 `/state`，默认只发布 `127.0.0.1:8765:8765`。无论 Windows 路径是什么，容器内部状态路径始终是 `/state`。演练 fixture 只绑定隔离容器内部的 `127.0.0.1:18080`，没有用户目标参数。

策略 30 分钟过期，并发为 1，最多 8 次请求、8000 正文字节、32 预留秒。演练实际发送 4 次请求：三个角色各一次成功观察，另一次故意超出响应字节边界并且不产生成功事实。记录包括无批准零命中、真实运行中快照、步数限制停止、明确合成人工判定、单独计数 N/A、事实撤销、Watchdog 恢复和重复任务拒绝。直接调用 exercise 时 `--pace-seconds` 必须是 0–3 的有限数值，默认 2。失败输出机器可读 JSON，保留状态并关闭所有 fixture/执行线程。

在同等资源约束下，Linux 直接入口为：

```text
python examples/pentest/local_legion.py prepare --state /state --artifacts /artifacts
python examples/pentest/local_legion.py exercise --state /state --artifacts /artifacts --pace-seconds 2
```

prepare 只能初始化全新空状态，每个 exercise 只能启动一次，包括失败。需要本地已有固定镜像，或允许 Docker 正常拉取。脚本不导入密码、凭据或环境密钥。
