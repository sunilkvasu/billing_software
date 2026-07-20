@echo off
REM ============================================================
REM  Launch the Billing Software with no console window.
REM  Double-click this file to start the app.
REM ============================================================

REM Run from the folder this .bat file lives in.
cd /d "%~dp0"

REM pythonw.exe runs the GUI without showing a black console window.
REM "start" launches it and returns immediately (runs in the background).
start "" pythonw.exe "billing_app.py"

REM If pythonw is not on PATH the app may not start. In that case,
REM edit the line above to point at your full Python path, e.g.:
REM   start "" "C:\Users\XVNT68\AppData\Local\Programs\Python\Python312\pythonw.exe" "billing_app.py"
