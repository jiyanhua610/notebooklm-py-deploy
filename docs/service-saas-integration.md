# SaaS 对接文档：如何调用 NotebookLM PDF 微服务

这份文档是写给 SaaS 开发团队的。目标是让后端工程师拿到这份文档后，就可以直接开始编码对接。

## 1. 服务定位

这个微服务负责做一件事：

- 接收一个用户上传的文件
- 将它提交给 NotebookLM 生成 slide deck
- 下载生成后的 PDF
- 返回一个任务状态查询接口和一个临时下载链接

它不是同步接口。

正确的使用方式是：

1. 你的 SaaS 先创建任务
2. 再轮询任务状态
3. 任务完成后拿到 `download_url`
4. 由你的 SaaS 下载 PDF，或者把下载地址返回给前端

## 2. 服务端行为约束

对接前请先理解这几个固定约束：

1. 服务同一时刻只执行 1 个任务
2. 允许多个请求连续提交
3. 后续请求会进入内部 FIFO 队列
4. 新任务不会并发调用 NotebookLM
5. 下载链接是临时的，不保证长期有效
6. 如果 NotebookLM 登录态过期，任务会失败

这意味着：

- 你们前端要接受“需要等待”的产品形态
- 你们后端要有轮询逻辑
- 不要把这个接口当成秒级同步生成接口

## 3. 鉴权方式

所有业务接口都需要在请求头带上：

```http
X-API-Token: <服务端分配给你的固定 token>
```

如果 token 错误，会返回：

```http
401 Unauthorized
```

## 4. 接口总览

### 4.1 创建任务

```http
POST /v1/pdf-jobs
Content-Type: multipart/form-data
```

### 4.2 查询任务

```http
GET /v1/pdf-jobs/{job_id}
```

### 4.3 取消任务

```http
POST /v1/pdf-jobs/{job_id}/cancel
```

### 4.4 下载结果

```http
GET /downloads/{token}
```

### 4.5 健康检查

```http
GET /healthz
```

## 5. 创建任务接口

### 请求

`multipart/form-data`

字段如下：

- `file`
  必填，用户上传的文件
- `title`
  可选，任务标题
- `instructions`
  可选，额外生成说明
- `deck_format`
  可选，当前支持：
  - `detailed_deck`
  - `presenter_slides`
- `deck_length`
  可选，当前支持：
  - `default`
  - `short`

### 请求示例：curl

```bash
curl -X POST "https://your-pdf-service.example.com/v1/pdf-jobs" \
  -H "X-API-Token: YOUR_TOKEN" \
  -F "file=@example.pdf" \
  -F "title=2026 Q1 行业分析" \
  -F "instructions=请生成适合管理层汇报的中文 PDF" \
  -F "deck_format=detailed_deck" \
  -F "deck_length=default"
```

### 请求示例：Node.js

```ts
import fs from "node:fs";
import FormData from "form-data";
import fetch from "node-fetch";

async function createPdfJob() {
  const form = new FormData();
  form.append("file", fs.createReadStream("./example.pdf"));
  form.append("title", "2026 Q1 行业分析");
  form.append("instructions", "请生成适合管理层汇报的中文 PDF");
  form.append("deck_format", "detailed_deck");
  form.append("deck_length", "default");

  const response = await fetch("https://your-pdf-service.example.com/v1/pdf-jobs", {
    method: "POST",
    headers: {
      "X-API-Token": process.env.NOTEBOOKLM_PDF_TOKEN || "",
      ...form.getHeaders(),
    },
    body: form,
  });

  if (!response.ok) {
    throw new Error(`Create job failed: ${response.status} ${await response.text()}`);
  }

  return response.json();
}
```

### 成功返回

```json
{
  "job_id": "6f4f8d4d5f164b52a7f8f8c21f8f3abc",
  "status": "queued",
  "queue_position": 1,
  "created_at": "2026-03-18T12:00:00+00:00"
}
```

### 返回字段说明

- `job_id`
  任务唯一 ID，后续查询和取消都要用它
- `status`
  初始固定为 `queued`
- `queue_position`
  当前排队位置，`1` 代表正在队列头部等待或即将执行
- `created_at`
  任务创建时间，UTC ISO 8601

### 错误返回

#### 401

```json
{"detail":"Unauthorized"}
```

#### 422

例如 `deck_format` 非法：

```json
{"detail":"Invalid deck_format"}
```

#### 429 队列已满

```json
{
  "detail": {
    "error_code": "queue_full"
  }
}
```

## 6. 查询任务接口

### 请求

```http
GET /v1/pdf-jobs/{job_id}
```

### 请求示例

```bash
curl "https://your-pdf-service.example.com/v1/pdf-jobs/6f4f8d4d5f164b52a7f8f8c21f8f3abc" \
  -H "X-API-Token: YOUR_TOKEN"
```

### 返回结构

```json
{
  "job_id": "6f4f8d4d5f164b52a7f8f8c21f8f3abc",
  "status": "waiting_generation",
  "queue_position": null,
  "download_url": null,
  "error_code": null,
  "error_message": null,
  "created_at": "2026-03-18T12:00:00+00:00",
  "updated_at": "2026-03-18T12:03:20+00:00",
  "started_at": "2026-03-18T12:00:05+00:00",
  "finished_at": null
}
```

### 字段说明

- `job_id`
  任务 ID
- `status`
  当前任务状态
- `queue_position`
  仅在 `queued` 时可能有值
- `download_url`
  仅在 `completed` 时有值
- `error_code`
  失败时的稳定错误码
- `error_message`
  失败时的辅助说明
- `created_at`
  任务创建时间
- `updated_at`
  最后更新时间
- `started_at`
  开始执行时间
- `finished_at`
  终态时间

## 7. 任务状态定义

### 排队态

- `queued`

说明：
任务已创建，文件已接收，但还没有开始执行。

### 执行态

- `creating_notebook`
- `uploading_source`
- `waiting_source_ready`
- `generating_pdf`
- `waiting_generation`
- `downloading_pdf`

说明：
任务已开始实际调用 NotebookLM。

### 终态

- `completed`
- `failed`
- `cancelled`

### 过渡态

- `cancel_requested`

说明：
表示运行中的任务收到了取消请求，但服务不会立即强杀 NotebookLM 远端任务；后台会继续把清理做完，最后通常会进入 `cancelled`。

## 8. 取消任务接口

### 请求

```http
POST /v1/pdf-jobs/{job_id}/cancel
```

### 行为说明

#### 如果任务还在排队

- 会立刻从队列中移除
- 状态变为 `cancelled`

#### 如果任务已经开始执行

- 状态先变成 `cancel_requested`
- 后台继续做必要清理
- 最终不会对外暴露 `download_url`

### 请求示例

```bash
curl -X POST "https://your-pdf-service.example.com/v1/pdf-jobs/6f4f8d4d5f164b52a7f8f8c21f8f3abc/cancel" \
  -H "X-API-Token: YOUR_TOKEN"
```

## 9. 下载结果接口

### 使用方式

当 `GET /v1/pdf-jobs/{job_id}` 返回：

```json
{
  "status": "completed",
  "download_url": "https://your-pdf-service.example.com/downloads/xxxxx"
}
```

你的 SaaS 可以：

1. 由后端服务端下载 PDF
2. 或把这个地址返回给前端，让前端直接下载

### 注意事项

- 下载地址有 TTL，会过期
- 过期后返回 404
- 不要把这个链接当永久资源地址保存
- 如果业务上要长期保留，建议 SaaS 自己下载后转存到你们自己的对象存储

## 10. 推荐的对接时序

你们的 SaaS 后端建议按这个流程编码。

### 步骤 1：上传文件并创建任务

调用 `POST /v1/pdf-jobs`

### 步骤 2：把 `job_id` 保存到你们自己的业务表

建议字段至少包括：

- `job_id`
- `source_file_id` 或 `source_document_id`
- `status`
- `download_url`
- `created_at`
- `finished_at`
- `error_code`
- `error_message`

### 步骤 3：开始轮询

轮询策略建议：

- 前 1 分钟：每 3 秒轮询一次
- 之后：每 5 到 10 秒轮询一次
- 总超时：由你们业务决定，比如 30 分钟

### 步骤 4：遇到终态后停止轮询

- `completed`：取 `download_url`
- `failed`：记录失败原因
- `cancelled`：标记任务取消

### 步骤 5：成功后立即下载并转存

如果你们需要长期保留结果，推荐你们后端在拿到 `download_url` 后立即下载到自己的存储系统。

## 11. 推荐的 SaaS 后端封装

建议你们不要在业务代码里到处手写 HTTP 请求，而是封一个统一的 client。

建议接口大概像这样：

```ts
interface CreatePdfJobParams {
  filePath: string;
  title?: string;
  instructions?: string;
  deckFormat?: "detailed_deck" | "presenter_slides";
  deckLength?: "default" | "short";
}

interface PdfJobStatus {
  jobId: string;
  status: string;
  queuePosition?: number | null;
  downloadUrl?: string | null;
  errorCode?: string | null;
  errorMessage?: string | null;
  createdAt: string;
  updatedAt: string;
  startedAt?: string | null;
  finishedAt?: string | null;
}
```

推荐 client 方法：

- `createPdfJob(params)`
- `getPdfJob(jobId)`
- `cancelPdfJob(jobId)`
- `downloadPdf(url)`

## 12. 推荐的错误处理策略

### 12.1 创建任务阶段

#### `401 Unauthorized`

含义：
SaaS 配置的 `X-API-Token` 错了。

处理：
- 立即报警
- 不要重试

#### `422`

含义：
请求参数错误。

处理：
- 改代码或修正参数
- 不要自动重试

#### `429 queue_full`

含义：
队列满了。

处理建议：
- 对用户提示“当前任务较多，请稍后再试”
- 可以由业务层延迟几分钟后再重新提交
- 不建议无限快速重试

### 12.2 查询任务阶段

#### `failed`

常见 `error_code`：

- `auth_expired`
- `rate_limited`
- `timeout`
- `network_error`
- `processing_failed`
- `queue_expired`

建议处理：

- `auth_expired`
  视为服务侧故障，通知运维
- `rate_limited`
  可提示稍后重试
- `timeout`
  可以记录为超时失败
- `network_error`
  可按业务规则重试提交
- `processing_failed`
  记录并人工排查
- `queue_expired`
  说明排队过久，可选择重新发起

## 13. 建议你们前端展示的状态文案

如果 SaaS 前端也要展示任务进度，建议把服务状态映射成更友好的文案。

例如：

- `queued` -> 排队中
- `creating_notebook` -> 正在创建工作区
- `uploading_source` -> 正在上传材料
- `waiting_source_ready` -> 正在解析材料
- `generating_pdf` -> 正在生成演示文稿
- `waiting_generation` -> 正在等待 NotebookLM 完成
- `downloading_pdf` -> 正在导出 PDF
- `completed` -> 已完成
- `failed` -> 生成失败
- `cancel_requested` -> 正在取消
- `cancelled` -> 已取消

## 14. 一个完整的对接示例

下面给你们一个最常见的后端工作流：

1. 用户在 SaaS 页面上传文件
2. SaaS 后端把文件转发给 PDF 微服务
3. 微服务返回 `job_id`
4. SaaS 后端保存 `job_id`
5. 定时任务或异步 worker 每隔几秒查询一次状态
6. 如果 `status = completed`
   - 下载 `download_url`
   - 存到你们自己的对象存储
   - 更新业务记录为完成
7. 如果 `status = failed`
   - 记录 `error_code`
   - 更新业务记录为失败
8. 如果用户中途取消
   - SaaS 调用 `/cancel`
   - 更新自己业务系统状态

## 15. SaaS 团队最容易踩的坑

### 坑 1：把它当同步接口

不要在一个前端请求里一直等到 PDF 完成。
正确方式是异步任务 + 轮询。

### 坑 2：不保存 `job_id`

`job_id` 是整个链路的唯一标识，必须保存。

### 坑 3：拿到 `download_url` 不立即处理

下载地址会过期。需要长期保留的话，请尽快转存。

### 坑 4：队列满了还疯狂重试

如果服务返回 `queue_full`，说明当前供给不足。应该走延迟重试，而不是秒级暴力重试。

### 坑 5：把失败都当成可重试

有些失败适合重试，比如短暂网络错误；有些不适合，比如参数错误、认证失效、源文件不合格。

## 16. 推荐给 SaaS 团队的开发任务拆分

你可以把这份文档直接转给团队，并建议他们按下面拆分：

### 后端同学

负责：

- 封装 HTTP client
- 提交任务
- 轮询状态
- 下载结果
- 转存 PDF
- 记录业务状态

### 前端同学

负责：

- 上传入口
- 状态展示
- 排队中的用户提示
- 成功后的下载入口
- 失败和取消的提示

### 运维 / 平台同学

负责：

- 配置 API Token
- 配置服务地址
- 健康检查与告警
- 队列积压监控

## 17. 最后给 SaaS 团队的一句落地建议

真正稳定的接法不是“前端拿文件直接调这个服务”，而是：

- 前端上传给 SaaS 自己后端
- SaaS 后端再调用 PDF 微服务
- SaaS 后端负责保存 `job_id`、轮询、转存结果、统一返回前端状态

这样你们后面要做鉴权、审计、重试、限流、转存、计费，都会更容易。
