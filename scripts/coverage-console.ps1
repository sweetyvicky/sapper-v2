[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$State,
    [ValidateRange(1, 65535)][int]$Port = 8765
)
$ErrorActionPreference = 'Stop'
if (-not [IO.Path]::IsPathFullyQualified($State)) { throw 'State must be an existing absolute directory.' }
$stateItem = Get-Item -LiteralPath $State
if (-not $stateItem.PSIsContainer) { throw 'State must be an existing directory.' }
$statePath = $stateItem.FullName
$sourcePath = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$networkName = 'sapper-viewer-' + [guid]::NewGuid().ToString('N')
$pythonImage = 'python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159'
$exitCode = 1
$created = $false
try {
    & docker network create --driver bridge $networkName | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the dedicated viewer network.' }
    $created = $true
    $dockerArgs = @('run', '--rm', '--network', $networkName, '--cpus', '2', '--memory', '512m',
        '--pids-limit', '128', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--read-only',
        '--tmpfs', '/tmp:rw,nosuid,nodev,size=128m', '--publish', "127.0.0.1:${Port}:${Port}",
        '--mount', "type=bind,source=$sourcePath,target=/src,readonly",
        '--mount', "type=bind,source=$statePath,target=/state,readonly",
        '--workdir', '/src', '--env', 'PYTHONDONTWRITEBYTECODE=1', $pythonImage,
        'python', 'lib/sapper.py', 'pentest', 'dashboard', '--state', '/state', '--port', "$Port", '--container-listen')
    Write-Host 'Read-only viewer. Open the complete fragment-capability URL printed below. Ctrl+C stops it.'
    Write-Host 'The Windows endpoint is loopback-only. This dedicated bridge container has network capability.'
    & docker @dockerArgs
    $exitCode = $LASTEXITCODE
}
finally {
    if ($created) { & docker network rm $networkName | Out-Null }
}
exit $exitCode
