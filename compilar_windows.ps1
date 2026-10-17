# =====================================================================
# SCRIPT DE COMPILACAO COMPLETA - WINDOWS (.EXE)
# =====================================================================
$ErrorActionPreference = "Stop"

Write-Host ">>> A verificar interpretador Python..." -ForegroundColor Cyan

$pyCmd = $null

if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3.12 -c "import sys" 2>$null
    if ($LASTEXITCODE -eq 0) {
        $pyCmd = "py -3.12"
    } else {
        & py -3.11 -c "import sys" 2>$null
        if ($LASTEXITCODE -eq 0) {
            $pyCmd = "py -3.11"
        }
    }
}

if (-not $pyCmd) {
    Write-Host "AVISO: Python 3.11/3.12 nao detectado via 'py'. A usar 'python' padrao." -ForegroundColor Yellow
    $pyCmd = "python"
}

Write-Host "Interpretador selecionado: $pyCmd" -ForegroundColor Green

# -------------------------------------------------------------
# 1. Compilar Backend
# -------------------------------------------------------------
Write-Host "`n===============================================" -ForegroundColor Cyan
Write-Host " [1/3] A preparar e compilar Backend..." -ForegroundColor Cyan
Write-Host "===============================================" -ForegroundColor Cyan

Set-Location "$PSScriptRoot\backend"

if (-not (Test-Path "venv")) {
    Write-Host "A criar ambiente virtual venv no backend..."
    Invoke-Expression "$pyCmd -m venv venv"
}

Write-Host "A ativar venv e a instalar dependencias..."
& ".\venv\Scripts\Activate.ps1"
python -m pip install --upgrade pip
pip install -r requirements.txt pyinstaller

Write-Host "A compilar Servidor Backend (SIGA-Backend.exe)..." -ForegroundColor Yellow
pyinstaller --clean -y SIGA-Backend.spec

Write-Host "A compilar Utilitario de Senhas (SIGA-Resetar-Senhas.exe)..." -ForegroundColor Yellow
pyinstaller --clean -y SIGA-Resetar-Senhas.spec

deactivate
Set-Location "$PSScriptRoot"

# -------------------------------------------------------------
# 2. Compilar Painel Windows
# -------------------------------------------------------------
Write-Host "`n===============================================" -ForegroundColor Cyan
Write-Host " [2/3] A preparar e compilar Painel Windows..." -ForegroundColor Cyan
Write-Host "===============================================" -ForegroundColor Cyan

Set-Location "$PSScriptRoot\painel_windows"

if (-not (Test-Path "venv")) {
    Write-Host "A criar ambiente virtual venv no painel_windows..."
    Invoke-Expression "$pyCmd -m venv venv"
}

Write-Host "A ativar venv e a instalar dependencias..."
& ".\venv\Scripts\Activate.ps1"
python -m pip install --upgrade pip

try {
    pip install -r requirements.txt pyinstaller
} catch {
    Write-Host "Falha no Pillow fixado. A tentar Pillow recente compativel..." -ForegroundColor Yellow
    pip install --upgrade pillow
    pip install customtkinter==5.2.2 requests==2.32.3 pyinstaller
}

Write-Host "A compilar Painel Geral (SIGA.exe)..." -ForegroundColor Yellow
pyinstaller --clean -y SIGA.spec

Write-Host "A compilar Painel Quimico (SIGA-Quimico.exe)..." -ForegroundColor Yellow
pyinstaller --clean -y SIGA-Quimico.spec

deactivate
Set-Location "$PSScriptRoot"

# -------------------------------------------------------------
# Conclusão
# -------------------------------------------------------------
Write-Host "`n===============================================" -ForegroundColor Green
Write-Host " CONCLUIDO COM SUCESSO!" -ForegroundColor Green
Write-Host " Ficheiros executaveis gerados em:" -ForegroundColor Green
Write-Host "  - backend\dist\SIGA-Backend.exe"
Write-Host "  - backend\dist\SIGA-Resetar-Senhas.exe"
Write-Host "  - painel_windows\dist\SIGA.exe"
Write-Host "  - painel_windows\dist\SIGA-Quimico.exe"
Write-Host "===============================================" -ForegroundColor Green