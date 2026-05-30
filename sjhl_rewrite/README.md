# SJHL Rewrite

这是一个独立重写版，不修改当前项目的 `backend`、`frontend` 和 `mobile-native-android`。

核心传输方式：

1. 任务开始时才获取 115 下载链接。
2. 先把 115 文件断点下载到本地临时目录。
3. 再用 Microsoft Graph upload session 分片上传到世纪互联 SharePoint。
4. 上传完成后删除本地临时文件，并记录去重指纹。

## 启动

在 PowerShell 执行：

```powershell
cd C:\Users\USER570019\Desktop\sjhl\sjhl_rewrite
.\run.ps1
```

默认地址：

```text
http://127.0.0.1:17652
```

## 目录

- `app/main.py`: FastAPI 入口和路由。
- `app/db.py`: DuckDB 数据库和数据读写。
- `app/pan115.py`: 115 Open/Cookie 获取下载链接。
- `app/graph.py`: Graph 分片上传。
- `app/transfer.py`: 任务队列、断点下载、本地上传。
- `static/index.html`: 内置后台页面。

