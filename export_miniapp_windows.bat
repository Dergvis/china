@echo off
setlocal enabledelayedexpansion

if "%~1"=="" (
  echo Usage: export_miniapp_windows.bat C:\path\to\tourist-miniapp-import
  exit /b 1
)

set TARGET=%~1
set SRC=%~dp0..\miniapp

if not exist "%SRC%" (
  echo miniapp folder not found: %SRC%
  exit /b 1
)

if exist "%TARGET%" rmdir /s /q "%TARGET%"
mkdir "%TARGET%"

xcopy "%SRC%\*" "%TARGET%\" /E /I /Y >nul

set ERR=0
for %%F in (
  "app.json"
  "project.config.json"
  "index.wxml"
  "index.js"
  "index.wxss"
) do (
  if not exist "%TARGET%\%%~F" (
    echo Missing: %%~F
    set ERR=1
  )
)

if "%ERR%"=="1" (
  echo Export failed.
  exit /b 1
)

echo Miniapp exported successfully to: %TARGET%
echo Import this exact folder in WeChat DevTools.
