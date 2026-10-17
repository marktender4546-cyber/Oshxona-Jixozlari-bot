@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Python virtual environment yaratilmoqda...
  py -3 -m venv .venv
  if errorlevel 1 goto error
)
call ".venv\Scripts\activate.bat"
python -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 goto error
python bot.py
if errorlevel 1 goto error
goto end
:error
echo.
echo Xatolik yuz berdi. README.md faylidagi qo'llanmani ko'ring.
:end
echo.
pause
