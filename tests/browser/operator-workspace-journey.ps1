<# Run one real-browser journey against the owned synthetic fixture. No fetch mocking. #>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$FixtureHome,
    [Parameter(Mandatory)][ValidateSet('Bootstrap','Rebootstrap','Models','Task','GuidanceQueued','Approve','Finding','ReviewCoverage','Invalidate','Reports','SlowTask','Pause','NextRound','Cancel','RoleGuidancePrepare','ModelRecovery','ActiveRestartPrepare','StateSmoke')][string]$Stage,
    [ValidatePattern('^[a-z0-9_-]{1,64}$')][string]$Session = 'operator-workspace-test'
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
Set-Location -LiteralPath $repo
if (-not (Get-Command npx -ErrorAction SilentlyContinue)) { throw 'Node.js/npm (npx) is required.' }
$null = New-Item -ItemType Directory -Force '.superpowers/operator/ui-validation'
$log = Join-Path $repo ".superpowers/operator/ui-validation/runner-$Session-$Stage-private.log"
$files = @{
 Models='models'; Task='task'; GuidanceQueued='guidance'; Approve='approve'; Finding='finding';
 ReviewCoverage='review-coverage'; Invalidate='invalidate'; Reports='reports'; SlowTask='slow-task';
 Pause='pause'; NextRound='next-round'; Cancel='cancel'; RoleGuidancePrepare='role-guidance-prepare';
 ModelRecovery='model-recovery'; ActiveRestartPrepare='active-restart-prepare'; StateSmoke='state-smoke'
}
$arguments = @('--yes','--package','@playwright/cli@0.1.23','playwright-cli',"-s=$Session")
if ($Stage -in @('Bootstrap','Rebootstrap')) {
    & (Join-Path $PSScriptRoot 'operator-workspace-fixture.ps1') -Action Status -FixtureHome $FixtureHome
    if ($LASTEXITCODE -ne 0) { throw 'Owned fixture status failed.' }
    $bootstrapPath = Join-Path $FixtureHome 'state/fixture/bootstrap.url'
    $bootstrapUrl = (Get-Content -LiteralPath $bootstrapPath -Raw).Trim()
    $operation = if ($Stage -eq 'Bootstrap') { 'open' } else { 'goto' }
    $arguments += @($operation,$bootstrapUrl)
    if ($Stage -eq 'Bootstrap') { $arguments += '--headed' }
} else {
    $file = Join-Path $PSScriptRoot ('operator-workspace-'+$files[$Stage]+'.js')
    $arguments += @('run-code','--filename',$file)
}
# CLI prints the invoked bootstrap URL and synthetic form text: always private.
$result = & npx @arguments 2>&1
$result | Set-Content -LiteralPath $log -Encoding utf8
if ($LASTEXITCODE -ne 0 -or (($result -join "`n") -match '### Error')) {
    throw "Browser journey $Stage failed; see its ignored private log."
}
Write-Output "PASS browser stage $Stage (real UI; synthetic fixture only)."
