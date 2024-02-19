@echo off
echo You must have git installed and on PATH to use the update program. Continue if this is fine
pause
git init
git pull https://github.com/JinxTheCatto/Stellite.git
echo Done updating!
pause