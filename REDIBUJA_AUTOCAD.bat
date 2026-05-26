@echo off
chcp 65001 > nul
title REDIBUJA AutoCAD - DP + Arc-Fitter
color 0B
set PYTHONIOENCODING=utf-8
py -3 "%~dp0autocad_redibuja.py"
if errorlevel 1 (
    echo.
    echo ERROR al ejecutar. Verifica que Python este instalado con: py -3 --version
    pause
)
