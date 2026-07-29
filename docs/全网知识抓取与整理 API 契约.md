# 全网知识抓取与整理 API 契约

> 这是 ra-miniapp 和 ra-webapp 的提议契约。实现前需以 FastAPI OpenAPI 为最终来源；本契约中的接口目前尚未在后端实现。

## 1. 通用约定

- Base path：/api/v1
- 新能力前缀：/api/v1/knowledge
- 鉴权：Authorization: Bearer <jwt>
- 默认响应：application/json; charset=utf-8
- 时间：ISO 8601 UTC，例如 2026-07-26T10:00:00Z
- 分页：cursor 分页，响应使用 items 和 next_cursor
- 创建任务：返回 202 Accepted
- 取消和重试使用幂等操作，重复调用不会产生第二个任务

除非特别说明，所有资源只返回当前 JWT 用户拥有的内容。

## 2. 对话联网与个人知识沉淀

### 2.1 发送消息

现有 POST /api/v1/chat/sessions/{session_id}/messages 保留，但请求增加联网和沉淀策略：

~~~json
{
  "content": "最近 OpenAI 发布了哪些重要更新？",
  "document_id": null,
  "web_mode": "auto",
  "knowledge_mode": "auto",
  "search_options": {
    "freshness": "30d",
    "top_k": 5,
    "language": "zh-CN"
  }
}
~~~

字段说明：

- web_mode：auto | off | always。auto 由系统根据时效性、问题类型和本地召回结果决定。
- knowledge_mode：auto | off | ask | always。auto 只保存实际引用的来源；off 不沉淀；ask 返回保存建议；always 保存搜索计划中通过质量门禁的来源。
- search_options.freshness：可选 day、week、month、year 或自定义时间范围。
- search_options.top_k：搜索候选页面数量，服务端必须设置上限。

完成时返回：

~~~json
{
  "status": "completed",
  "message": {
    "id": 120,
    "role": "assistant",
    "content": "回答内容",
    "refs": [
      {
        "citation_id": "web_1",
        "ref_type": "web",
        "document_id": 301,
        "document_version_id": 3011,
        "title": "网页标题",
        "url": "https://example.com/article",
        "canonical_url": "https://example.com/article",
        "quote": "原文引用",
        "source_domain": "example.com",
        "published_at": "2026-07-27T08:00:00Z",
        "fetched_at": "2026-07-28T10:00:00Z"
      }
    ],
    "metadata": {
      "web_searched": true,
      "knowledge_mode": "auto",
      "knowledge_ingest_job_id": "kjob_01J..."
    }
  }
}
~~~

联网任务超过同步预算时返回：

~~~json
{
  "status": "thinking",
  "thinking_id": "turn_01J...",
  "phase": "web_search",
  "message_id": 119
}
~~~

### 2.2 Chat thinking

GET /api/v1/chat/thinking/{thinking_id}

运行中：

~~~json
{
  "status": "running",
  "thinking_id": "turn_01J...",
  "phase": "page_fetching",
  "counters": {"searched": 5, "fetched": 3, "accepted": 2}
}
~~~

完成后：

~~~json
{
  "status": "completed",
  "thinking_id": "turn_01J...",
  "message": {
    "id": 120,
    "role": "assistant",
    "content": "回答内容",
    "refs": []
  },
  "knowledge_ingest_job_id": "kjob_01J..."
}
~~~

失败时必须返回 error.code、error.message 和 retryable，不能固定返回 not_found。

### 2.3 Chat events

GET /api/v1/chat/thinking/{thinking_id}/events?after_seq=0&limit=100

事件类型：

~~~text
chat.started
local.retrieval.completed
web.search.started
web.search.completed
page.fetching
page.accepted
answer.started
answer.completed
knowledge.ingest.started
knowledge.ingest.completed
chat.failed
~~~

### 2.4 Web search run

GET /api/v1/knowledge/web-search-runs/{run_id}

返回搜索查询、provider、候选结果、实际抓取来源和当前用户是否已保存：

~~~json
{
  "id": "wsr_01J...",
  "session_id": 12,
  "message_id": 119,
  "query": "OpenAI recent updates",
  "provider": "search-provider",
  "status": "completed",
  "results": [
    {
      "rank": 1,
      "title": "网页标题",
      "url": "https://example.com/article",
      "snippet": "搜索摘要",
      "used_in_answer": true,
      "document_id": 301
    }
  ],
  "created_at": "2026-07-28T10:00:00Z"
}
~~~

### 2.5 手动保存搜索来源

POST /api/v1/knowledge/web-search-runs/{run_id}/save

用于 knowledge_mode=ask 或用户手动保存未自动沉淀的来源。

~~~json
{
  "result_ids": [1, 3],
  "organize": true
}
~~~

返回 202：

~~~json
{
  "knowledge_ingest_job_id": "kjob_01J...",
  "status": "queued"
}
~~~

### 2.6 个人知识沉淀任务

GET /api/v1/knowledge/ingest-jobs/{job_id}

返回：

~~~json
{
  "id": "kjob_01J...",
  "origin": "chat_search",
  "message_id": 119,
  "status": "partially_succeeded",
  "document_ids": [301],
  "counters": {
    "accepted": 2,
    "organized": 1,
    "indexed": 1,
    "failed": 0
  }
}
~~~

POST /api/v1/knowledge/ingest-jobs/{job_id}/retry 用于重试失败整理或索引。

POST /api/v1/knowledge/ingest-jobs/{job_id}/cancel 用于取消尚未完成的整理和索引任务；已经保存的原始快照不回滚。

DELETE /api/v1/knowledge/documents/{document_id} 必须同时删除当前用户可见的文档版本、知识卡片、证据关系、向量索引和允许删除的原始快照。

## 3. 枚举

### Source

~~~
seed_type: url | sitemap | rss
status: active | paused | archived
~~~

### Crawl job

~~~
status: queued | running | cancelling | succeeded | partially_succeeded | failed | cancelled
~~~

### Page

~~~
status: queued | fetching | fetched | normalized | organized | indexed | skipped | failed
~~~

### Document / card

~~~
quality_status: pending | accepted | review_required | rejected
card_status: pending | ready | failed | review_required
~~~

### Chat turn

~~~
status: queued | running | waiting_web | answering | completed | failed | cancelled
web_mode: auto | off | always
knowledge_mode: auto | off | ask | always
~~~

## 4. Sources

### POST /api/v1/knowledge/sources

创建或保存可复用来源。此接口只保存配置，不立即抓取。

Request：

~~~json
{
  "name": "OpenAI News",
  "seed_type": "url",
  "seed_url": "https://example.com/news",
  "allowed_domains": ["example.com"],
  "policy": {
    "max_depth": 2,
    "max_pages_per_run": 50,
    "same_site_only": true,
    "respect_robots": true,
    "render": "auto",
    "include_patterns": ["/news/"],
    "exclude_patterns": ["/login", "/account"],
    "max_concurrency": 2,
    "delay_ms": 1000
  },
  "domain": "technical",
  "tags": ["news", "ai"]
}
~~~

Response 201：

~~~json
{
  "id": "src_01J...",
  "name": "OpenAI News",
  "seed_type": "url",
  "seed_url": "https://example.com/news",
  "allowed_domains": ["example.com"],
  "policy": {
    "max_depth": 2,
    "max_pages_per_run": 50,
    "same_site_only": true,
    "respect_robots": true,
    "render": "auto",
    "max_concurrency": 2,
    "delay_ms": 1000
  },
  "domain": "technical",
  "tags": ["news", "ai"],
  "status": "active",
  "created_at": "2026-07-26T10:00:00Z",
  "last_run": null
}
~~~

### GET /api/v1/knowledge/sources

Query：

~~~
status=active&limit=20&cursor=...
~~~

Response：

~~~json
{
  "items": [],
  "next_cursor": null
}
~~~

### GET /api/v1/knowledge/sources/{source_id}

返回 source 配置、最近 10 次运行摘要和当前统计。

### PATCH /api/v1/knowledge/sources/{source_id}

允许修改 name、policy、domain、tags、status。不允许通过 PATCH 改写历史任务和快照。

## 5. Crawl jobs

### POST /api/v1/knowledge/crawl-jobs

启动抓取任务。推荐使用 Idempotency-Key header。

Request：

~~~json
{
  "source_id": "src_01J...",
  "options": {
    "max_pages": 50,
    "max_depth": 2,
    "render": "auto",
    "organize": true,
    "publish": false,
    "force_refresh": false
  }
}
~~~

也允许不创建 source 直接启动一次性任务：

~~~json
{
  "seed": {
    "type": "url",
    "url": "https://example.com/article"
  },
  "options": {
    "max_pages": 1,
    "max_depth": 0,
    "render": "auto",
    "organize": true,
    "publish": false
  }
}
~~~

Response 202：

~~~json
{
  "id": "job_01J...",
  "status": "queued",
  "source_id": "src_01J...",
  "options": {
    "max_pages": 50,
    "max_depth": 2,
    "render": "auto",
    "organize": true,
    "publish": false
  },
  "counters": {
    "discovered": 0,
    "scheduled": 0,
    "fetched": 0,
    "accepted": 0,
    "organized": 0,
    "indexed": 0,
    "failed": 0,
    "skipped": 0
  },
  "created_at": "2026-07-26T10:00:00Z",
  "links": {
    "self": "/api/v1/knowledge/crawl-jobs/job_01J...",
    "events": "/api/v1/knowledge/crawl-jobs/job_01J.../events"
  }
}
~~~

校验失败返回 422；SSRF、禁止域名或策略不允许返回 400；超过用户额度返回 429。

### GET /api/v1/knowledge/crawl-jobs

Query：

~~~
status=running&source_id=src_01J&limit=20&cursor=...
~~~

### GET /api/v1/knowledge/crawl-jobs/{job_id}

Response：

~~~json
{
  "id": "job_01J...",
  "status": "partially_succeeded",
  "phase": "organizing",
  "source_id": "src_01J...",
  "counters": {
    "discovered": 50,
    "scheduled": 50,
    "fetched": 48,
    "accepted": 42,
    "organized": 40,
    "indexed": 40,
    "failed": 2,
    "skipped": 6
  },
  "error_summary": [
    {"code": "HTTP_429", "count": 2, "message": "Remote site rate limited requests"}
  ],
  "created_at": "2026-07-26T10:00:00Z",
  "started_at": "2026-07-26T10:00:03Z",
  "finished_at": "2026-07-26T10:04:12Z"
}
~~~

### POST /api/v1/knowledge/crawl-jobs/{job_id}/cancel

Response 202：返回最新 job。取消是协作式的；已经写入的 snapshot 和 document 不回滚。

### POST /api/v1/knowledge/crawl-jobs/{job_id}/retry

只允许 failed 或 partially_succeeded。默认仅重试失败页面，也可传：

~~~json
{
  "mode": "failed_pages"
}
~~~

## 6. Events

### GET /api/v1/knowledge/crawl-jobs/{job_id}/events

Query：after_seq=0&limit=100

Response：

~~~json
{
  "items": [
    {
      "seq": 12,
      "type": "page.accepted",
      "created_at": "2026-07-26T10:01:09Z",
      "payload": {
        "url": "https://example.com/news/1",
        "document_id": 301,
        "quality_score": 0.91
      }
    },
    {
      "seq": 13,
      "type": "job.progress",
      "created_at": "2026-07-26T10:01:10Z",
      "payload": {
        "phase": "organizing",
        "completed": 12,
        "total_known": 42
      }
    }
  ],
  "next_after_seq": 13,
  "has_more": false
}
~~~

推荐事件类型：job.started、frontier.discovered、page.fetching、page.accepted、page.skipped、page.failed、document.created、card.ready、job.progress、job.completed、job.failed。

## 7. Knowledge documents

### GET /api/v1/knowledge/documents

Query：

~~~
keyword=vector&source_id=src_01J&quality_status=accepted
&card_status=ready&created_after=2026-07-01T00:00:00Z
&limit=20&cursor=...
~~~

Response：

~~~json
{
  "items": [
    {
      "id": 301,
      "title": "页面标题",
      "canonical_url": "https://example.com/news/1",
      "domain": "technical",
      "tags": ["news", "ai"],
      "quality_status": "accepted",
      "card_status": "ready",
      "summary": "摘要",
      "chunk_count": 8,
      "source": {"source_id": "src_01J...", "host": "example.com"},
      "fetched_at": "2026-07-26T10:01:08Z",
      "updated_at": "2026-07-26T10:01:08Z"
    }
  ],
  "next_cursor": null
}
~~~

### GET /api/v1/knowledge/documents/{document_id}

返回现有文档详情之外，增加：

~~~json
{
  "id": 301,
  "current_version": {
    "id": 3011,
    "version_no": 2,
    "content_hash": "sha256:...",
    "quality_score": 0.91,
    "fetched_at": "2026-07-26T10:01:08Z",
    "source_snapshot_id": 881
  },
  "source": {
    "url": "https://example.com/news/1",
    "canonical_url": "https://example.com/news/1",
    "host": "example.com",
    "adapter": "crawl4ai",
    "http_status": 200,
    "content_type": "text/html"
  },
  "quality": {
    "status": "accepted",
    "score": 0.91,
    "signals": {"main_text_ratio": 0.74, "language": "zh-CN", "soft_404": false}
  },
  "card": {"id": "card_01J...", "status": "ready"}
}
~~~

### POST /api/v1/knowledge/documents/{document_id}/reorganize

重新执行知识整理，不重新抓取页面。

Request：

~~~json
{
  "version_id": 3011,
  "sections": ["summary", "topics", "facts", "faq"]
}
~~~

Response 202：

~~~json
{
  "job_id": "job_organize_01J...",
  "status": "queued",
  "document_id": 301
}
~~~

### POST /api/v1/knowledge/documents/{document_id}/publish

Request：

~~~json
{
  "published": true,
  "version_id": 3011
}
~~~

发布前必须通过质量门禁；不通过时返回 409，并在 detail.code 中返回 QUALITY_REVIEW_REQUIRED。

## 8. Knowledge cards

### GET /api/v1/knowledge/cards/{card_id}

返回结构化卡片、模型运行信息和证据：

~~~json
{
  "id": "card_01J...",
  "document_id": 301,
  "document_version_id": 3011,
  "status": "ready",
  "title": "页面主题",
  "summary": "摘要",
  "topics": ["topic-a"],
  "entities": [{"name": "Entity", "type": "product"}],
  "facts": [
    {
      "statement": "事实内容",
      "confidence": 0.87,
      "evidence": [
        {
          "chunk_id": 9001,
          "quote": "原文引用",
          "locator": {"start_offset": 120, "end_offset": 145}
        }
      ]
    }
  ],
  "faq": [{"question": "问题", "answer": "回答"}],
  "organizer": {"model": "kimi-model", "prompt_version": "knowledge-v1"},
  "created_at": "2026-07-26T10:01:20Z"
}
~~~

## 9. 错误格式

统一错误格式：

~~~json
{
  "detail": {
    "code": "DOMAIN_NOT_ALLOWED",
    "message": "The target domain is not allowed by this source policy.",
    "request_id": "req_01J...",
    "retryable": false,
    "fields": {"seed.url": "https://example.com/private"}
  }
}
~~~

建议错误码：

~~~
INVALID_URL
SSRF_BLOCKED
DOMAIN_NOT_ALLOWED
ROBOTS_BLOCKED
QUOTA_EXCEEDED
JOB_NOT_CANCELLABLE
QUALITY_REVIEW_REQUIRED
FETCH_TIMEOUT
HTTP_429
HTTP_4XX
HTTP_5XX
RENDER_FAILED
ORGANIZER_SCHEMA_INVALID
INDEX_WRITE_FAILED
~~~

## 10. 前端最小联调流程

### Web

~~~
发送对话 -> auto 判断是否联网 -> 轮询 thinking
-> 查看带引用回答 -> 查看知识沉淀状态 -> 后续进入个人知识库

深度采集：

创建来源 -> 点击立即抓取 -> 轮询 crawl job -> 查看事件/错误
-> 浏览知识文档 -> 查看来源和卡片 -> 发布或重新整理
~~~

### Miniapp

~~~
发送问题 -> 等待联网回答 -> 查看引用
-> 查看个人知识沉淀状态 -> 基于文档继续追问

小程序主动抓取：

输入单个 URL -> 启动一次性 job -> 任务页轮询
-> 完成后跳转知识详情 -> 基于文档进入现有聊天
~~~

小程序第一期不建议暴露复杂的抓取策略表单，只开放 URL、是否抓取同站链接、最大页面数和是否自动整理；Web 端再提供完整策略配置。

## 11. 与现有 API 的兼容

- 现有 POST /api/v1/documents 保留，后续可内部改为创建 ingest job，但响应兼容 DocumentSchema 的迁移应单独评审。
- 现有 /api/v1/search 继续搜索当前用户的已发布文档；抓取文档只有 published=true 后才进入默认搜索。
- 现有聊天引用继续兼容 document_id，但必须扩展 citation_id、ref_type、canonical_url、document_version_id、quote 和 fetched_at。
- 现有 chat/thinking 占位接口必须改为真实的持久化 ChatTurn 状态查询。
- Agent/MCP 不得直接向全局 Chroma 或 Memory collection 写入个人知识；必须调用带 user_id 的 PersonalKnowledgeService。
- 前端当前的本地文档关键词过滤可以保留，新增接口稳定后再迁移为服务端分页过滤。
