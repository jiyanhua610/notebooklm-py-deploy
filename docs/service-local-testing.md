# 本地测试手册：一步步把 NotebookLM PDF 微服务跑起来

这份文档默认你是第一次接触这个项目，也不熟悉 Python 服务部署。你只要按顺序做，就能在本地把服务跑起来，并且亲手发一个 PDF 生成任务。

## 1. 这个服务是做什么的

这个服务会做一条固定链路：

1. 你的 SaaS 或本地测试程序上传一个或多个文件
2. 服务把任务放进内部队列
3. 服务按顺序一次只执行 1 个任务
4. 服务调用 NotebookLM：创建 notebook、逐个上传文件、生成 slide deck、下载 PDF
5. 服务返回一个任务 ID
6. 你轮询任务状态
7. 成功后拿到一个临时下载地址，下载 PDF

当前实现的主要接口在：
- `POST /v1/pdf-jobs`
- `GET /v1/pdf-jobs/{job_id}`
- `POST /v1/pdf-jobs/{job_id}/cancel`
- `GET /downloads/{token}`
- `GET /healthz`

服务代码入口在 [main.py](/D:/notebooklm-py/src/notebooklm/service/main.py)，应用工厂在 [app.py](/D:/notebooklm-py/src/notebooklm/service/app.py)。

## 2. 你本地需要准备什么

至少需要这几样：

1. Python 3.10 或更高版本
2. 一个可以用的 pip
3. Git
4. 一个 Redis
5. 一个已经登录过 NotebookLM 的 Google 账号会话

### 2.1 检查 Python

在终端里运行：

```bash
python --version
```

或者：

```bash
py --version
```

如果没有 Python，请先安装 Python 3.10+。

### 2.2 检查 Redis

如果你本机已经装了 Redis，可以直接运行：

```bash
redis-server --version
```

如果你没有 Redis，最简单的方法通常是 Docker：

```bash
docker run -d --name notebooklm-redis -p 6379:6379 redis:7
```

如果你不用 Docker，也可以安装本地 Redis 服务，只要能提供一个 `redis://localhost:6379/0` 即可。

## 3. 下载代码并进入项目目录

如果你还没有仓库：

```bash
git clone <你的仓库地址>
cd notebooklm-py
```

如果你已经在这个仓库里，直接进入根目录即可。

## 4. 安装依赖

### 方案 A：使用 pip

推荐先创建虚拟环境。

Windows PowerShell：

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

macOS / Linux：

```bash
python3 -m venv .venv
source .venv/bin/activate
```

然后安装服务所需依赖：

```bash
pip install -e ".[service,browser]"
```

如果你还想运行测试，再加上开发依赖：

```bash
pip install -e ".[service,browser,dev]"
```

### 方案 B：使用 uv

如果你机器上已经装了 `uv`：

```bash
uv sync --extra service --extra browser --extra dev
```

## 5. 准备 NotebookLM 登录态

这是最关键的一步。

这个服务不是用 API Key，而是复用你的 Google 登录态。也就是说，服务能不能正常工作，取决于你有没有一份可用的 `storage_state.json`，或者一份 `NOTEBOOKLM_AUTH_JSON`。

### 5.1 最推荐的做法

先在本地用浏览器完成 NotebookLM 登录：

```bash
notebooklm login
```

登录成功后，默认会得到一个文件：

```text
~/.notebooklm/storage_state.json
```

这个文件里保存了浏览器会话 cookie。

### 5.2 如果你已经有现成的登录态文件

也可以直接复用它，不需要重新登录。

### 5.3 两种给服务注入认证的方式

#### 方式 1：直接用文件

设置环境变量：

Windows PowerShell：

```powershell
$env:NOTEBOOKLM_STORAGE_PATH="C:\Users\你的用户名\.notebooklm\storage_state.json"
```

macOS / Linux：

```bash
export NOTEBOOKLM_STORAGE_PATH="$HOME/.notebooklm/storage_state.json"
```

#### 方式 2：直接用 JSON 字符串

把 `storage_state.json` 的内容塞到环境变量里：

```bash
export NOTEBOOKLM_AUTH_JSON='{"cookies":[...]}'
```

对于本地调试来说，方式 1 更简单。

## 6. 配置服务环境变量

这个服务会读取下面这些环境变量，最常用的是前 8 个：

- `NOTEBOOKLM_SERVICE_API_TOKEN`
- `NOTEBOOKLM_SERVICE_REDIS_URL`
- `NOTEBOOKLM_SERVICE_QUEUE`
- `NOTEBOOKLM_SERVICE_PREFIX`
- `NOTEBOOKLM_SERVICE_TMP_DIR`
- `NOTEBOOKLM_SERVICE_DOWNLOADS_DIR`
- `NOTEBOOKLM_SERVICE_MAX_QUEUE_SIZE`
- `NOTEBOOKLM_SERVICE_PUBLIC_BASE_URL`
- `NOTEBOOKLM_SERVICE_DOWNLOAD_TTL_SECONDS`
- `NOTEBOOKLM_SERVICE_QUEUE_TIMEOUT_SECONDS`
- `NOTEBOOKLM_SERVICE_SOURCE_WAIT_TIMEOUT_SECONDS`
- `NOTEBOOKLM_SERVICE_GENERATION_WAIT_TIMEOUT_SECONDS`
- `NOTEBOOKLM_SERVICE_RETRY_ATTEMPTS`
- `NOTEBOOKLM_SERVICE_RETRY_DELAY_SECONDS`

### 6.1 本地最小配置示例

Windows PowerShell：

```powershell
$env:NOTEBOOKLM_SERVICE_API_TOKEN="dev-secret"
$env:NOTEBOOKLM_SERVICE_REDIS_URL="redis://localhost:6379/0"
$env:NOTEBOOKLM_SERVICE_MAX_QUEUE_SIZE="10"
$env:NOTEBOOKLM_SERVICE_PUBLIC_BASE_URL="http://127.0.0.1:8000"
$env:NOTEBOOKLM_STORAGE_PATH="C:\Users\你的用户名\.notebooklm\storage_state.json"
```

macOS / Linux：

```bash
export NOTEBOOKLM_SERVICE_API_TOKEN="dev-secret"
export NOTEBOOKLM_SERVICE_REDIS_URL="redis://localhost:6379/0"
export NOTEBOOKLM_SERVICE_MAX_QUEUE_SIZE="10"
export NOTEBOOKLM_SERVICE_PUBLIC_BASE_URL="http://127.0.0.1:8000"
export NOTEBOOKLM_STORAGE_PATH="$HOME/.notebooklm/storage_state.json"
```

## 7. 启动 Redis

如果你用 Docker：

```bash
docker start notebooklm-redis
```

如果没启动过，可以重新执行：

```bash
docker run -d --name notebooklm-redis -p 6379:6379 redis:7
```

## 8. 启动服务

### 方式 1：用项目脚本启动

```bash
notebooklm-pdf-service
```

默认会监听：

```text
http://0.0.0.0:8000
```

### 方式 2：直接用 uvicorn 启动

```bash
uvicorn notebooklm.service.app:create_app --factory --host 0.0.0.0 --port 8000
```

## 9. 先检查服务是否正常

浏览器访问，或者用 curl：

```bash
curl http://127.0.0.1:8000/healthz
```

正常应该看到类似：

```json
{
  "ok": true,
  "queue_length": 0,
  "active_job_id": null,
  "auth_configured": true
}
```

如果 `auth_configured` 是 `false`，说明你的 NotebookLM 登录态没有正确注入。

## 10. 提交一个测试任务

说明：推荐使用重复的 `files` 字段上传多个文件；历史单文件字段 `file` 仍兼容，但新调用建议统一改成 `files`。

准备一个或多个小一点的源文件，比如 `example.pdf`、`appendix.docx`。

```bash
curl -X POST "http://127.0.0.1:8000/v1/pdf-jobs" \
  -H "X-API-Token: dev-secret" \
  -F "files=@example.pdf" \
  -F "files=@appendix.docx" \
  -F "title=测试任务" \
  -F "instructions=请生成结构清晰的中文演示文稿" \
  -F "deck_format=detailed_deck" \
  -F "deck_length=default"
```

成功后会返回：

```json
{
  "job_id": "a1b2c3d4...",
  "status": "queued",
  "queue_position": 1,
  "created_at": "2026-03-18T...",
  "source_count": 2,
  "output_format": "pdf"
}
```

把 `job_id` 记下来。

## 11. 轮询任务状态

```bash
curl "http://127.0.0.1:8000/v1/pdf-jobs/<job_id>" \
  -H "X-API-Token: dev-secret"
```

你会看到这些状态之一：

- `queued`
- `creating_notebook`
- `uploading_source`
- `waiting_source_ready`
- `generating_pdf`
- `waiting_generation`
- `downloading_pdf`
- `completed`
- `failed`
- `cancelled`
- `cancel_requested`

### 11.1 成功时的返回

```json
{
  "job_id": "a1b2c3d4...",
  "status": "completed",
  "queue_position": null,
  "download_url": "http://127.0.0.1:8000/downloads/xxxxx",
  "error_code": null,
  "error_message": null,
  "created_at": "...",
  "updated_at": "...",
  "started_at": "...",
  "finished_at": "...",
  "source_count": 2,
  "filenames": ["example.pdf", "appendix.docx"],
  "output_format": "pdf"
}
```

## 12. 下载结果文件

拿到 `download_url` 后直接访问即可。当前实际下载结果为 `.pdf`：

```bash
curl -L -o result.pdf "http://127.0.0.1:8000/downloads/xxxxx"
```

如果返回 404，通常有三种可能：

1. token 已经过期
2. 文件已经被清理
3. 任务根本没有成功完成

## 13. 如何取消任务

### 13.1 取消排队中的任务

```bash
curl -X POST "http://127.0.0.1:8000/v1/pdf-jobs/<job_id>/cancel" \
  -H "X-API-Token: dev-secret"
```

如果任务还在排队，返回会是：

```json
{
  "job_id": "...",
  "status": "cancelled"
}
```

### 13.2 取消正在执行的任务

同样调用取消接口。

这时服务会把状态改成 `cancel_requested`，但不会强制终止 Google 那边已经开始的任务；后台仍会继续把清理收尾做完，最终对外结果会变成 `cancelled`，不会给下载地址。

## 14. 如何验证“只允许串行执行”

这个服务的设计是：

- 允许你连续提交多个请求
- 但任意时刻只会执行 1 个 NotebookLM 任务
- 第二个任务必须等第一个进入终态后才开始

你可以这样验证：

1. 提交第一个大文件
2. 立刻再提交第二个文件
3. 查第二个任务状态

你会看到第二个任务保持 `queued`

第一个完成后，第二个才会开始进入：

- `creating_notebook`
- `uploading_source`
- `waiting_source_ready`
- 后续状态

## 15. 常见问题

### 15.1 `401 Unauthorized`

说明请求头 `X-API-Token` 不对。

### 15.2 `auth_configured = false`

说明服务没拿到 NotebookLM 认证信息。检查：

- `NOTEBOOKLM_STORAGE_PATH`
- `NOTEBOOKLM_AUTH_JSON`
- 登录态文件是否真的存在

### 15.3 任务一直失败，`error_code = auth_expired`

说明 NotebookLM 登录态失效了。重新执行：

```bash
notebooklm login
```

然后重启服务。

### 15.4 新任务提交时报 `queue_full`

说明排队数量达到 `NOTEBOOKLM_SERVICE_MAX_QUEUE_SIZE` 的上限。

### 15.5 下载地址过一会儿失效

这是正常行为。下载链接是临时的，受 `NOTEBOOKLM_SERVICE_DOWNLOAD_TTL_SECONDS` 控制。

## 16. 本地测试结束后如何清理

如果你是 Docker Redis：

```bash
docker stop notebooklm-redis
```

如果想删掉服务生成的临时文件：

```bash
rm -rf .notebooklm-service
```

Windows PowerShell：

```powershell
Remove-Item -Recurse -Force .notebooklm-service
```

## 17. 推荐你的本地联调顺序

最稳的顺序是：

1. 安装 Python 和 Redis
2. 安装项目依赖
3. 先跑 `notebooklm login`
4. 设置环境变量
5. 启动 Redis
6. 启动服务
7. 先访问 `/healthz`
8. 再发 `POST /v1/pdf-jobs`
9. 轮询状态
10. 成功后下载 PDF

如果你按这个流程走，绝大多数本地问题都能快速定位出来。