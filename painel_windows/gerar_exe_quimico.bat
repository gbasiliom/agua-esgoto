@echo off
cd /d "%~dp0"
echo Gerando SIGA-Quimico.exe ...
pip install pyinstaller
pyinstaller --noconfirm SIGA-Quimico.spec
echo.
echo Pronto: dist\SIGA-Quimico.exe
pause
