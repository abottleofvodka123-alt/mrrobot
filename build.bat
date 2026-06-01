@echo off
echo Installing dependencies...
pip install -r requirements.txt

echo Building exe...
pyinstaller code_solver.spec --noconfirm

echo Done! Exe is in dist\code_solver\
pause