@echo off
rem Builds dist\S2mini60\S2mini60.exe (folder build, no console).
rem Needs Python 3.10+; creates its own .venv-build environment.
cd /d "%~dp0"
if not exist .venv-build python -m venv .venv-build
call .venv-build\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --onedir --windowed --noupx --name S2mini60 ^
  --collect-all customtkinter --collect-all winrt --collect-submodules pycaw --collect-submodules comtypes ^
  --hidden-import pystray._win32 --hidden-import hid --hidden-import serial --hidden-import serial.tools.list_ports ^
  s2mini_app.py
echo.
echo Done: %~dp0dist\S2mini60\S2mini60.exe
