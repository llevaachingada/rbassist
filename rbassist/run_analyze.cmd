
@echo off
setlocal enabledelayedexpansion
if not exist .venv\Scripts\python.exe (
  echo [!] .venv not found. Run install.cmd first.
  pause
  exit /b 1
)
set MUSIC=D:\Music
set /p MUSIC=Enter path to your music folder [default D:\Music]: 
if "%MUSIC%"=="" set MUSIC=D:\Music
echo Running analysis on "%MUSIC%"
".venv\Scripts\python.exe" -m rbassist.cli analyze --input "%MUSIC%" --profile club_hifi_150s --device auto --workers 6 --rebuild-index
pause
