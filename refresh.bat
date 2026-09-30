@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在刷新 Loon 脚本数据（增量拉取镜像库）...
python build.py
if errorlevel 1 (
  echo.
  echo [失败] 请检查 git / python 是否可用。
) else (
  echo.
  echo [完成] 双击 index.html 即可查看最新数据。
)
pause
