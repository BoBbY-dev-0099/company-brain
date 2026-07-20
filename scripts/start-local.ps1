param(
  [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $repoRoot ".env"
Set-Location $repoRoot

if (-not (Test-Path -LiteralPath $envPath)) {
  Copy-Item -LiteralPath (Join-Path $repoRoot ".env.example") -Destination $envPath
}

$lines = @(Get-Content -LiteralPath $envPath)

function New-UrlSafeSecret {
  param([int]$ByteCount = 32)
  $bytes = New-Object byte[] $ByteCount
  $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
  try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
  return ([Convert]::ToBase64String($bytes).Replace('+', '-').Replace('/', '_'))
}

function Get-EnvValue {
  param([string]$Name)
  $line = $lines | Where-Object { $_ -match "^$([regex]::Escape($Name))=" } | Select-Object -First 1
  if ($null -eq $line) { return "" }
  return ($line -replace "^$([regex]::Escape($Name))=", "")
}

function Set-EnvValue {
  param([string]$Name, [string]$Value)
  $prefix = "$Name="
  for ($i = 0; $i -lt $script:lines.Count; $i++) {
    if ($script:lines[$i].StartsWith($prefix)) {
      $script:lines[$i] = "$prefix$Value"
      return
    }
  }
  $script:lines += "$prefix$Value"
}

# This helper is intentionally local-only. Production must provide its own
# operator credentials through its secret-management process.
if ([string]::IsNullOrWhiteSpace((Get-EnvValue "INTEGRATION_ADMIN_TOKEN"))) {
  Set-EnvValue "INTEGRATION_ADMIN_TOKEN" (New-UrlSafeSecret)
}
if ([string]::IsNullOrWhiteSpace((Get-EnvValue "INTEGRATION_CONFIG_ENCRYPTION_KEY"))) {
  Set-EnvValue "INTEGRATION_CONFIG_ENCRYPTION_KEY" (New-UrlSafeSecret)
}
if ([string]::IsNullOrWhiteSpace((Get-EnvValue "LOCAL_REHEARSAL"))) {
  Set-EnvValue "LOCAL_REHEARSAL" "true"
}

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllLines($envPath, $lines, $utf8NoBom)
Write-Host "Local operator setup is ready. Secrets were generated or preserved in .env (values are not printed)."

$composeArgs = @("compose", "--profile", "full", "up", "-d", "--force-recreate")
if (-not $SkipBuild) { $composeArgs += "--build" }
$composeArgs += @("api", "worker", "nginx")
& docker @composeArgs
if ($LASTEXITCODE -ne 0) { throw "Docker Compose failed with exit code $LASTEXITCODE" }

# Nginx resolves the api service address at startup; restart it after API
# recreation so a stale container IP cannot produce a local 502.
for ($attempt = 0; $attempt -lt 30; $attempt++) {
  $health = (& docker inspect companybrain-api --format '{{.State.Health.Status}}' 2>$null)
  if ($health -eq "healthy") { break }
  Start-Sleep -Seconds 2
}
& docker compose restart nginx
if ($LASTEXITCODE -ne 0) { throw "Nginx restart failed with exit code $LASTEXITCODE" }

Write-Host "Open http://localhost/setup and click Refresh status."
