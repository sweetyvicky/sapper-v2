[CmdletBinding()]
param(
    [ValidateSet('Start','Status','Open','Stop')][string]$Action='Status',
    [string]$HomeDirectory=(Join-Path $PSScriptRoot '../../operator-workspace'),
    [ValidateRange(1,65535)][int]$Port=8765,
    [switch]$NoBrowser,
    [switch]$AcknowledgePreviousFailure
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version 3
if ($AcknowledgePreviousFailure -and $Action -ne 'Start') { throw 'AcknowledgePreviousFailure is supported only on Start for an owned stopped failure.' }
$image='python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159'
$source=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if (-not $IsWindows) { throw 'Run this installer on Windows with PowerShell 7 and Linux Docker.' }
if (-not [IO.Path]::IsPathFullyQualified($HomeDirectory)) { throw 'HomeDirectory must be absolute.' }
$base=[IO.Path]::GetFullPath($HomeDirectory).TrimEnd('\','/')
if ($base -eq [IO.Path]::GetPathRoot($base).TrimEnd('\') -or $base -eq [Environment]::GetFolderPath('UserProfile')) { throw 'Use a dedicated installation home.' }
function Ordinary([string]$path) {
    $current=[IO.Path]::GetFullPath($path)
    while ($current) {
        if (Test-Path -LiteralPath $current) {
            $item=Get-Item -Force -LiteralPath $current
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Deployment reparse path refused.' }
        }
        $parent=[IO.Path]::GetDirectoryName($current)
        if ($parent -eq $current) { break }; $current=$parent
    }
}
function Tree-Ordinary([string]$path) {
    Ordinary $path
    foreach ($item in Get-ChildItem -Force -LiteralPath $path -Recurse) {
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Deployment reparse entry refused.' }
    }
}
Ordinary $base
$manifestPath=Join-Path $base 'deployment.json'
if (-not (Test-Path -LiteralPath $manifestPath)) {
    if ($AcknowledgePreviousFailure) { throw 'Acknowledgment requires an existing owned stopped failure.' }
    if ($Action -eq 'Status' -and -not (Test-Path -LiteralPath $base)) { '{"installed":false}'; return }
    if ($Action -ne 'Start') { throw 'No owned installation exists.' }
    if ((Test-Path -LiteralPath $base) -and @(Get-ChildItem -Force -LiteralPath $base).Count) { throw 'Fresh installation home must be empty.' }
}
$identity=[Security.Principal.WindowsIdentity]::GetCurrent().User
$allowed=@($identity.Value,'S-1-5-18','S-1-5-32-544')|Select-Object -Unique
function Protect-New([string]$path) {
    $acl=[Security.AccessControl.DirectorySecurity]::new()
    $acl.SetOwner($identity); $acl.SetAccessRuleProtection($true,$false)
    foreach ($sid in $allowed) {
        $rule=[Security.AccessControl.FileSystemAccessRule]::new([Security.Principal.SecurityIdentifier]::new($sid),'FullControl','ContainerInherit,ObjectInherit','None','Allow')
        $acl.AddAccessRule($rule)
    }
    Set-Acl -LiteralPath $path -AclObject $acl
}
function Verify-Private([string]$path) {
    foreach ($item in @((Get-Item -Force -LiteralPath $path))+@(Get-ChildItem -Force -Recurse -LiteralPath $path)) {
        $acl=Get-Acl -LiteralPath $item.FullName
        if ($acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -notin $allowed) { throw 'Private ACL owner mismatch.' }
        $seen=@()
        foreach ($rule in $acl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])) {
            if ($rule.IdentityReference.Value -notin $allowed -or $rule.AccessControlType -ne 'Allow') { throw 'Private ACL grants unexpected access.' }
            if (($rule.FileSystemRights -band [Security.AccessControl.FileSystemRights]::FullControl) -eq [Security.AccessControl.FileSystemRights]::FullControl) { $seen+=$rule.IdentityReference.Value }
        }
        foreach ($sid in $allowed) { if ($sid -notin $seen) { throw 'Private ACL required access missing.' } }
    }
}
function Docker([string[]]$arguments) {
    $output=& docker.exe @arguments 2>&1
    if ($LASTEXITCODE -ne 0) { throw 'Owned Docker operation failed; inspect private deployment diagnosis. No unrelated resources were changed.' }
    return ($output -join "`n").Trim()
}
function Save {
    $temp=Join-Path $base 'deployment.pending.json'
    $script:m|ConvertTo-Json -Depth 20|Set-Content -LiteralPath $temp -Encoding utf8
    Move-Item -LiteralPath $temp -Destination $manifestPath -Force
}
function Normalize([string]$path) { $path.Replace('\','/').TrimEnd('/').ToLowerInvariant() }
function Release-Valid($m=$script:m) {
    if ($m.schema -ne 1 -or $m.owner -notmatch '^[a-f0-9]{32}$' -or $m.home -ne $base -or $m.image -ne $image -or
        $m.state -ne (Join-Path $base 'state') -or $m.models -ne (Join-Path $base 'models') -or
        $m.release -ne (Join-Path $base ('releases/'+$m.generation)) -or $m.generation -notmatch '^[a-f0-9]{32}$' -or
        $m.version -notmatch '^[a-f0-9]{40}$' -or $m.tree -notmatch '^[a-f0-9]{40}$') { throw 'Installation ownership metadata mismatch.' }
    $proofPath=$m.release+'.integrity.json'
    if ((Get-FileHash -LiteralPath $proofPath -Algorithm SHA256).Hash -ne $m.inventoryHash) { throw 'Source integrity inventory mismatch.' }
    $proof=Get-Content -Raw -LiteralPath $proofPath|ConvertFrom-Json -AsHashtable
    if ($proof.version -ne $m.version -or $proof.tree -ne $m.tree) { throw 'Source integrity identity mismatch.' }
    $actual=@(Get-ChildItem -Force -Recurse -File -LiteralPath $m.release)
    if ($actual.Count -ne $proof.files.Count) { throw 'Source integrity file count mismatch.' }
    foreach ($file in $actual) {
        $rel=[IO.Path]::GetRelativePath($m.release,$file.FullName)
        if (-not $proof.files.ContainsKey($rel) -or (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash -ne $proof.files[$rel]) { throw 'Source integrity mismatch.' }
    }
}
function Label-Args([string]$role) {
    @('--label',"sapper.operator.owner=$($m.owner)",'--label',"sapper.operator.home=$base",'--label',"sapper.operator.generation=$($m.generation)",'--label',"sapper.operator.tree=$($m.tree)",'--label',"sapper.operator.role=$role")
}
function Labels-Valid($labels,[string]$role) {
    if ($labels.'sapper.operator.owner' -ne $m.owner -or $labels.'sapper.operator.home' -ne $base -or
        $labels.'sapper.operator.generation' -ne $m.generation -or $labels.'sapper.operator.tree' -ne $m.tree -or $labels.'sapper.operator.role' -ne $role) { throw 'Resource ownership labels mismatch.' }
}
function Command { @('python','-W','error::ResourceWarning','-m','pentest.workspace','--root','/state','--models-root','/models','--port',"$($m.port)",'--container-listen') }
function Inspect([string]$kind,$record) {
    $raw=& docker.exe $kind inspect $record.id 2>$null
    if ($LASTEXITCODE -ne 0) { throw 'Recorded owned resource missing; diagnosis retained.' }
    $item=@(($raw -join "`n"|ConvertFrom-Json -AsHashtable))[0]
    if ($item.Id -ne $record.id -or $item.Name.TrimStart('/') -ne $record.name) { throw 'Resource ownership ID/name mismatch.' }
    return $item
}
function Owned {
    Release-Valid
    $network=Inspect network $m.network; Labels-Valid $network.Labels 'network'
    if ($network.Driver -ne 'bridge' -or $network.Internal -or $network.EnableIPv6) { throw 'Owned bridge configuration mismatch.' }
    foreach ($key in $network.Options.Keys) {
        $expected=switch ($key) { 'com.docker.network.enable_ipv4' {'true'}; 'com.docker.network.enable_ipv6' {'false'}; default { throw 'Owned bridge option mismatch.' } }
        if ($network.Options[$key] -ne $expected) { throw 'Owned bridge option mismatch.' }
    }
    foreach ($id in $network.Containers.Keys) { if ($id -ne $m.container.id) { throw 'Unowned member on owned network.' } }
    $item=Inspect container $m.container; Labels-Valid $item.Config.Labels 'app'
    $h=$item.HostConfig
    if ($item.Config.Image -ne $image -or $h.Privileged -or -not $h.ReadonlyRootfs -or $h.NanoCpus -ne 2000000000 -or
        $h.Memory -ne 1073741824 -or $h.PidsLimit -ne 128 -or 'ALL' -notin $h.CapDrop -or 'no-new-privileges' -notin $h.SecurityOpt -or
        $h.Tmpfs.'/tmp' -ne 'rw,nosuid,nodev,size=128m' -or $h.NetworkMode -ne $m.network.name -or
        $h.RestartPolicy.Name -ne 'no' -or ($null -ne $h.Devices -and $h.Devices.Count -gt 0) -or ($null -ne $h.Binds -and $h.Binds.Count -gt 0) -or $item.Config.StopTimeout -ne 300 -or
        $item.Config.WorkingDir -ne '/src' -or ($item.Config.Cmd|ConvertTo-Json -Compress) -ne ((Command)|ConvertTo-Json -Compress)) { throw 'Owned container boundary mismatch.' }
    $mounts=@($item.Mounts)
    if ($mounts.Count -ne 3) { throw 'Owned mount count mismatch.' }
    foreach ($dest in @('/src','/state','/models')) {
        $mount=@($mounts|Where-Object Destination -eq $dest)
        $expected=switch ($dest) { '/src' {$m.release}; '/state' {$m.state}; '/models' {$m.models} }
        if ($mount.Count -ne 1 -or $mount[0].Type -ne 'bind' -or (Normalize $mount[0].Source) -ne (Normalize $expected) -or $mount[0].RW -ne ($dest -ne '/src')) { throw 'Owned mount boundary mismatch.' }
    }
    $ports=$h.PortBindings
    if (@($ports.Keys).Count -ne 1 -or -not $ports.ContainsKey("$($m.port)/tcp") -or @($ports["$($m.port)/tcp"]).Count -ne 1 -or
        $ports["$($m.port)/tcp"][0].HostIp -ne '127.0.0.1' -or $ports["$($m.port)/tcp"][0].HostPort -ne "$($m.port)") { throw 'Owned publication mismatch.' }
    if (@($item.NetworkSettings.Networks.Keys).Count -ne 1 -or -not $item.NetworkSettings.Networks.ContainsKey($m.network.name)) { throw 'Owned network attachment mismatch.' }
    if ($item.State.Running -and $item.NetworkSettings.Networks[$m.network.name].NetworkID -ne $m.network.id) { throw 'Owned network ID mismatch.' }
    return $item
}
function Ready {
    $item=Owned
    if (-not $item.State.Running) { throw 'Owned workspace is stopped.' }
    $logs=Docker @('logs',$m.container.id)
    $match=[regex]::Match($logs,('(?m)^http://127\.0\.0\.1:'+ $m.port +'/#[A-Za-z0-9_-]+\s*$'))
    if (-not $match.Success) { throw 'Workspace readiness bootstrap pending.' }
    $url=$match.Value.Trim(); $origin='http://127.0.0.1:'+$m.port
    $null=Invoke-WebRequest -Uri ($origin+'/') -TimeoutSec 3
    $auth=Invoke-RestMethod -Uri ($origin+'/api/session') -Method Post -Headers @{Origin=$origin} -ContentType 'application/json' -Body (@{token=([uri]$url).Fragment.Substring(1)}|ConvertTo-Json -Compress) -SessionVariable readySession -TimeoutSec 3
    if (-not $auth.ready) { throw 'Workspace authentication readiness failed.' }
    foreach ($route in @('/api/session','/api/tasks','/api/models')) { $null=Invoke-RestMethod -Uri ($origin+$route) -WebSession $readySession -TimeoutSec 3 }
    Set-Content -LiteralPath (Join-Path $base 'runtime/bootstrap.url') -Value $url -Encoding ascii
    if ($m.phase -in @('readiness_failed','readiness_pending')) { $m.phase='ready'; Save }
    return $url
}
function Show {
    $item=Owned
    $ready=$false
    if ($item.State.Running) {
        try { $null=Ready; $ready=$true } catch { $m.phase='readiness_failed'; $m.lastReadinessFailure=[DateTime]::UtcNow.ToString('o'); Save; throw 'Workspace readiness failed; private runtime diagnosis retained.' }
    }
    $failed=-not $item.State.Running -and ($m.phase -ne 'stopped_clean' -or $item.State.ExitCode -ne 0 -or $item.State.OOMKilled)
    if ($failed) { Record-Failure $item 'unexpected_exit' }
    @{installed=$true;version=$m.version;tree=$m.tree;running=[bool]$item.State.Running;ready=$ready;phase=$m.phase;
      exitCode=$item.State.ExitCode;oomKilled=[bool]$item.State.OOMKilled;lastFailure=$m['lastFailure'];state=$m.state;models=$m.models;url=('http://127.0.0.1:'+$m.port+'/');
      sourcePolicy='Running Start is idempotent. Stop then Start installs the current committed checkout.'}|ConvertTo-Json
    if ($failed) { throw 'Owned workspace unexpectedly stopped; failure diagnosis retained. Inspect Status, then deliberately Start -AcknowledgePreviousFailure to recover without replay.' }
}
function Record-Failure($item,[string]$phase) {
    if (-not $m['lastFailure'] -or $m.lastFailure.generation -ne $m.generation) {
        $m.lastFailure=@{generation=$m.generation;version=$m.version;tree=$m.tree;containerId=$m.container.id;
            exitCode=$item.State.ExitCode;oomKilled=[bool]$item.State.OOMKilled;observedAt=[DateTime]::UtcNow.ToString('o');reason=$phase}
    }
    # Keep the original diagnosis even when a subsequent Stop observes the same failed process.
    $m.phase=$phase; Save
    Docker @('logs',$m.container.id)|Set-Content -LiteralPath (Join-Path $base ('runtime/'+$m.generation+'.log')) -Encoding utf8
    $bootstrap=Join-Path $base 'runtime/bootstrap.url'; if (Test-Path -LiteralPath $bootstrap) { Remove-Item -LiteralPath $bootstrap }
}
function Check-Port([int]$number) {
    $listener=[Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback,$number)
    try { $listener.Start() } catch { throw 'Requested localhost port is already occupied; nothing was stopped.' } finally { $listener.Stop() }
}
function Snapshot {
    $dirty=& git -C $source status --porcelain --untracked-files=no
    if ($LASTEXITCODE -ne 0 -or $dirty) { throw 'Start requires a clean committed tracked checkout.' }
    $version=(& git -C $source rev-parse HEAD).Trim(); if ($LASTEXITCODE -ne 0) { throw 'Committed source required.' }
    $tree=(& git -C $source rev-parse ($version+'^{tree}')).Trim()
    $entries=& git -C $source ls-tree -r $version
    if ($LASTEXITCODE -ne 0 -or @($entries|Where-Object { $_ -match '^(120000|160000) ' }).Count) { throw 'Source symlinks/submodules refused.' }
    $generation=[guid]::NewGuid().ToString('N'); $release=Join-Path $base ('releases/'+$generation)
    $archive=Join-Path $base ('runtime/source-'+$generation+'.zip')
    & git -C $source archive --format=zip --output $archive $version
    if ($LASTEXITCODE -ne 0) { throw 'Committed archive failed.' }
    Expand-Archive -LiteralPath $archive -DestinationPath $release
    Tree-Ordinary $release
    $files=@{}
    foreach ($file in Get-ChildItem -Force -Recurse -File -LiteralPath $release) { $files[[IO.Path]::GetRelativePath($release,$file.FullName)]=(Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash }
    @{version=$version;tree=$tree;files=$files}|ConvertTo-Json -Depth 8|Set-Content -LiteralPath ($release+'.integrity.json') -Encoding utf8
    Remove-Item -LiteralPath $archive
    if ($script:m) { $owner=$m.owner } else { $owner=[guid]::NewGuid().ToString('N') }
    $prefix='sapper-operator-'+$owner.Substring(0,8)+'-'+$generation.Substring(0,8)
    $candidate=@{schema=1;owner=$owner;home=$base;image=$image;generation=$generation;version=$version;tree=$tree;release=$release;
        inventoryHash=(Get-FileHash -LiteralPath ($release+'.integrity.json') -Algorithm SHA256).Hash;
        state=(Join-Path $base 'state');models=(Join-Path $base 'models');port=$Port;phase='captured';
        network=@{name=$prefix+'-net';id=''};container=@{name=$prefix+'-app';id=''}}
    if ($script:m -and $m['lastFailure']) { $candidate.lastFailure=$m.lastFailure|ConvertTo-Json -Depth 10|ConvertFrom-Json -AsHashtable }
    Release-Valid $candidate
    return $candidate
}
function Stop-Owned {
    $item=Owned
    if ($item.State.Running) {
        $m.phase='stop_pending'; Save
        Write-Information 'Stopping: allowing up to 300 seconds for in-flight work and storage to drain.' -InformationAction Continue
        $null=Docker @('stop','--time','300',$m.container.id)
    }
    $item=Owned
    Docker @('logs',$m.container.id)|Set-Content -LiteralPath (Join-Path $base ('runtime/'+$m.generation+'.log')) -Encoding utf8
    if ($item.State.Running -or $item.State.ExitCode -ne 0 -or $item.State.OOMKilled -or
        ($m.phase -notin @('stop_pending','stopped_clean') -and $item.State.Status -ne 'created')) {
        Record-Failure $item 'stop_incomplete_or_forced'
        throw 'Owned workspace stop was incomplete, forced or unexpected; state and failure retained. Inspect Status, then deliberately Start -AcknowledgePreviousFailure to recover without replay.'
    }
    $m.phase='stopped_clean'; Save
    $bootstrap=Join-Path $base 'runtime/bootstrap.url'; if (Test-Path -LiteralPath $bootstrap) { Remove-Item -LiteralPath $bootstrap }
}
$lock=$null; $script:m=$null
try {
    if (-not (Test-Path -LiteralPath $manifestPath)) {
        # Validate prerequisites before creating private paths or capturing source.
        Check-Port $Port
        if ((Docker @('info','--format','{{.OSType}}')) -ne 'linux') { throw 'Linux Docker is required.' }
        $dirty=& git -C $source status --porcelain --untracked-files=no
        if ($LASTEXITCODE -ne 0 -or $dirty) { throw 'Start requires a clean committed tracked checkout.' }
        $null=New-Item -ItemType Directory -Force -Path $base; Protect-New $base
        foreach ($dir in @('state','models','runtime','releases')) { $null=New-Item -ItemType Directory -Path (Join-Path $base $dir) }
    }
    Tree-Ordinary $base; Verify-Private $base
    $lock=[IO.File]::Open((Join-Path $base 'operation.lock'),'OpenOrCreate','ReadWrite','None')
    if (Test-Path -LiteralPath $manifestPath) { $script:m=Get-Content -Raw -LiteralPath $manifestPath|ConvertFrom-Json -AsHashtable; $null=Owned }
    switch ($Action) {
        'Status' { Show }
        'Stop' { Stop-Owned; Show }
        'Open' { $url=Ready; if (-not $NoBrowser) { Start-Process $url }; @{opened=(-not $NoBrowser);ready=$true;url=('http://127.0.0.1:'+$m.port+'/')}|ConvertTo-Json }
        'Start' {
            if ($m -and (Owned).State.Running) {
                if ($AcknowledgePreviousFailure) { throw 'Acknowledgment requires an owned stopped failure; running deployment was not changed.' }
                $url=Ready; if (-not $NoBrowser) { Start-Process $url }; Show; break
            }
            Check-Port $Port
            $dirty=& git -C $source status --porcelain --untracked-files=no
            if ($LASTEXITCODE -ne 0 -or $dirty) { throw 'Start requires a clean committed tracked checkout.' }
            if ($m) {
                $item=Owned
                if ($m.phase -ne 'stopped_clean' -or $item.State.ExitCode -ne 0 -or $item.State.OOMKilled) {
                    Record-Failure $item 'unexpected_exit'
                    if (-not $AcknowledgePreviousFailure) { throw 'Previous deployment did not stop cleanly. Inspect Status, then deliberately Start -AcknowledgePreviousFailure; no work is replayed.' }
                } elseif ($AcknowledgePreviousFailure) { throw 'No current failed exit to acknowledge; use normal Start after a clean Stop.' }
            } elseif ($AcknowledgePreviousFailure) { throw 'Acknowledgment requires an existing owned stopped failure.' }
            # Capture and verify the entire candidate before changing the installed manifest/resources.
            $candidate=Snapshot
            if ($m) {
                $null=Owned
                if ($AcknowledgePreviousFailure) {
                    $m.lastFailure.acknowledgedAt=[DateTime]::UtcNow.ToString('o')
                    $candidate.lastFailure=$m.lastFailure|ConvertTo-Json -Depth 10|ConvertFrom-Json -AsHashtable
                }
                $m|ConvertTo-Json -Depth 20|Set-Content -LiteralPath (Join-Path $base ('runtime/deployment-'+$m.generation+'.json')) -Encoding utf8
                # Resource creation/removal failures after this boundary retain metadata for diagnosis.
                $null=Docker @('rm',$m.container.id); $null=Docker @('network','rm',$m.network.id)
            }
            $script:m=$candidate; Save
            $m.network.id=Docker (@('network','create','--driver','bridge')+(Label-Args 'network')+@($m.network.name)); $m.phase='network_created'; Save
            $args=@('create','--name',$m.container.name,'--network',$m.network.name,'--cpus','2','--memory','1g','--pids-limit','128',
                '--cap-drop','ALL','--security-opt','no-new-privileges','--read-only','--stop-timeout','300','--tmpfs','/tmp:rw,nosuid,nodev,size=128m',
                '--publish',"127.0.0.1:$($m.port):$($m.port)",'--mount',"type=bind,source=$($m.release),target=/src,readonly",'--mount',"type=bind,source=$($m.state),target=/state",
                '--mount',"type=bind,source=$($m.models),target=/models",'--workdir','/src','--env','PYTHONPATH=/src/lib','--env','PYTHONDONTWRITEBYTECODE=1','--env','PYTHONUNBUFFERED=1')
            $m.container.id=Docker ($args+(Label-Args 'app')+@($image)+(Command)); $m.phase='created'; Save
            $null=Owned; $null=Docker @('start',$m.container.id); $m.phase='readiness_pending'; Save
            $url=$null; $deadline=[DateTime]::UtcNow.AddSeconds(45)
            do { try { $url=Ready; break } catch { Start-Sleep -Milliseconds 300 } } while ([DateTime]::UtcNow -lt $deadline)
            if (-not $url) { $m.phase='readiness_failed'; Save; throw 'Workspace readiness failed; owned resources and private diagnosis retained.' }
            $m.phase='ready'; Save
            if (-not $NoBrowser) { Start-Process $url }; Show
        }
    }
} finally { if ($lock) { $lock.Dispose() } }
