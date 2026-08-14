@echo off
title MW Books
cd /d "%~dp0"
echo Starting MW Books (first run installs two small components)...
python -m pip install --quiet flask beancount 2>nul || py -m pip install --quiet flask beancount
start "" http://localhost:5001
python mw-ui\app.py || py mw-ui\app.py
pause
