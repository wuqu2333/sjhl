# 世纪互联 SP 管理器

当前项目已整理为 Python FastAPI 后端 + Vue3 TypeScript Vite 前端。

## 目录

- `backend/`: FastAPI 后端、DuckDB 数据库访问、Graph/115/同步/传输队列服务。
- `frontend/apps/web-antd/`: Vue3 + TypeScript + Ant Design Vue 风格后台页面。
- `scripts/run-local.ps1`: 本地源码一键运行脚本。
- `scripts/build-windows-exe.ps1`: Windows 单文件 exe 打包脚本。

本地数据默认保存到：

```text
%APPDATA%\SJHL-SP-Manager
```

## 本地源码一键运行

双击：

```text
run-local.cmd
```

或手动执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-local.ps1
```

脚本会启动：

- 后端 FastAPI 源码服务。
- 前端 Vite 开发服务。
- 浏览器页面。

如果 `17651` 或 `5173` 被占用，脚本会自动向后寻找空闲端口，并把前端代理指向实际后端端口。

## 首次运行依赖

后端需要已有虚拟环境：

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

前端如果没有 `frontend/node_modules`，一键运行脚本会自动执行：

```powershell
npm --prefix frontend ci
```

## 常用开发命令

后端单独运行：

```powershell
cd backend
.\.venv\Scripts\python.exe run.py
```

前端单独运行：

```powershell
cd frontend
npm run dev
```

前端构建校验：

```powershell
npm --prefix frontend run build
```

打包 exe：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build-windows-exe.ps1
```

