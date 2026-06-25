@echo off
setlocal

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m PyInstaller --clean --onefile --windowed --name "APK Manager" src\apk_manager.py

if errorlevel 1 (
  echo Build failed.
  exit /b 1
)

echo Built dist\APK Manager.exe
