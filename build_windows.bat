@echo off
setlocal

set "APP_NAME=APK Manager"
set "APP_EXE=dist\%APP_NAME%.exe"

if exist "%APP_EXE%" (
  echo Existing "%APP_EXE%" found. Checking whether it can be replaced...
  del /f /q "%APP_EXE%" >nul 2>nul
  if exist "%APP_EXE%" (
    echo.
    echo Build failed before packaging because "%APP_EXE%" is locked.
    echo Close APK Manager if it is running, close any Explorer preview/details panes,
    echo and make sure antivirus or backup software is not scanning the file, then rerun this script.
    exit /b 1
  )
)

python -m pip install --upgrade pip
if errorlevel 1 (
  echo Build failed while upgrading pip.
  exit /b 1
)

python -m pip install -r requirements.txt
if errorlevel 1 (
  echo Build failed while installing requirements.
  exit /b 1
)

python -m PyInstaller --clean --noconfirm --onefile --windowed --name "%APP_NAME%" src\apk_manager.py
if errorlevel 1 (
  echo Build failed while packaging "%APP_EXE%".
  exit /b 1
)

echo Built "%APP_EXE%"
