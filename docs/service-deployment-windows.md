# 部署手册：如何将 NotebookLM PDF 微服务部署到 Windows 服务器

这份文档详细介绍了如何将 NotebookLM PDF 微服务部署到 Windows Server 环境中。虽然项目核心逻辑是跨平台的，但 Windows 在后台服务管理和部分依赖（如 Redis）上与 Linux 有所不同。

## 1. 系统要求与工具准备

在开始之前，请确保您的 Windows 服务器满足以下要求：

- **操作系统**：Windows Server 2019/2022 或 Windows 10/11 64位。
- **Python 3.10+**：建议从 [python.org](https://www.python.org/) 下载安装，并确保勾选 "Add Python to PATH"。
- **Git**：用于克隆代码仓库。
- **uv**（推荐）：极其快速的 Python 依赖包管理工具。
  - 安装命令（PowerShell）：`powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
- **Redis for Windows**：
  - 推荐使用 [Memurai](https://www.memurai.com/) (Redis 的 Windows 本地移植版)。
  - 或者使用 **Docker Desktop** 运行 Redis 容器。
- **NSSM (Non-Sucking Service Manager)**：用于将 Python 进程注册为 Windows 系统服务。
  - 下载地址：[nssm.cc](https://nssm.cc/download)

## 2. 推荐的目录结构

建议在 `C:` 盘根目录下创建项目目录，以避免长路径或权限问题：

```text
C:\notebooklm-py\
├── app\                  # 代码目录 (git clone 处)
├── runtime\
│   ├── tmp\              # 上传临时文件
│   └── downloads\        # 结果 PDF
├── env\
│   ├── service.env       # 环境变量文件
│   └── storage_state.json # NotebookLM 登录态文件
└── tools\                # 存放 nssm.exe 等工具
```

## 3. 部署代码与环境

1. **创建目录**：
   ```powershell
   mkdir C:\notebooklm-py\app
   mkdir C:\notebooklm-py\runtime\tmp
   mkdir C:\notebooklm-py\runtime\downloads
   mkdir C:\notebooklm-py\env
   ```

2. **克隆代码**：
   ```powershell
   cd C:\notebooklm-py
   git clone <你的仓库地址> app
   cd app
   ```

3. **安装依赖**：
   使用 `uv` 同步依赖（会自动创建虚拟环境）：
   ```powershell
   uv sync --extra service --extra browser
   ```

## 4. 配置环境变量

在 `C:\notebooklm-py\env\service.env` 中创建配置文件。注意 Windows 路径使用反斜杠或双反斜杠：

```ini
NOTEBOOKLM_SERVICE_API_TOKEN=你的随机强密码
NOTEBOOKLM_SERVICE_REDIS_URL=redis://127.0.0.1:6379/0
NOTEBOOKLM_SERVICE_TMP_DIR=C:\notebooklm-py\runtime\tmp
NOTEBOOKLM_SERVICE_DOWNLOADS_DIR=C:\notebooklm-py\runtime\downloads
NOTEBOOKLM_SERVICE_MAX_QUEUE_SIZE=20
NOTEBOOKLM_SERVICE_PUBLIC_BASE_URL=http://你的服务器IP:8000
NOTEBOOKLM_STORAGE_PATH=C:\notebooklm-py\env\storage_state.json
# Windows 专用：强制开启 UTF-8 模式防止中文乱码
PYTHONUTF8=1
```

## 5. 准备登录态 (storage_state.json)

由于服务器通常不方便开启浏览器进行登录，请在您的**开发机（本地电脑）**上生成登录态：

1. 在本地电脑运行：`uv run notebooklm login`
2. 完成登录并按下回车。
3. 将生成的 `C:\Users\<你的用户名>\.notebooklm\storage_state.json` 拷贝到服务器的 `C:\notebooklm-py\env\storage_state.json`。

## 6. 后台运行与服务管理

### 6.1 推荐方案：使用 NSSM 注册服务

为了让服务在后台常驻运行并在重启后自动启动，最稳定的方式是使用 NSSM。

1. 将下载的 `nssm.exe` (Win64版) 放到 `C:\notebooklm-py\tools\`。
2. 以**管理员身份**打开 PowerShell，运行：
   ```powershell
   C:\notebooklm-py\tools\nssm.exe install NotebookLM-PDF
   ```
3. 在弹出的 GUI 窗口中配置：
   - **Path**: `C:\notebooklm-py\app\.venv\Scripts\python.exe`
   - **Startup directory**: `C:\notebooklm-py\app`
   - **Arguments**: `-m uvicorn notebooklm.service.app:create_app --factory --host 127.0.0.1 --port 8000`
   - **Environment** 选项卡：点击 "Edit" 并粘贴 `service.env` 中的内容（每行一个变量）。
4. 点击 **Install service**。
5. 启动服务：
   ```powershell
   Start-Service NotebookLM-PDF
   ```

### 6.2 快速方案：使用任务计划程序 (内置工具)

如果您不想下载第三方工具，可以使用 Windows 自带的“任务计划程序”来实现后台运行和开机自启。

1. **创建启动脚本** (`C:\notebooklm-py\app\start_service.bat`)：
   ```batch
   @echo off
   cd /d C:\notebooklm-py\app
   :: 设置必要的环境变量
   set NOTEBOOKLM_STORAGE_PATH=C:\notebooklm-py\app\storage_state.json
   :: 执行服务程序
   .venv\Scripts\notebooklm-pdf-service.exe
   ```

2. **通过命令行创建并注册任务**（需管理员权限）：
   使用以下命令将脚本注册为系统任务，随系统启动且在后台静默运行：
   ```powershell
   schtasks /create /tn "NotebookLM_Service" /tr "C:\notebooklm-py\app\start_service.bat" /sc onstart /ru "System" /rl highest
   ```

3. **管理命令**：
   - **立即启动**：`schtasks /run /tn "NotebookLM_Service"`
   - **停止任务**：`schtasks /end /tn "NotebookLM_Service"`
   - **删除任务**：`schtasks /delete /tn "NotebookLM_Service" /f`

## 7. 配置 Nginx 反向代理 (可选但推荐)

1. 下载 [Nginx for Windows](http://nginx.org/en/download.html) 并解压。
2. 编辑 `conf/nginx.conf`，在 `http` 块中添加：
   ```nginx
   server {
       listen 80;
       server_name your-pdf-service.example.com;

       client_max_body_size 50M;

       location / {
           proxy_pass http://127.0.0.1:8000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
       }
   }
   ```
3. 启动 Nginx。

## 8. 验证部署

1. **访问健康检查**：
   在浏览器或使用 `curl` 访问 `http://127.0.0.1:8000/healthz`。
2. **确认认证**：
   确保返回的 JSON 中 `"auth_configured": true`。

## 9. 维护与更新

- **查看日志**：Windows 服务日志可以在 NSSM 的 "I/O" 选项卡中配置输出文件，或者查看 Windows 事件查看器。
- **更新代码**：
  ```powershell
  cd C:\notebooklm-py\app
  git pull
  uv sync --extra service --extra browser
  Restart-Service NotebookLM-PDF
  ```
- **登录过期**：按照第 5 步重新从开发机同步 `storage_state.json` 并在服务器上重启服务。

## 10. 常见问题 (Windows 特有)

- **端口占用**：如果 8000 端口被占用，请在 NSSM 参数和 `service.env` 中修改。
- **权限问题**：确保运行服务的用户（默认为 LocalSystem）有权访问 `C:\notebooklm-py` 及其子目录。
- **字符编码**：如果任务日志中出现中文乱码，请务必确认环境变量 `PYTHONUTF8=1` 已生效。
