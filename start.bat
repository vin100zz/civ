@echo off
cd /d %~dp0
python run.py %*
rem Keep the window open when the server stops on an error, so the message can be read.
if errorlevel 1 pause
