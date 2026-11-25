@echo off
setlocal
REM ============================================================
REM  HBK - Windows-Installer bauen (Doppelklick genuegt)
REM  Voraussetzungen (einmalig installieren):
REM   1) Python 3.10+ von python.org (Haken bei "Add python.exe to PATH"
REM      und "tcl/tk and IDLE" gesetzt lassen)
REM   2) Inno Setup 6 von jrsoftware.org
REM ============================================================
cd /d "%~dp0"

where py >nul 2>nul && (set PY=py -3) || (set PY=python)

echo [1/4] Virtuelle Umgebung ...
%PY% -m venv .venv || goto :fehler
call .venv\Scripts\activate.bat

echo [2/4] Pakete installieren ...
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt pyinstaller || goto :fehler

echo [3/4] Tests ...
python -m unittest discover -s tests -p "test_core.py" || goto :fehler

echo [4/4] Programm und Installer bauen ...
pyinstaller --noconfirm --clean --windowed --name HBK --icon "hbk\assets\HBK.ico" --add-data "hbk\assets;hbk\assets" --collect-submodules reportlab --collect-submodules openpyxl --collect-submodules pypdf main.py || goto :fehler

set ISCC="%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist %ISCC% set ISCC="%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist %ISCC% (
  echo Inno Setup 6 wurde nicht gefunden. Bitte installieren: https://jrsoftware.org/isdl.php
  goto :fehler
)
%ISCC% installer\hbk.iss || goto :fehler

echo.
echo FERTIG: dist-installer\HBK-Setup-2.3.0.exe
pause
exit /b 0

:fehler
echo.
echo FEHLER beim Bauen - siehe Meldungen oben.
pause
exit /b 1
