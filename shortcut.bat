@echo off
rem A .bat file cannot carry an icon of its own: this puts a "Civ" shortcut to start.bat,
rem with the temple icon, on the desktop. Run it once (again if the folder moves).
cd /d %~dp0
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$s = (New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop') + '\Civ.lnk');" ^
  "$s.TargetPath = '%~dp0start.bat';" ^
  "$s.WorkingDirectory = '%~dp0';" ^
  "$s.IconLocation = '%~dp0resources\civ.ico,0';" ^
  "$s.Save()"
if errorlevel 1 (pause) else (echo Raccourci "Civ" cree sur le Bureau.)
