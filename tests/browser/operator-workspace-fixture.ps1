[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidateSet('Start','Status','Stop','Restart','Arm','Release','FailNext')][string]$Action,
    [Parameter(Mandatory)][string]$FixtureHome,
    [ValidateRange(1,65535)][int]$Port=8876,
    [ValidateSet('probe','plan','analyze','guidance','review')][string]$Purpose
)
$ErrorActionPreference='Stop'
$image='python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159'
$source=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).Path
if (-not [IO.Path]::IsPathFullyQualified($FixtureHome)) { throw 'FixtureHome must be absolute.' }
$homePath=[IO.Path]::GetFullPath($FixtureHome).TrimEnd('\','/')
if ($homePath -eq [IO.Path]::GetPathRoot($homePath)) { throw 'Use a dedicated fixture directory.' }
if ($Port -eq 8765) { throw 'Port 8765 is reserved.' }
if (($Action -eq 'FailNext') -ne [bool]$Purpose) { throw 'Purpose is required only with FailNext.' }
function Docker([string[]]$Arguments) {
    $result=& docker.exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw 'Owned fixture Docker operation failed.' }
    return $result
}
function Normalize([string]$Path) { return $Path.Replace('\','/').TrimEnd('/').ToLowerInvariant() }
function Save-Owner { $owner | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifest -Encoding utf8 }
function Labels([string]$Role) {
    return @('--label',"sapper.fixture.owner=$($owner.owner)",'--label',"sapper.fixture.home=$homePath",'--label',"sapper.fixture.source=$source",'--label',"sapper.fixture.role=$Role")
}
function Verify-Labels($Resource,[string]$Role) {
    $labels=if ($Resource.Config) { $Resource.Config.Labels } else { $Resource.Labels }
    if ($labels.'sapper.fixture.owner' -ne $owner.owner -or $labels.'sapper.fixture.home' -ne $homePath -or
        $labels.'sapper.fixture.source' -ne $source -or $labels.'sapper.fixture.role' -ne $Role) { throw 'Fixture ownership labels do not match.' }
}
function Verify-Network($Record,[string]$Role,[bool]$Internal) {
    $network=(Docker @('network','inspect',$Record.id) | ConvertFrom-Json)[0]
    Verify-Labels $network $Role
    if ($network.Id -ne $Record.id -or $network.Name -ne $Record.name -or $network.Driver -ne 'bridge' -or $network.Internal -ne $Internal) { throw 'Fixture network boundary mismatch.' }
    $allowed=@($owner.app.id,$owner.relay.id)
    foreach ($member in $network.Containers.PSObject.Properties) {
        if ($member.Name -notin $allowed) { throw 'Unowned member on fixture network.' }
    }
}
function Verify-Container($Record,[string]$Role) {
    $container=(Docker @('inspect',$Record.id) | ConvertFrom-Json)[0]
    Verify-Labels $container $Role
    $relay=$Role -eq 'relay'
    $cpu=if ($relay) { 500000000 } else { 2000000000 }
    $memory=if ($relay) { 134217728 } else { 1073741824 }
    $pids=if ($relay) { 64 } else { 128 }
    if ($container.Id -ne $Record.id -or $container.Name -ne ('/'+$Record.name) -or $container.Config.Image -ne $image -or
        $container.HostConfig.Privileged -or -not $container.HostConfig.ReadonlyRootfs -or $container.HostConfig.NanoCpus -ne $cpu -or
        $container.HostConfig.Memory -ne $memory -or $container.HostConfig.PidsLimit -ne $pids -or
        'ALL' -notin $container.HostConfig.CapDrop -or 'no-new-privileges' -notin $container.HostConfig.SecurityOpt -or
        $container.HostConfig.Tmpfs.'/tmp' -ne 'rw,nosuid,nodev,size=128m') { throw 'Container ownership/resource boundary mismatch.' }
    $mounts=@($container.Mounts)
    if ($relay) {
        if ($mounts.Count -ne 1 -or $mounts[0].Destination -ne '/relay.py' -or $mounts[0].RW -or
            (Normalize $mounts[0].Source) -ne (Normalize (Join-Path $PSScriptRoot 'operator_fixture_relay.py'))) { throw 'Relay mount mismatch.' }
        $command=@('python','-W','error::ResourceWarning','/relay.py','--peer',$owner.peer,'--port',$owner.port.ToString())
    } else {
        $src=@($mounts | Where-Object Destination -eq '/src'); $state=@($mounts | Where-Object Destination -eq '/state')
        if ($mounts.Count -ne 2 -or $src.Count -ne 1 -or $state.Count -ne 1 -or $src[0].RW -or -not $state[0].RW -or
            (Normalize $src[0].Source) -ne (Normalize $source) -or (Normalize $state[0].Source) -ne (Normalize (Join-Path $homePath 'state'))) { throw 'App mount mismatch.' }
        $command=@('python','-W','error::ResourceWarning','tests/browser/operator_workspace_fixture.py','--home','/state','--port',$owner.port.ToString(),'--container-listen')
    }
    if (($container.Config.Cmd|ConvertTo-Json -Compress) -ne ($command|ConvertTo-Json -Compress)) { throw 'Fixture entry command mismatch.' }
    $bindings=@($container.HostConfig.PortBindings.PSObject.Properties)
    if ($relay) {
        if ($bindings.Count -ne 1 -or $bindings[0].Name -ne ($owner.port.ToString()+'/tcp') -or @($bindings[0].Value).Count -ne 1 -or
            $bindings[0].Value[0].HostIp -ne '127.0.0.1' -or $bindings[0].Value[0].HostPort -ne $owner.port.ToString()) { throw 'Relay publication mismatch.' }
    } elseif ($bindings.Count) { throw 'App must not publish ports.' }
    $networks=@($container.NetworkSettings.Networks.PSObject.Properties)
    $expected=if ($relay) { @($owner.internal.name,$owner.ingress.name) } else { @($owner.internal.name) }
    if ($networks.Count -ne $expected.Count -or @($networks.Name | Where-Object { $_ -notin $expected }).Count) { throw 'Fixture network attachment mismatch.' }
    foreach ($attachment in $networks) {
        $id=if ($attachment.Name -eq $owner.internal.name) { $owner.internal.id } else { $owner.ingress.id }
        if ($container.State.Running -and $attachment.Value.NetworkID -ne $id) { throw 'Fixture network ID mismatch.' }
    }
    if (-not $relay -and $container.State.Running -and $container.NetworkSettings.Networks.($owner.internal.name).IPAddress -ne $owner.peer) { throw 'App numeric peer mismatch.' }
    return $container
}
function Verify-Owned {
    if ($owner.version -ne 2 -or $owner.home -ne $homePath -or $owner.source -ne $source -or $owner.image -ne $image -or $owner.port -eq 8765) { throw 'Fixture manifest does not match this home/source/image.' }
    Verify-Network $owner.internal 'internal' $true
    Verify-Network $owner.ingress 'ingress' $false
    $null=Verify-Container $owner.app 'app'
    $null=Verify-Container $owner.relay 'relay'
}
function Assert-Ready {
    $origin='http://127.0.0.1:'+$owner.port; $fixturePath=Join-Path $homePath 'state/fixture'
    $deadline=[DateTime]::UtcNow.AddSeconds(30)
    do {
        $app=Verify-Container $owner.app 'app'; $relay=Verify-Container $owner.relay 'relay'
        if (-not $app.State.Running -or -not $relay.State.Running) { throw 'Owned fixture is not running.' }
        $readyPath=Join-Path $fixturePath 'ready.json'
        if (Test-Path -LiteralPath $readyPath) {
            $metadata=Get-Content -Raw -LiteralPath (Join-Path $fixturePath 'metadata.json') | ConvertFrom-Json
            $ready=Get-Content -Raw -LiteralPath $readyPath | ConvertFrom-Json
            if ($ready.generation -eq $metadata.generation -and $ready.authenticated -and $ready.inert) {
                $bootstrap=Get-Content -Raw -LiteralPath (Join-Path $fixturePath 'bootstrap.url')
                $token=([uri]$bootstrap).Fragment.Substring(1)
                $null=Invoke-RestMethod -Uri ($origin+'/api/session') -Method Post -Headers @{Origin=$origin} -ContentType 'application/json' -Body (@{token=$token}|ConvertTo-Json -Compress) -SessionVariable fixtureSession
                foreach ($route in @('/api/session','/api/models','/api/tasks')) { $null=Invoke-RestMethod -Uri ($origin+$route) -WebSession $fixtureSession }
                $after=Get-Content -Raw -LiteralPath (Join-Path $fixturePath 'metadata.json') | ConvertFrom-Json
                if (($metadata.counts|ConvertTo-Json -Compress) -ne ($after.counts|ConvertTo-Json -Compress)) { throw 'Readiness caused unexpected calls.' }
                return
            }
        }
        Start-Sleep -Milliseconds 150
    } while ([DateTime]::UtcNow -lt $deadline)
    throw 'Owned fixture readiness timed out.'
}
function Stop-Owned {
    foreach ($record in @($owner.relay,$owner.app)) {
        $role=if ($record.id -eq $owner.app.id) { 'app' } else { 'relay' }
        $container=Verify-Container $record $role
        if ($container.State.Running) { $null=Docker @('stop','--time','300',$record.id) }
        $container=Verify-Container $record $role
        if ($container.State.Running -or $container.State.ExitCode -ne 0) { throw 'Fixture did not stop cleanly; state retained for inspection.' }
    }
}
if ((Docker @('version','--format','{{.Server.Os}}')).Trim() -ne 'linux') { throw 'Linux Docker is required.' }
$manifest=Join-Path $homePath 'fixture-owner.json'
if (-not (Test-Path -LiteralPath $manifest)) {
    if ($Action -ne 'Start') { throw 'No fixture ownership manifest exists.' }
    if ((Test-Path -LiteralPath $homePath) -and @(Get-ChildItem -Force -LiteralPath $homePath).Count) { throw 'Fresh home must be empty; existing data is never reset.' }
    $listener=[Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback,$Port)
    try { $listener.Start() } finally { $listener.Stop() }
    $null=New-Item -ItemType Directory -Force -Path (Join-Path $homePath 'state')
    $id=[guid]::NewGuid().ToString('N'); $name='sapper-operator-fixture-'+$id.Substring(0,12)
    $owner=[pscustomobject]@{version=2;owner=$id;home=$homePath;source=$source;image=$image;port=$Port;peer='';
        internal=@{name=$name+'-internal';id=''};ingress=@{name=$name+'-ingress';id=''};app=@{name=$name+'-app';id=''};relay=@{name=$name+'-relay';id=''}}
    $owner.internal.id=(Docker (@('network','create','--internal','--driver','bridge')+(Labels 'internal')+@($owner.internal.name))).Trim(); Save-Owner
    $owner.ingress.id=(Docker (@('network','create','--driver','bridge')+(Labels 'ingress')+@($owner.ingress.name))).Trim(); Save-Owner
    $network=(Docker @('network','inspect',$owner.internal.id)|ConvertFrom-Json)[0]
    $bytes=[Net.IPAddress]::Parse($network.IPAM.Config[0].Gateway).GetAddressBytes(); $bytes[3]++
    $owner.peer=([Net.IPAddress]::new($bytes)).ToString(); Save-Owner
    $common=@('--cap-drop','ALL','--security-opt','no-new-privileges','--read-only','--stop-timeout','300','--tmpfs','/tmp:rw,nosuid,nodev,size=128m','--env','PYTHONDONTWRITEBYTECODE=1')
    $args=@('create','--name',$owner.app.name,'--network',$owner.internal.name,'--ip',$owner.peer,'--cpus','2','--memory','1g','--pids-limit','128')+$common+(Labels 'app')+@(
        '--mount',"type=bind,source=$source,target=/src,readonly",'--mount',"type=bind,source=$(Join-Path $homePath 'state'),target=/state",'--workdir','/src',
        $image,'python','-W','error::ResourceWarning','tests/browser/operator_workspace_fixture.py','--home','/state','--port',"$Port",'--container-listen')
    $owner.app.id=(Docker $args).Trim(); Save-Owner
    $args=@('create','--name',$owner.relay.name,'--network',$owner.ingress.name,'--network',$owner.internal.name,'--cpus','0.5','--memory','128m','--pids-limit','64')+$common+(Labels 'relay')+@(
        '--publish',"127.0.0.1:${Port}:${Port}",'--mount',"type=bind,source=$(Join-Path $PSScriptRoot 'operator_fixture_relay.py'),target=/relay.py,readonly",
        $image,'python','-W','error::ResourceWarning','/relay.py','--peer',$owner.peer,'--port',"$Port")
    $owner.relay.id=(Docker $args).Trim(); Save-Owner
} else { $owner=Get-Content -Raw -LiteralPath $manifest | ConvertFrom-Json }
Verify-Owned
switch ($Action) {
    'Stop' { Stop-Owned }
    'Restart' {
        Stop-Owned
        $null=Docker @('start',$owner.app.id); $null=Docker @('start',$owner.relay.id); Assert-Ready
    }
    'Start' {
        foreach ($record in @($owner.app,$owner.relay)) {
            $container=(Docker @('inspect',$record.id)|ConvertFrom-Json)[0]
            if (-not $container.State.Running) { $null=Docker @('start',$record.id) }
        }
        Assert-Ready
    }
    'Status' { Assert-Ready }
    default {
        Assert-Ready
        $command=@{Arm='arm';Release='release';FailNext='fail_next'}[$Action]
        $controlArgs=@('exec',$owner.app.id,'python','tests/browser/operator_workspace_fixture.py','--home','/state','--control',$command)
        if ($Purpose) { $controlArgs+=@('--purpose',$Purpose) }
        $null=Docker $controlArgs
    }
}
Write-Output ('Owned synthetic fixture '+$Action+': http://127.0.0.1:'+$owner.port)
