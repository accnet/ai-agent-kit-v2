<# Install this nested AI-Kit into its parent project directory. #>
[CmdletBinding()]
param(
    [string]$Target = (Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))),
    [switch]$Force,
    [switch]$DryRun
)

$source = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$targetPath = (Resolve-Path $Target).Path
if ($source -eq $targetPath) { throw 'Target cannot be the kit directory.' }

$items = @('AGENTS.md','CLAUDE.md','GEMINI.md','ANTIGRAVITY.md','.agents','.ai','.claude','.cursor','.githooks','.windsurf','.github/copilot-instructions.md','.github/workflows/gates.yml')
$files = foreach ($item in $items) {
    $path = Join-Path $source $item
    if (Test-Path -LiteralPath $path -PathType Container) { Get-ChildItem -LiteralPath $path -Recurse -File }
    elseif (Test-Path -LiteralPath $path -PathType Leaf) { Get-Item -LiteralPath $path }
}

# Drop build artifacts / local-only config that happen to live under a
# managed path (__pycache__, .claude/settings.local.json, ...) but keep
# untracked-yet-real files, so this only relies on .gitignore, not history.
$isGitRepo = $false
try { git -C $source rev-parse --is-inside-work-tree 2>$null | Out-Null; $isGitRepo = ($LASTEXITCODE -eq 0) } catch { $isGitRepo = $false }
if ($isGitRepo) {
    $files = $files | Where-Object {
        $relative = $_.FullName.Substring($source.Length).TrimStart('\','/')
        git -C $source check-ignore -q -- $relative
        $LASTEXITCODE -ne 0
    }
}

$conflicts = @()
foreach ($file in $files) {
    $relative = $file.FullName.Substring($source.Length).TrimStart('\','/')
    $destination = Join-Path $targetPath $relative
    if ((Test-Path -LiteralPath $destination) -and -not ((Get-FileHash -LiteralPath $file.FullName).Hash -eq (Get-FileHash -LiteralPath $destination).Hash)) { $conflicts += $relative }
}
if ($conflicts.Count -gt 0 -and -not $Force) {
    $conflicts | ForEach-Object { Write-Error "conflict: $_" }
    throw 'Installation stopped. Re-run with -Force to replace managed files.'
}

foreach ($file in $files) {
    $relative = $file.FullName.Substring($source.Length).TrimStart('\','/')
    $destination = Join-Path $targetPath $relative
    if ($DryRun) { Write-Output "copy: $relative"; continue }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destination) | Out-Null
    Copy-Item -LiteralPath $file.FullName -Destination $destination -Force
}

if (-not $DryRun) {
    $ignore = Join-Path $targetPath '.gitignore'
    $marker = '# AI-Kit runtime state'
    if (-not (Test-Path -LiteralPath $ignore) -or -not (Select-String -LiteralPath $ignore -SimpleMatch $marker -Quiet)) {
        Add-Content -LiteralPath $ignore -Value "`n$marker`n.ai-work/state/`n.ai-work/logs/`n.ai-work/snapshots/`n.ai-work/**/*.lock`n.ai-work/**/*.tmp"
    }
}

Write-Output "AI-Kit installed into $targetPath"
Write-Output 'Next: bash .ai/scripts/bootstrap.sh; bash .ai/scripts/doctor.sh'
