@echo off
title Audio Upscale Lab

call "%USERPROFILE%\miniconda3\Scripts\activate.bat" audio-upscale-lab

cd /d "%~dp0"

python app.py

echo.
echo L'application s'est fermee.
pause