@echo off
cd /d %~dp0
rem Take up the latest saved game (python run.py alone starts a new one).
python run.py --resume %*
rem Keep the window open when the server stops on an error, so the message can be read.
if errorlevel 1 pause
