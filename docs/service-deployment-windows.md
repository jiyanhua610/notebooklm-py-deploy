# NotebookLM PDF 服务 Windows 部署指南

本指南介绍如何在 Windows Server 环境下部署和运行 NotebookLM PDF 微服务。

## 1. 准备工作

- **Python 3.10+**: 建议安装最新的 Python 3.12。
- **Git**: 用于克隆和同步代码。
- **Redis**: Windows 版 Redis (推荐使用 [Redis-6.2.6-Windows-x64](https://github.com/tporadowski/redis/releases))。

## 2. 环境搭建

1. **克隆代码**：
   ```powershell
   git clone https://github.com/jiyanhua610/notebooklm-py-deploy.git C:\notebooklm-py\app
   ```

2. **安装 uv** (高性能 Python 包管理器)：
   ```powershell
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

3. **安装依赖**：
   ```powershell
   cd C:\notebooklm-py\app
   uv sync --extra service --extra browser
   ```

## 3. 服务配置 (service_config.json)

本项目使用 `service_config.json` 进行统一配置，不再依赖环境变量。

在项目根目录下创建该文件：
```json
{
    "api_token": "Jiumiao20260325",
    "redis_url": "redis://127.0.0.1:6379/0",
    "temp_dir": "C:/notebooklm-py/runtime/tmp",
    "downloads_dir": "C:/notebooklm-py/runtime/downloads",
    "download_ttl_seconds": 2592000,
    "job_retention_seconds": 2592000,
    "storage_path": "C:/notebooklm-py/app/storage_state.json",
    "default_language": "zh_Hans"
}
```

- **api_token**: 通讯暗号，需与 Java 端配置一致。
- **download_ttl_seconds**: 生成的 PDF 保留时长（2592000 秒 = 30 天）。
- **storage_path**: 登录态文件 `storage_state.json` 的绝对路径。

## 4. 准备登录态 (storage_state.json)

请在您的**本地电脑**上生成登录态并拷贝到服务器：
1. 本地运行：`uv run notebooklm login`
2. 完成登录后，将生成的 `storage_state.json` 拷贝到服务器 `service_config.json` 中指定的路径。

## 5. 后台运行与管理

### 5.1 启动脚本 (start_service.bat)
项目根目录已包含 `start_service.bat`，内容如下：
```batch
@echo off
cd /d C:\notebooklm-py\app
set PYTHONPATH=src
set PYTHONUTF8=1
.venv\Scripts\python.exe -m uvicorn notebooklm.service.app:create_app --factory --host 0.0.0.0 --port 8000
```

### 5.2 注册为 Windows 任务
以管理员权限运行：
```powershell
schtasks /create /tn "NotebookLM_Service" /tr "C:\notebooklm-py\app\start_service.bat" /sc onstart /ru "System" /rl highest
```

### 5.3 管理命令
- **启动**：`schtasks /run /tn "NotebookLM_Service"`
- **停止**：`schtasks /end /tn "NotebookLM_Service"`

## 6. 验证部署

访问 `http://<服务器IP>:8000/healthz`，确保返回：
- `"auth_configured": true` (文件已就绪)
- `"google_auth_ok": true` (谷歌连接正常)

## 7. 常见问题
- **查看日志**：直接查看项目根目录下的 `service.log`。
- **更新代码**：执行 `git pull` 后重启任务即可。
