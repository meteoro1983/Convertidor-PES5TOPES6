@echo off
setlocal
pushd "%~dp0"
set PY=python
where python >nul 2>nul || set PY=py
where %PY% >nul 2>nul || (echo Instala Python 3 desde python.org y marca "Add Python to PATH".& pause & exit /b 1)
%PY% -m pip install --upgrade pyinstaller
rem Opcional: permite arrastrar el archivo sobre la ventana (si no se instala, se puede arrastrar sobre el icono del .exe)
set DND=
%PY% -m pip install tkinterdnd2 >nul 2>nul
%PY% -c "import tkinterdnd2" >nul 2>nul && set DND=--collect-all tkinterdnd2
%PY% -m PyInstaller --onefile --noconsole --name Convertidor_WE9_a_PES6 --add-data "datos;datos" %DND% we9_a_pes6.py
echo.
echo Listo: el .exe portable esta en la carpeta "dist"  (Convertidor_WE9_a_PES6.exe).
pause
