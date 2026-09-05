# PROJECT HUNTER - cria o .env local pedindo as chaves na tela (entrada oculta).
# Uso (PowerShell, de qualquer pasta):
#   powershell -ExecutionPolicy Bypass -File C:\dev\project-hunter\infra\scripts\setup_env.ps1
# As chaves nunca passam por chat, log ou agente: voce digita, o arquivo e gravado, fim.
# (Arquivo mantido em ASCII puro: o PowerShell 5.1 le scripts sem BOM como ANSI.)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$envPath = Join-Path $root ".env"

Write-Host ""
Write-Host "PROJECT HUNTER - configuracao do .env" -ForegroundColor Yellow
Write-Host "Arquivo: $envPath"
Write-Host "Pegue as chaves em clerk.com -> sua aplicacao -> Configure -> API keys -> Quick copy (Next.js)."
Write-Host ""

if (Test-Path $envPath) {
  $answer = Read-Host "Ja existe um .env. Sobrescrever? (s/N)"
  if ($answer -notmatch '^[sS]$') { Write-Host "Nada alterado."; exit 0 }
}

$issuerDefault = "https://measured-stingray-3890.clerk.accounts.dev"
$issuer = Read-Host "CLERK_ISSUER (Enter para usar $issuerDefault)"
if ([string]::IsNullOrWhiteSpace($issuer)) { $issuer = $issuerDefault }
$issuer = $issuer.TrimEnd('/')

# Aceita o valor puro, "NOME=valor", ou varias linhas coladas de uma vez (pega o token certo).
function Extract-Key([string]$raw, [string]$prefix) {
  if (-not $raw) { return $null }
  $tokens = $raw -split '[\s"'']+'
  foreach ($t in $tokens) {
    $candidate = $t
    $eq = $candidate.LastIndexOf('=')
    if ($eq -ge 0) { $candidate = $candidate.Substring($eq + 1) }
    if ($candidate.StartsWith($prefix) -and $candidate.Length -gt ($prefix.Length + 10)) { return $candidate }
  }
  return $null
}

function Read-Secret([string]$label, [string]$prefix) {
  while ($true) {
    $prompt = $label + " (comeca com " + $prefix + "; digitacao oculta)"
    $secure = Read-Host -AsSecureString $prompt
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    $plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    $value = Extract-Key $plain $prefix
    if ($value) { return $value }
    Write-Host ("  valor invalido: precisa conter uma chave que comeca com " + $prefix + ". Tente de novo.") -ForegroundColor Red
  }
}

$pk = Read-Secret "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY" "pk_test_"
$sk = Read-Secret "CLERK_SECRET_KEY" "sk_test_"

# Opcional: chave da OpenAI para a segunda opiniao da Astra (infra/scripts/ask_astra.py).
$openaiSecure = Read-Host -AsSecureString "OPENAI_API_KEY (opcional, Enter para pular; digitacao oculta)"
$openaiBstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($openaiSecure)
$openai = [Runtime.InteropServices.Marshal]::PtrToStringAuto($openaiBstr)
[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($openaiBstr)

$lines = @(
  "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=" + $pk,
  "CLERK_SECRET_KEY=" + $sk,
  "CLERK_ISSUER=" + $issuer,
  "CLERK_JWKS_URL=" + $issuer + "/.well-known/jwks.json"
)
if (-not [string]::IsNullOrWhiteSpace($openai)) {
  $lines += "OPENAI_API_KEY=" + $openai.Trim()
  $lines += "OPENAI_MODEL=gpt-6-astra"
}
$content = ($lines -join "`n") + "`n"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[IO.File]::WriteAllText($envPath, $content, $utf8NoBom)

Write-Host ""
Write-Host ("OK: .env gravado com " + $lines.Count + " variaveis (valores nao exibidos).") -ForegroundColor Green
Write-Host ("  publishable key: " + $pk.Substring(0, 8) + "... (" + $pk.Length + " caracteres)")
Write-Host ("  secret key:      " + $sk.Substring(0, 8) + "... (" + $sk.Length + " caracteres)")
Write-Host "Agora diga ao agente 'salvei' para ele reiniciar o servidor com as chaves."
