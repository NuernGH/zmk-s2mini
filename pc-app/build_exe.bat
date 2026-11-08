@echo off
rem Buduje S2mini60.exe (jeden plik, bez konsoli) w folderze dist\.
rem Wymaga Pythona 3.10+; tworzy własne środowisko .venv-build.
cd /d "%~dp0"
if not exist .venv-build python -m venv .venv-build
call .venv-build\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --onefile --windowed --name S2mini60 ^
  --collect-all customtkinter --collect-all winrt --collect-submodules pycaw --collect-submodules comtypes ^
  --hidden-import pystray._win32 --hidden-import hid --hidden-import serial --hidden-import serial.tools.list_ports ^
  s2mini_app.py
echo.
echo Gotowe: %~dp0dist\S2mini60.exe
