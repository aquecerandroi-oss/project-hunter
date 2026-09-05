# PROJECT HUNTER — cria o .env local pedindo as chaves na tela (entrada oculta).
# Uso (PowerShell, na raiz do projeto ou de qualquer lugar):
#   powershell -ExecutionPolicy Bypass -File C:\dev\project-hunter\infra\scripts\setup_env.ps1
# As chaves nunca passam por chat, log ou agente: você digita, o arquivo é gravado, fim.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$envPath = Join-Path $root ".env"

Write-Host ""
Write-Host "PROJECT HUNTER — configuração do .env" -ForegroundColor Yellow
Write-Host "Arquivo: $envPath"
Write-Host "Pegue as chaves em clerk.com -> sua aplicação -> Configure -> API keys -> Quick copy (Next.js)."
Write-Host ""

if (Test-Path $envPath) {
  $answer = Read-Host "Já existe um .env. Sobrescrever? (s/N)"
  if ($answer -notmatch '^[sS]$') { Write-Host "Nada alterado."; exit 0 }
}

$issuerDefault = "https://measured-stingray-3890.clerk.accounts.dev"
$issuer = Read-Host "CLERK_ISSUER (Enter para usar $issuerDefault)"
if ([string]::IsNullOrWhiteSpace($issuer)) { $issuer = $issuerDefault }
$issuer = $issuer.TrimEnd('/')

function Read-Secret([string]$label, [string]$prefix) {
  while ($true) {
    $secure = Read-Host -AsSecureString "$label (começa com $prefix; digitação oculta)"
    $plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
    if ($plain -and $plain.StartsWith($prefix) -and $plain.Length -gt ($prefix.Length + 10)) { return $plain }
    Write-Host "  valor inválido: precisa começar com $prefix. Tente de novo." -ForegroundColor Red
  }
}

$pk = Read-Secret "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY" "pk_test_"
$sk = Read-Secret "CLERK_SECRET_KEY" "sk_test_"

$content = @(
  "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=$pk",
  "CLERK_SECRET_KEY=$sk",
  "CLERK_ISSUER=$issuer",
  "CLERK_JWKS_URL=$issuer/.well-known/jwks.json"
) -join "`n"

[IO.File]::WriteAllText($envPath, $content + "`n", (New-Object Text.UTF8Encoding($false)))
Write-Host ""
Write-Host "OK: .env gravado com 4 variáveis (valores não exibidos)." -ForegroundColor Green
Write-Host "Agora diga ao agente 'salvei' para ele reiniciar o servidor com as chaves."
