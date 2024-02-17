@echo off 
Title Downloading Modules...
python --version 3>NUL
if errorlevel 1 goto errorNoPython
pip -v>NUL
if errorlevel 1 goto errorNoPip
python -m pip install -r assets/requirements.txt
cls
echo Done! Please use config.json to edit important settings
pause