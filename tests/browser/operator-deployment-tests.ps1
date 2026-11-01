[CmdletBinding()]
param([switch]$Integration,[string]$HomeDirectory,[int]$Port=8877,
    [ValidateSet('None','Source','Exit')][string]$Regression='None')
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
if ($Regression -ne 'None') {
    Assert ([IO.Path]::IsPathFullyQualified($HomeDirectory) -and -not (Test-Path -LiteralPath $HomeDirectory)) 'Regression requires a new dedicated absolute home.'
    # All synthetic commits stay in this isolated checkout. Never move the user's HEAD.
    $checkout=Join-Path $scratch 'checkout'
    $null=& git clone --quiet --no-hardlinks $repo $checkout
    Assert ($LASTEXITCODE -eq 0) 'Isolated checkout failed.'
    Copy-Item -LiteralPath $scriptPath -Destination (Join-Path $checkout 'scripts/operator-workspace.ps1')
    $null=& git -C $checkout add scripts/operator-workspace.ps1
    $null=& git -C $checkout -c user.name=DeploymentRegression -c user.email=deployment-regression@example.invalid commit --quiet --allow-empty -m 'Synthetic controller under test'
    Assert ($LASTEXITCODE -eq 0) 'Synthetic controller commit failed.'
    $scriptPath=Join-Path $checkout 'scripts/operator-workspace.ps1'
    $good=(& git -C $checkout rev-parse HEAD).Trim()
    $r=Run Start $HomeDirectory @('-AcknowledgePreviousFailure')
    Assert ($r.code -ne 0 -and -not (Test-Path -LiteralPath $HomeDirectory)) 'Acknowledgment must refuse a fresh home without creating it.'
    $r=Run Start $HomeDirectory; Assert ($r.code -eq 0) $r.text
    $manifest=Join-Path $HomeDirectory 'deployment.json'
    $installed=Get-Content -Raw $manifest|ConvertFrom-Json
    $r=Run Start $HomeDirectory @('-AcknowledgePreviousFailure')
    Assert ($r.code -ne 0 -and (Get-Content -Raw $manifest|ConvertFrom-Json).container.id -eq $installed.container.id) 'Acknowledgment must refuse a running instance without replacing it.'
    $origin="http://127.0.0.1:$Port"
    function Regression-Login {
        $url=(Get-Content -Raw (Join-Path $HomeDirectory 'runtime/bootstrap.url')).Trim()
        $session=New-Object Microsoft.PowerShell.Commands.WebRequestSession
        $auth=Invoke-RestMethod -Uri "$origin/api/session" -Method Post -Headers @{Origin=$origin} -ContentType 'application/json' -Body (@{token=([uri]$url).Fragment.Substring(1)}|ConvertTo-Json -Compress) -WebSession $session
        return @{session=$session;headers=@{Origin=$origin;'X-Sapper-CSRF'=$auth.csrf_token}}
    }
    $auth=Regression-Login
    $preview=Invoke-RestMethod -Uri "$origin/api/assets/preview" -Method Post -Headers $auth.headers -WebSession $auth.session -ContentType 'application/json' -Body '{"text":"https://correction.invalid/","format":"lines"}'
    $task=Invoke-RestMethod -Uri "$origin/api/tasks" -Method Post -Headers $auth.headers -WebSession $auth.session -ContentType 'application/json' -Body (@{data=@{name='Synthetic correction persistence';goal='Save only';assets=$preview.preview.assets}}|ConvertTo-Json -Depth 16)
    $profile=Invoke-RestMethod -Uri "$origin/api/models" -Method Post -Headers $auth.headers -WebSession $auth.session -ContentType 'application/json' -Body '{"profile":{"name":"Synthetic correction never-call","provider":"custom","base_url":"https://model.correction.invalid/v1","model":"synthetic","api_key":"synthetic-correction-only"}}'
    if ($Regression -eq 'Source') {
        $r=Run Stop $HomeDirectory; Assert ($r.code -eq 0) $r.text
        $before=(Get-FileHash -LiteralPath $manifest).Hash
        $r=Run Start $HomeDirectory @('-AcknowledgePreviousFailure')
        Assert ($r.code -ne 0 -and (Get-FileHash -LiteralPath $manifest).Hash -eq $before) 'Acknowledgment must refuse a clean stop without changing metadata.'
        # Windows core.symlinks=false represents the unsupported Git mode as an ordinary file.
        $blob=('README.md'|& git -C $checkout hash-object -w --stdin).Trim()
        $null=& git -C $checkout update-index --add --cacheinfo "120000,$blob,deployment-test-link"
        $null=& git -C $checkout -c user.name=DeploymentRegression -c user.email=deployment-regression@example.invalid commit --quiet -m 'Synthetic unsupported source mode'
        $null=& git -C $checkout -c core.symlinks=false checkout-index -f -- deployment-test-link
        Assert ($LASTEXITCODE -eq 0 -and -not (& git -C $checkout status --porcelain --untracked-files=no)) 'Unsupported source fixture must be clean and committed.'
        Reject Start $HomeDirectory 'symlinks/submodules'
        Assert ((Get-FileHash -LiteralPath $manifest).Hash -eq $before) 'Rejected source changed installed metadata.'
        $r=Run Status $HomeDirectory; Assert ($r.code -eq 0) 'Rejected source stranded previous resources; Status must still work.'
        $r=Run Stop $HomeDirectory; Assert ($r.code -eq 0) 'Rejected source prevented subsequent Stop.'
        $null=& git -C $checkout checkout --quiet $good
        $r=Run Start $HomeDirectory; Assert ($r.code -eq 0) 'Corrected committed source could not restart preserved installation.'
    } else {
        # Only this newly created exact owned synthetic process is deliberately terminated.
        $r=Run Status $HomeDirectory; Assert ($r.code -eq 0) $r.text
        $probe=(& docker.exe inspect $installed.container.id|ConvertFrom-Json)[0]
        Assert ($probe.Id -eq $installed.container.id -and $probe.Config.Labels.'sapper.operator.home' -eq $HomeDirectory -and $probe.Config.Labels.'sapper.operator.owner' -eq $installed.owner) 'Synthetic kill ownership mismatch.'
        $null=& docker.exe kill --signal KILL $installed.container.id
        Assert ($LASTEXITCODE -eq 0) 'Synthetic forced termination failed.'
        $null=& docker.exe wait $installed.container.id
        $probe=(& docker.exe inspect $installed.container.id|ConvertFrom-Json)[0]
        Assert ($probe.State.ExitCode -eq 137 -and -not $probe.State.Running) 'Expected actual synthetic exit 137.'
        $r=Run Status $HomeDirectory
        $classified=Get-Content -Raw $manifest|ConvertFrom-Json
        $statusFailed=$r.code -ne 0 -and $classified.phase -eq 'unexpected_exit' -and $classified.lastFailure.exitCode -eq 137 -and -not $classified.lastFailure.oomKilled
        $r=Run Start $HomeDirectory
        Assert ($r.code -ne 0) 'Unacknowledged failed exit restarted silently.'
        $r=Run Stop $HomeDirectory
        Assert ($r.code -ne 0) 'Failed exit was relabeled as clean.'
        $r=Run Start $HomeDirectory @('-AcknowledgePreviousFailure')
        $recoverySucceeded=$r.code -eq 0
        if (-not $recoverySucceeded) {
            throw "Failure classification=$statusFailed; explicit recovery=$recoverySucceeded. Actual exit137 must surface attention and allow deliberate recovery."
        }
        Assert $statusFailed 'Unexpected stopped Status returned stale success or omitted exit diagnosis.'
        $current=Get-Content -Raw $manifest|ConvertFrom-Json
        Assert ($current.lastFailure.exitCode -eq 137 -and $current.lastFailure.generation -eq $installed.generation -and $current.lastFailure.acknowledgedAt -and $current.phase -eq 'ready') 'Recovery discarded or relabeled previous failure.'
        $history=Get-Content -Raw (Join-Path $HomeDirectory ('runtime/deployment-'+$installed.generation+'.json'))|ConvertFrom-Json
        Assert ($history.phase -ne 'stopped_clean' -and $history.lastFailure.exitCode -eq 137) 'Archived failed release was relabeled clean.'
    }
    $auth=Regression-Login
    $saved=Invoke-RestMethod -Uri "$origin/api/tasks/$($task.task.id)" -Headers $auth.headers -WebSession $auth.session
    $savedProfile=Invoke-RestMethod -Uri "$origin/api/models/$($profile.profile.id)" -Headers $auth.headers -WebSession $auth.session
    Assert ($saved.task.data.name -eq 'Synthetic correction persistence' -and @($saved.runs).Count -eq 0 -and $savedProfile.profile.has_key) 'Regression lost persisted draft/key or replayed work.'
    $current=Get-Content -Raw $manifest|ConvertFrom-Json
    Assert ($current.state -eq $installed.state -and $current.models -eq $installed.models) 'Regression moved state/models.'
    $countCode=@'
import json, sqlite3
from contextlib import closing
with closing(sqlite3.connect('file:/state/workspace.sqlite3?mode=ro',uri=True)) as db:
    counts={name:db.execute('SELECT count(*) FROM '+name).fetchone()[0] for name in ('drafts','runs','model_calls','messages')}
with closing(sqlite3.connect('file:/models/models.sqlite3?mode=ro',uri=True)) as db:
    counts['profiles']=db.execute('SELECT count(*) FROM profiles').fetchone()[0]
print(json.dumps(counts))
'@
    $counts=(& docker.exe exec $current.container.id python -c $countCode)|ConvertFrom-Json
    Assert ($LASTEXITCODE -eq 0 -and $counts.drafts -eq 1 -and $counts.profiles -eq 1 -and $counts.runs -eq 0 -and $counts.model_calls -eq 0 -and $counts.messages -eq 0) 'Regression changed records or made model calls.'
    $r=Run Stop $HomeDirectory; Assert ($r.code -eq 0) $r.text
    Write-Output "PASS $Regression correction regression; isolated committed source, draft/key persistence, zero runs, final clean Stop"
    exit
}
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
