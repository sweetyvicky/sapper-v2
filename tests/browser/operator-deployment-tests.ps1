[CmdletBinding()]
param([switch]$Integration,[string]$HomeDirectory,[int]$Port=8877)
$ErrorActionPreference='Stop'
$scriptPath=Join-Path $PSScriptRoot '../../scripts/operator-workspace.ps1'
$pwsh=(Get-Command pwsh).Source
function Assert($condition,$message) { if (-not $condition) { throw $message } }
function Run($action,$homePath,$extra=@()) {
    $output=& $pwsh -NoProfile -File $scriptPath -Action $action -HomeDirectory $homePath -Port $Port -NoBrowser @extra 2>&1
    return @{code=$LASTEXITCODE;text=($output -join "`n")}
}
function Reject($action,$homePath,$reason) { $r=Run $action $homePath; Assert ($r.code -ne 0 -and $r.text.Contains($reason)) "Expected $reason rejection; got $($r.text)" }
Assert (Test-Path -LiteralPath $scriptPath) 'Deployment entry is missing.'
$repo=(Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$scratch=Join-Path $repo ('.superpowers/operator/deployment-tests-'+[guid]::NewGuid().ToString('N'))
$null=New-Item -ItemType Directory -Path $scratch
$absent=Join-Path $scratch 'absent'
$r=Run Status $absent; Assert ($r.code -eq 0 -and (($r.text|ConvertFrom-Json).installed -eq $false)) 'Absent Status must be side effect free.'
Assert (-not (Test-Path -LiteralPath $absent)) 'Status created an installation.'
$foreign=Join-Path $scratch 'foreign'; $null=New-Item -ItemType Directory -Path $foreign
Set-Content -LiteralPath (Join-Path $foreign 'keep.txt') -Value 'unowned'
Reject Start $foreign 'empty'; Assert ((Get-Content (Join-Path $foreign 'keep.txt')) -eq 'unowned') 'Foreign data changed.'
Reject Start $scratch 'empty'
$junction=Join-Path $scratch 'junction'; $null=New-Item -ItemType Junction -Path $junction -Target $foreign
Reject Status $junction 'reparse'
Write-Output 'PASS absent status, foreign home refusal, reparse refusal'
if (-not $Integration) { exit }
Assert ([IO.Path]::IsPathFullyQualified($HomeDirectory)) 'Integration requires an explicit absolute dedicated HomeDirectory.'
$r=Run Start $HomeDirectory; Assert ($r.code -eq 0) $r.text
$m=Get-Content -Raw (Join-Path $HomeDirectory 'deployment.json')|ConvertFrom-Json
$initial=$m.container.id; $release=$m.release
$privateAcl=Get-Acl -LiteralPath (Join-Path $HomeDirectory 'models')
try {
    $changed=Get-Acl -LiteralPath (Join-Path $HomeDirectory 'models')
    $changed.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new([Security.Principal.SecurityIdentifier]::new('S-1-1-0'),'Read','ContainerInherit,ObjectInherit','None','Allow'))
    Set-Acl -LiteralPath (Join-Path $HomeDirectory 'models') -AclObject $changed
    Reject Status $HomeDirectory 'ACL'
} finally { Set-Acl -LiteralPath (Join-Path $HomeDirectory 'models') -AclObject $privateAcl }
$r=Run Start $HomeDirectory; Assert ($r.code -eq 0) $r.text
$m=Get-Content -Raw (Join-Path $HomeDirectory 'deployment.json')|ConvertFrom-Json
Assert ($m.container.id -eq $initial -and $m.release -eq $release) 'Start replaced running deployment.'
$r=Run Open $HomeDirectory; Assert ($r.code -eq 0 -and $r.text -notmatch '#[A-Za-z0-9_-]{20}') 'Open leaked bootstrap.'
# Running is insufficient: an unresponsive owned process must fail readiness visibly.
$null=& docker.exe pause $initial
Assert ($LASTEXITCODE -eq 0) 'Could not pause owned acceptance container.'
try { Reject Status $HomeDirectory 'readiness' }
finally { $null=& docker.exe unpause $initial }
$r=Run Status $HomeDirectory; Assert ($r.code -eq 0) $r.text
$recovered=$r.text|ConvertFrom-Json
Assert ($recovered.ready -and $recovered.phase -eq 'ready') 'Recovered readiness must clear failed phase.'
# Exact release integrity is checked even for Stop; preserve and restore deliberate corruption.
$file=Join-Path $release 'README.md'; $before=[IO.File]::ReadAllBytes($file)
try { [IO.File]::AppendAllText($file,'tampered'); Reject Status $HomeDirectory 'integrity'; Reject Stop $HomeDirectory 'integrity' }
finally { [IO.File]::WriteAllBytes($file,$before) }
# Altering a recorded ID to an unrelated container must never act on it.
$manifest=Join-Path $HomeDirectory 'deployment.json'; $original=[IO.File]::ReadAllBytes($manifest)
try { $m.container.id='f'*64; $m|ConvertTo-Json -Depth 16|Set-Content $manifest; Reject Stop $HomeDirectory 'owned' }
finally { [IO.File]::WriteAllBytes($manifest,$original) }
# A real unrelated stopped container must remain untouched despite a forged record.
$foreignName='sapper-deployment-negative-'+[guid]::NewGuid().ToString('N')
$foreignId=(& docker.exe create --name $foreignName --network none --label 'sapper.deployment.test=negative' $m.image python -c 'pass').Trim()
Assert ($LASTEXITCODE -eq 0) 'Negative fixture creation failed.'
try {
    $m.container=@{id=$foreignId;name=$foreignName}
    $m|ConvertTo-Json -Depth 16|Set-Content $manifest
    Reject Stop $HomeDirectory 'owned'
    $probe=(& docker.exe inspect $foreignId|ConvertFrom-Json)[0]
    Assert ($probe.Id -eq $foreignId -and $probe.State.Status -eq 'created') 'Unrelated resource changed.'
} finally {
    [IO.File]::WriteAllBytes($manifest,$original)
    $probe=(& docker.exe inspect $foreignId|ConvertFrom-Json)[0]
    if ($probe.Id -ne $foreignId -or $probe.Name -ne ('/'+$foreignName) -or $probe.Config.Labels.'sapper.deployment.test' -ne 'negative') { throw 'Negative fixture ownership mismatch.' }
    $null=& docker.exe rm $foreignId
}
$origin="http://127.0.0.1:$Port"
function Login {
    $url=(Get-Content -Raw (Join-Path $HomeDirectory 'runtime/bootstrap.url')).Trim()
    $token=([uri]$url).Fragment.Substring(1)
    $session=New-Object Microsoft.PowerShell.Commands.WebRequestSession
    $auth=Invoke-RestMethod -Uri "$origin/api/session" -Method Post -Headers @{Origin=$origin} -ContentType 'application/json' -Body (@{token=$token}|ConvertTo-Json -Compress) -WebSession $session
    return @{session=$session;headers=@{Origin=$origin;'X-Sapper-CSRF'=$auth.csrf_token}}
}
$auth=Login
$preview=Invoke-RestMethod -Uri "$origin/api/assets/preview" -Method Post -Headers $auth.headers -WebSession $auth.session -ContentType 'application/json' -Body '{"text":"https://acceptance.invalid/","format":"lines"}'
$data=@{name='Synthetic deployment persistence';goal='Save only; do not prepare or request this asset';assets=$preview.preview.assets}
$task=Invoke-RestMethod -Uri "$origin/api/tasks" -Method Post -Headers $auth.headers -WebSession $auth.session -ContentType 'application/json' -Body (@{data=$data}|ConvertTo-Json -Depth 16)
# Synthetic key is deliberately never sent to a provider. Verify existence/metadata only.
$profile=Invoke-RestMethod -Uri "$origin/api/models" -Method Post -Headers $auth.headers -WebSession $auth.session -ContentType 'application/json' -Body '{"profile":{"name":"Synthetic never-call profile","provider":"custom","base_url":"https://model.acceptance.invalid/v1","model":"synthetic","api_key":"synthetic-deployment-acceptance-only"}}'
$r=Run Stop $HomeDirectory; Assert ($r.code -eq 0) $r.text
$r=Run Status $HomeDirectory; Assert ($r.code -eq 0 -and -not ($r.text|ConvertFrom-Json).running) 'Stopped status wrong.'
$listener=[Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback,$Port)
try { $listener.Start(); Reject Start $HomeDirectory 'port' } finally { $listener.Stop() }
$r=Run Start $HomeDirectory; Assert ($r.code -eq 0) $r.text
$auth=Login
$saved=Invoke-RestMethod -Uri "$origin/api/tasks/$($task.task.id)" -Headers $auth.headers -WebSession $auth.session
Assert ($saved.task.data.name -eq $data.name -and @($saved.runs).Count -eq 0) 'Draft persistence or no-replay failed.'
$savedProfile=Invoke-RestMethod -Uri "$origin/api/models/$($profile.profile.id)" -Headers $auth.headers -WebSession $auth.session
Assert ($savedProfile.profile.has_key) 'Synthetic key did not persist.'
$m=Get-Content -Raw $manifest|ConvertFrom-Json
Assert ($m.state -eq (Join-Path $HomeDirectory 'state') -and $m.models -eq (Join-Path $HomeDirectory 'models')) 'Persistent paths changed.'
Write-Output 'PASS real start/idempotence/open/source mismatch/ownership refusal/stop/port collision/restart/task and synthetic key persistence; zero run preparation or provider tests'
