@echo off
chcp 65001 >nul
cd /d %~dp0
if not exist venv (
  echo [info] 创建虚拟环境 ...
  python -m venv venv
)
call venv\Scripts\activate.bat
echo [info] 安装依赖（首次较慢）...
pip install -q -r requirements.txt
echo [info] 启动后端服务 http://localhost:5000
python app.py
