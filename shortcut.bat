@echo off
rem Puts a "Civ" shortcut with the temple icon on the desktop. It runs launcher.pyw with pythonw.exe:
rem no console, the game opens in a window of its own, and the shortcut can be pinned to the taskbar.
rem Run it once (again if the folder or Python moves).
cd /d %~dp0
set "PYTHONW="
for /f "delims=" %%p in ('python -c "import sys, pathlib; print(pathlib.Path(sys.executable).with_name('pythonw.exe'))"') do set "PYTHONW=%%p"
if not exist "%PYTHONW%" (
    echo pythonw.exe introuvable : installer Python 3.11 ou plus, voir README.md.
    pause
    exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$s = (New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop') + '\Civ.lnk');" ^
  "$s.TargetPath = '%PYTHONW%';" ^
  "$s.Arguments = [char]34 + '%~dp0launcher.pyw' + [char]34;" ^
  "$s.WorkingDirectory = '%~dp0';" ^
  "$s.IconLocation = '%~dp0resources\civ.ico,0';" ^
  "$s.Save()"
if errorlevel 1 (pause) else (echo Raccourci "Civ" cree sur le Bureau.)
