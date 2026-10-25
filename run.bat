@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Use pythonw (no console window); fall back to PATH if the default install is not found
set "PYW=%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe"
if not exist "%PYW%" set "PYW=pythonw"
start "" "%PYW%" main.py %*
