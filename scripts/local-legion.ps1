[CmdletBinding()]
param(
    [ValidateSet('Start','Status','Open','Stop','Replay')][string]$Action = 'Status',
    [string]$HomeDirectory = (Join-Path $PSScriptRoot '../work/local-legion'),
    [ValidateRange(1,65535)][int]$Port = 8765,
    [switch]$NoBrowser
)
$ErrorActionPreference = 'Stop'
$pythonImage = 'python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159'
if (-not [IO.Path]::IsPathFullyQualified($HomeDirectory)) { throw 'HomeDirectory 必须是绝对路径。' }
$base = [IO.Path]::GetFullPath($HomeDirectory)
if ($base -eq [IO.Path]::GetPathRoot($base) -or $base.TrimEnd('\','/') -eq [Environment]::GetFolderPath('UserProfile').TrimEnd('\','/')) {
    throw '请选择专用部署目录，不能使用磁盘根目录或用户主目录。'
}
New-Item -ItemType Directory -Path $base -Force | Out-Null
$lock = [IO.File]::Open((Join-Path $base 'operation.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
$manifestPath = Join-Path $base 'deployment.json'
$ownerPath = Join-Path $base 'owner.txt'
$source = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
function Docker([string[]]$Arguments) {
    $output = & docker.exe @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) { throw ('Docker operation failed: ' + ($output -join "`n")) }
    return ($output -join "`n")
}
function Save-Manifest {
    $temporary = Join-Path $base 'deployment.pending.json'
    $script:manifest | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $temporary -Encoding utf8
    Move-Item -LiteralPath $temporary -Destination $manifestPath -Force
}
function Inspect-Owned($resource, [string]$kind) {
    if (-not $resource -or -not $resource.id) { return $null }
    $raw = & docker.exe $kind inspect $resource.id 2>$null
    if ($LASTEXITCODE -ne 0) { return $null }
    $item = ($raw -join "`n" | ConvertFrom-Json -AsHashtable)[0]
    $labels = if ($kind -eq 'container') { $item.Config.Labels } else { $item.Labels }
    $name = $item.Name.TrimStart('/')
    if ($item.Id -ne $resource.id -or $name -ne $resource.name -or
        $labels['sapper.local.owner'] -ne $script:owner -or $labels['sapper.local.run'] -ne $script:manifest.runId) {
        throw '资源归属不匹配，已拒绝操作。'
    }
    return $item
}
function Stop-Owned {
    foreach ($key in @('exercise','viewer','prepare')) {
        $resource = $script:manifest[$key]
        $item = Inspect-Owned $resource 'container'
        if ($item) {
            # Preserve private process logs locally; never emit the fragment credential.
            $logPath = Join-Path $script:manifest.artifacts ($key + '.log')
            & docker.exe logs $resource.id 2>&1 | Set-Content -LiteralPath $logPath -Encoding utf8
            if ($item.State.Running) { Docker @('stop','--time','10',$resource.id) | Out-Null }
            Docker @('rm',$resource.id) | Out-Null
        }
    }
    if (Inspect-Owned $script:manifest.network 'network') {
        Docker @('network','rm',$script:manifest.network.id) | Out-Null
    }
    $script:manifest.stopped = $true
    Save-Manifest
}
function Viewer-Url {
    $item = Inspect-Owned $script:manifest.viewer 'container'
    if (-not $item -or -not $item.State.Running) { return $null }
    $logs = Docker @('logs',$script:manifest.viewer.id)
    $match = [regex]::Match($logs, 'http://127\.0\.0\.1:\d+/#[A-Za-z0-9_-]+')
    if ($match.Success) { return $match.Value }
    return $null
}
function Resource-Status($resource) {
    $item = Inspect-Owned $resource 'container'
    if (-not $item) { return @{ name=$resource.name; present=$false } }
    return @{ name=$resource.name; id=$item.Id; present=$true; running=$item.State.Running;
        status=$item.State.Status; exitCode=$item.State.ExitCode }
}
function Show-Status {
    if (-not $script:manifest) { @{ installed=$false } | ConvertTo-Json; return }
    @{ installed=$true; runId=$script:manifest.runId; version=$script:manifest.version; tree=$script:manifest.tree;
       state=$script:manifest.state; artifacts=$script:manifest.artifacts;
       viewer=(Resource-Status $script:manifest.viewer); exercise=(Resource-Status $script:manifest.exercise);
       url=('http://127.0.0.1:'+$script:manifest.port+'/');
       scope='仅合成回环演练；逻辑 Mock 角色，不是真实模型';
       viewerNetwork='独立普通 bridge；查看器具有网络能力' } | ConvertTo-Json -Depth 8
}
function Container-Args([string]$name, [string]$network, [bool]$readOnlyState) {
    $stateMount = 'type=bind,source='+$script:manifest.state+',target=/state'
    if ($readOnlyState) { $stateMount += ',readonly' }
    $result = @('create','--name',$name,'--label',('sapper.local.owner='+$script:owner),
        '--label',('sapper.local.run='+$script:manifest.runId),'--network',$network,
        '--cpus','2','--memory','512m','--pids-limit','128','--cap-drop','ALL',
        '--security-opt','no-new-privileges','--read-only','--tmpfs','/tmp:rw,nosuid,nodev,size=128m',
        '--mount',('type=bind,source='+$script:manifest.release+',target=/src,readonly'),
        '--mount',$stateMount,'--workdir','/src','--env','PYTHONDONTWRITEBYTECODE=1','--env','PYTHONUNBUFFERED=1')
    if (-not $readOnlyState) { $result += @('--mount',('type=bind,source='+$script:manifest.artifacts+',target=/artifacts')) }
    return $result
}
function Create-Run {
    $version = (& git -C $source rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Committed source is required.' }
    $tree = (& git -C $source rev-parse 'HEAD^{tree}').Trim()
    $release = Join-Path $base ('releases/'+$version)
    if (-not (Test-Path -LiteralPath $release)) {
        $archive = Join-Path $base ('source-'+[guid]::NewGuid().ToString('N')+'.zip')
        & git -C $source archive --format=zip --output $archive $version
        if ($LASTEXITCODE -ne 0) { throw 'Committed source snapshot failed.' }
        Expand-Archive -LiteralPath $archive -DestinationPath $release
        Remove-Item -LiteralPath $archive
    }
    if (-not (Test-Path -LiteralPath (Join-Path $release 'examples/pentest/local_legion.py'))) { throw 'Commit the scenario before Start.' }
    $run = [guid]::NewGuid().ToString('N')
    $runRoot = Join-Path $base ('runs/'+$run)
    $state = Join-Path $runRoot 'state'
    $artifacts = Join-Path $runRoot 'artifacts'
    New-Item -ItemType Directory -Path $state,$artifacts -Force | Out-Null
    $script:manifest = @{ schema=1; owner=$script:owner; runId=$run; version=$version; tree=$tree;
        release=$release; state=$state; artifacts=$artifacts; port=$Port; stopped=$false }
    Save-Manifest
    @{ version=$version; tree=$tree; image=$pythonImage; adapter='mock' } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runRoot 'source.json') -Encoding utf8
    $prefix = 'sapper-local-'+$script:owner.Substring(0,8)+'-'+$run.Substring(0,8)
    $prepName = $prefix+'-prepare'
    $arguments = @(Container-Args $prepName 'none' $false) + @($pythonImage,'python','examples/pentest/local_legion.py','prepare','--state','/state','--artifacts','/artifacts')
    $id = Docker $arguments
    $script:manifest.prepare = @{name=$prepName;id=$id}; Save-Manifest
    Docker @('start','--attach',$id) | Set-Content -LiteralPath (Join-Path $artifacts 'prepare.log') -Encoding utf8
    $prepared = Inspect-Owned $script:manifest.prepare 'container'
    if ($prepared.State.ExitCode -ne 0) { throw 'Preparation failed; see private prepare.log.' }
}
function Start-Run {
    $prefix = 'sapper-local-'+$script:owner.Substring(0,8)+'-'+$script:manifest.runId.Substring(0,8)
    $networkName = $prefix+'-viewer-net'
    $network = Docker @('network','create','--driver','bridge','--label',('sapper.local.owner='+$script:owner),
        '--label',('sapper.local.run='+$script:manifest.runId),$networkName)
    $script:manifest.network = @{ name=$networkName;id=$network }; Save-Manifest
    $viewerName = $prefix+'-viewer'
    $arguments = @(Container-Args $viewerName $networkName $true) + @('--publish',('127.0.0.1:'+$script:manifest.port+':'+$script:manifest.port),
        $pythonImage,'python','lib/sapper.py','pentest','dashboard','--state','/state','--port',[string]$script:manifest.port,'--container-listen')
    $viewer = Docker $arguments
    $script:manifest.viewer = @{ name=$viewerName;id=$viewer }; Save-Manifest
    Docker @('start',$viewer) | Out-Null
    $url = $null
    for ($attempt=0; $attempt -lt 40; $attempt++) {
        $url = Viewer-Url
        if ($url) {
            try { $ready = Invoke-WebRequest -Uri $url.Split('#')[0] -TimeoutSec 2; if ($ready.StatusCode -eq 200) { break } } catch { $url=$null }
        }
        Start-Sleep -Milliseconds 250
    }
    if (-not $url) { throw '等待查看器就绪超时。' }
    # A restarted consumed run only reopens its viewer. Replay creates new state.
    if (-not (Test-Path -LiteralPath (Join-Path $script:manifest.state 'exercise-started.json'))) {
        $exerciseName = $prefix+'-exercise'
        $arguments = @(Container-Args $exerciseName 'none' $false) + @($pythonImage,'python','examples/pentest/local_legion.py',
            'exercise','--state','/state','--artifacts','/artifacts','--pace-seconds','2')
        $exercise = Docker $arguments
        $script:manifest.exercise = @{name=$exerciseName;id=$exercise}; Save-Manifest
        Docker @('start',$exercise) | Out-Null
    }
    $script:manifest.stopped=$false; Save-Manifest
    Write-Output $url
    if (-not $NoBrowser) { Start-Process $url }
    Show-Status
}
try {
    if (Test-Path -LiteralPath $ownerPath) { $script:owner = (Get-Content -LiteralPath $ownerPath -Raw).Trim() }
    else { $script:owner=[guid]::NewGuid().ToString('N'); Set-Content -LiteralPath $ownerPath -Value $script:owner -Encoding ascii }
    if ($script:owner -notmatch '^[0-9a-f]{32}$') { throw 'Invalid deployment owner marker.' }
    $script:manifest=$null
    if (Test-Path -LiteralPath $manifestPath) {
        $script:manifest=Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json -AsHashtable
        if ($script:manifest.owner -ne $script:owner) { throw 'Deployment owner mismatch.' }
    }
    switch ($Action) {
        'Status' { Show-Status }
        'Stop' { if ($script:manifest) { Stop-Owned }; Show-Status }
        'Open' {
            if (-not $script:manifest) { throw '请先使用 Start 启动本地部署。' }
            $url=Viewer-Url
            if (-not $url) { throw '查看器未运行，请使用 Start。' }
            Write-Output $url
            if (-not $NoBrowser) { Start-Process $url }
        }
        { $_ -in 'Start','Replay' } {
            try {
                if ($Action -eq 'Replay' -and $script:manifest) { Stop-Owned; $script:manifest=$null }
                if ($script:manifest -and (Viewer-Url)) {
                    $url=Viewer-Url; Write-Output $url
                    if (-not $NoBrowser) { Start-Process $url }
                    Show-Status
                } else {
                    if ($script:manifest) { Stop-Owned } else { Create-Run }
                    Start-Run
                }
            } catch {
                if ($script:manifest) { Stop-Owned }
                throw
            }
        }
    }
} finally { $lock.Dispose() }



