param(
  [string]$Model = "qwen3-embedding:0.6b-fp16"
)

$ErrorActionPreference = "Stop"

function Assert-Command($Name) {
  if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
    throw "$Name is not available in PATH"
  }
}

if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
  Assert-Command winget
  winget install --id Ollama.Ollama --exact --accept-package-agreements --accept-source-agreements
  $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
}

Assert-Command ollama

$server = Get-Process -Name "ollama" -ErrorAction SilentlyContinue
if (-not $server) {
  Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden
  Start-Sleep -Seconds 5
}

ollama pull $Model
python scripts/check_embedding_provider.py --model "ollama/$Model" --dimensions 1024
