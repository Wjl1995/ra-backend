# ReActAgent 线上化项目计划与技术方案

> 文档定位：单人可落地、低代码优先、最小运维成本的线上化路线图
> 适用对象：开发者（1 人）、运营方（初期=开发者本人）
> 项目目标：将本地 ReAct + 知识库学习项目升级为面向真实用户的"垂直领域智能助手"，含 C 端微信小程序 + B 端低代码后台

---

## 1. 项目目标与成功度量

### 1.1 目标
- **产品定位**：垂直领域（示例：营销活动）智能问答助手
- **用户价值**：打开微信即可"问专家"，获取基于内部知识库的引用回答
- **运营价值**：运营方上传 Word/PDF/PPT/Excel/Markdown → 自动入库 → 立即可被用户检索

### 1.2 成功度量（上线 2 个月内）

| 指标 | 目标 |
| --- | --- |
| 知识库文档数 | ≥ 50 份 |
| 注册用户 | ≥ 200 人 |
| 周活跃对话轮次 | ≥ 300 |
| 用户主观满意（点赞/收藏） | ≥ 70% |
| 核心服务可用率 | ≥ 99% |

---

## 2. 产品功能范围（MVP + 二期）

### 2.1 MVP 范围（一期必做）

#### C 端 - 微信小程序
- 微信登录（openid）
- 会话：创建 / 多轮对话 / 删除 / 继续
- 对话页：用户气泡 + AI 气泡 + 引用文档小卡片
- 知识库浏览与搜索（关键词 / 语义）
- 我的：历史会话列表、每日配额、关于
- TabBar：首页 / 知识库 / 我的

#### B 端 - 运营后台（SQLAdmin 低代码）
- 登录：用户名 + 密码（管理后台独立鉴权）
- 文档管理：列表 / 上传 / 解析状态 / 删除 / 编辑元数据
- 文档分集合 / 领域 / 标签
- Chunk 查看：文档拆成的片段列表，支持浏览与搜索
- 用户管理：列表 / 封禁 / 配额调整
- 消息审计：查看会话内容、命中引用
- 反馈 / 举报处理：查看用户反馈
- 系统配置：模型名称、Temperature、System Prompt 等

### 2.2 二期范围（上线后迭代，不急）
- 流式响应（SSE 打字机效果）
- Markdown 富文本渲染（接入 towxml）
- 语音输入 + 语音识别
- 图片识别 / OCR
- 分享小程序卡片、朋友圈海报
- 深色模式、字体大小
- 多模型切换（Kimi / DeepSeek / 通义 / 豆包）
- 多租户 / 团队协作
- 独立付费体系（微信支付）
- 运营数据看板（对话量、token 数、热门问题）

---

## 3. 总体架构

### 3.1 架构图（文字版）

```
                          ┌──────────────────────┐
                          │   微信用户小程序       │
                          │  原生 WXML/WXSS/JS     │
                          │  Vant Weapp 组件库     │
                          └──────────┬───────────┘
                                     │ HTTPS / JSON
                                     │
                          ┌──────────▼───────────┐
                          │   Caddy（反代+SSL）    │
                          └──────────┬───────────┘
                                     │
                     ┌───────────────▼───────────────┐
                     │   FastAPI + Uvicorn (Docker)    │
                     │  ┌──────────────────────────┐   │
                     │  │ /api/v1/auth/wx-login    │   │  ← 微信 code → openid → JWT
                     │  │ /api/v1/chat/...         │   │  ← 会话 / 消息 / 流式
                     │  │ /api/v1/documents/...    │   │  ← 文档 CRUD / 上传 / 解析
                     │  │ /api/v1/search           │   │  ← 语义搜索
                     │  │ /api/v1/me               │   │  ← 个人信息 / 配额
                     │  │ /admin                   │   │  ← SQLAdmin 后台(独立鉴权)
                     │  └──────────────────────────┘   │
                     │  ┌──────────────┐                │
                     │  │ ReAct Agent  │                │  ← core(复用现有)
                     │  │ + LLM API    │                │  ← Kimi / DeepSeek
                     │  │ + 记忆系统    │                │  ← 长/短期记忆
                     │  └──────────────┘                │
                     └──┬───────────┬───────────┬───────┘
                        │           │           │
              ┌─────────▼──┐ ┌──────▼────┐ ┌───▼────────┐
              │ SQLite      │ │ ChromaDB /│ │  LLM API   │
              │ 用户/会话/  │ │ Qdrant    │ │ Kimi/...   │
              │ 文档/消息   │ │ 向量      │ │ (外部)     │
              └────────────┘ └───────────┘ └────────────┘
```

### 3.2 部署物理视图（一台机搞定）

```
一台 2C4G 腾讯云 Lighthouse（Ubuntu 22.04 + Docker 基础镜像）
├─ /var/react-agent/
│  ├─ data/db.sqlite3          ← SQLite 业务库
│  ├─ data/chroma_data/        ← ChromaDB 向量库
│  └─ data/uploads/            ← 用户上传原始文档
├─ Caddy (容器)                ← 80/443 → 自动 ACME
└─ app (容器)                  ← FastAPI + 全部业务代码
```

---

## 4. 技术选型决策

### 4.1 核心选型

| 层 | 选型 | 理由 |
| --- | --- | --- |
| 前端小程序 | **微信原生小程序 + Vant Weapp** | 审核最稳、学习成本最低、一个人够用 |
| 后端框架 | **FastAPI** | Python 生态与现有 react-agent 无缝衔接；自动生成 Swagger 便于联调 |
| 后端语言 | **Python 3.11+** | 与现有代码一致，无额外学习 |
| 业务数据库 | **SQLite** | 零运维；单人够用；切 PostgreSQL 只需改 `DATABASE_URL` |
| 向量库 | **ChromaDB（文件模式）** | 与当前项目一致；二期看情况切 Qdrant（Docker 或 Qdrant Cloud） |
| 后台管理 | **SQLAdmin** | 基于 SQLAlchemy 的低代码后台，注册一个 `ModelView` 即得完整 CRUD，0 前端代码 |
| 鉴权 | **JWT（python-jose）** + 后台独立 Basic/Session 登录 | 小程序 JWT、后台独立 session，两套不互相干扰 |
| LLM | **Kimi（moonshot.cn）**，配置可切 DeepSeek/通义 | 价格合理、中文表现好、与当前项目一致 |
| 内容安全 | **DashScope / 百度 AIP 文本安全检测**（免费额度够用） | 小程序审核要求必须有内容审核 |
| 部署 | **Docker Compose + 一台云服务器** | 单人运维成本最低 |
| 反代/HTTPS | **Caddy** | 单文件配置，自动 Let's Encrypt 证书续签 |
| 备份 | 每日 `sqlite3 .dump` + `tar chroma_data` → 复制到本地或对象存储 | 脚本 10 行以内 |
| 异常监控 | **Sentry Free Tier** | 捕获线上错误堆栈，免费用 |

### 4.2 明确不选的方案

| 方案 | 不选原因 |
| --- | --- |
| Uni-app / Taro / React Native | 学习成本高，单人项目多端适配性价比低 |
| 微信云开发 | 冷启动 + 知识库/向量检索不便 |
| Kubernetes / K8s | 过度设计，1 万 DAU 之前不需要 |
| 云托管 PostgreSQL RDS | 一期费用高且无必要 |
| Redis / Kafka / Elasticsearch | 一期零收益 |

---

## 5. 代码仓组织（两仓分离）

### 5.1 仓库拆分原则

- **两仓独立版本管理、独立发版、独立 CI/CD**
- 后端仓库承担"核心业务 + AI 能力 + 数据"，不耦合任何前端
- 小程序仓库是纯前端工程，只依赖后端接口契约（API 文档 / Swagger）
- 通过**接口版本号（`/api/v1/...`）+ 接口契约文档** 保持两端解耦；后端接口变更须在 CHANGELOG 中同步告知前端

### 5.2 仓库一：后端（ReAct Agent 后端 + 知识库）

```
仓库名：ReActAgent  （即当前仓库 github.com/Wjl1995/ReActAgent）
定位：后端服务 + 核心 AI 引擎 + 低代码后台 + 数据
```

```
ReActAgent/
├── apps/
│   └── backend/                     ← FastAPI 后端（新增目录）
│       ├── main.py                  ← FastAPI 实例；挂载路由 + SQLAdmin
│       ├── config.py                ← 配置（.env 环境变量）
│       ├── database.py              ← SQLAlchemy Engine / Session
│       ├── models.py                ← User / Session / Message / Document / Chunk / Feedback
│       ├── schemas.py               ← Pydantic 请求/响应
│       ├── dependencies.py          ← get_db / get_current_user / admin_auth
│       ├── auth.py                  ← wx.login → openid → JWT
│       ├── content_security.py      ← 文本安全检测
│       ├── version.py               ← __version__ + API_VERSION = "v1"
│       ├── services/
│       │   ├── chat_service.py      ← ReAct 对话封装（按用户/会话隔离）
│       │   ├── document_service.py  ← 文档上传/解析/入库/查询
│       │   └── search_service.py    ← 语义搜索（Chroma）
│       ├── api/
│       │   ├── __init__.py
│       │   ├── auth.py              ← /api/v1/auth/*
│       │   ├── chat.py              ← /api/v1/chat/*
│       │   ├── document.py          ← /api/v1/documents/*
│       │   ├── search.py            ← /api/v1/search
│       │   └── me.py                ← /api/v1/me
│       ├── admin_views.py           ← SQLAdmin ModelView 注册
│       └── admin_auth.py            ← 后台登录（OAuth2PasswordRequestForm）
├── agent/                           ← 复用现有 ReActAgent
├── knowledge/                       ← 复用现有 parsers / store / pipelines
├── memory/                          ← 复用现有 memory
├── tools/                           ← 复用现有 tool registry
├── config.py                        ← 现有全局配置（保留向后兼容常量）
├── main.py                          ← 本地 CLI（保留，与线上后端不冲突）
├── requirements.txt                 ← 扩展 fastapi / uvicorn / sqladmin / sqlalchemy / python-jose / markitdown ...
├── Dockerfile                       ← Python 3.11-slim + uvicorn
├── docker-compose.yml               ← app + caddy
├── Caddyfile                        ← 反代 + 自动 HTTPS
├── .env.example                     ← 生产示例环境变量
├── .gitignore                       ← data/ / .env / *.sqlite3
├── README.md                        ← 项目总入口说明 + 本地启动命令
├── CHANGELOG.md                     ← （新增）后端接口与版本变更记录
├── API_CONTRACT.md                  ← （新增）面向前端的接口契约摘要 + 示例
└── docs/
    ├── ONLINE_PLAN_线上化项目计划与技术方案.md    ← 本文档
    ├── ChromaDB学习报告.md
    ├── ReAct学习报告.md
    ├── MARKITDOWN_INTEGRATION.md
    ├── KNOWLEDGE_IMPORT_GUIDE.md
    └── 知识库导入指南.md
```

### 5.3 仓库二：小程序前端

```
仓库名：react-agent-miniprogram  （新建仓库，独立 Git）
定位：微信小程序纯前端；不包含任何后端 / LLM / 数据库代码
```

```
react-agent-miniprogram/
├── app.js / app.json / app.wxss     ← 小程序入口与全局配置
├── project.config.json              ← 开发者工具项目配置（写入 AppID）
├── sitemap.json                     ← 搜索引擎收录配置
├── pages/
│   ├── index/                       ← 首页（推荐问题 + 入口）
│   ├── chat/                        ← 对话页（核心）
│   ├── knowledge/                   ← 知识库列表
│   ├── knowledge-detail/            ← 文档详情
│   └── me/                          ← 我的
├── components/
│   ├── message-bubble/
│   ├── thinking-dots/
│   └── doc-ref-card/
├── utils/
│   ├── request.js                   ← 统一 wx.request（带 JWT、错误处理、401 重登录）
│   ├── auth.js                      ← wx.login → 换 openid → 保存 JWT
│   └── format.js                    ← 时间/文本格式化小工具
├── services/
│   ├── chat.js                      ← /api/v1/chat/*
│   ├── document.js                  ← /api/v1/documents/*
│   └── search.js                    ← /api/v1/search
├── config/
│   └── env.js                       ← API_BASE_URL 环境切换（开发版/体验版/正式版）
├── package.json                     ← 仅用于管理 Vant Weapp 等 npm 依赖
├── miniprogram_npm/                 ← （构建产物，由开发者工具生成；.gitignore 可选）
├── .gitignore
├── README.md                        ← 小程序本地启动与真机调试说明 + 体验版/正式版发布流程
└── CHANGELOG.md                     ← 小程序版本变更记录（用于同步微信小程序版本号）
```

### 5.4 两仓协作与版本发布流程

- **接口契约**：后端对外暴露 `/docs`（Swagger UI）+ `API_CONTRACT.md`（摘要），两端以此为准
- **版本号规则**（两端独立）：
  - 后端：`1.0.0`（语义化版本，major 变=破坏接口）
  - 小程序：`1.0.0`（与微信后台提交的版本号保持一致）
- **发版流程**：
  1. 后端：`git tag v1.0.0` → push → 在服务器 `git pull` → `docker compose up -d --build`
  2. 小程序：`git tag v1.0.0` → 微信开发者工具"上传"→ mp 后台提交审核 → 审核通过后发布
- **接口破坏约束**：一期后端接口路径统一带 `/api/v1/`（如 `/api/v1/chat/sessions/...`），如需 breaking change 引入 `/api/v2/` 并保留旧版一段时间（至少 1 个小程序审核周期）
- **联调方式**：
  - 本地开发：后端 `uvicorn apps.backend.main:app --reload` 跑在 8000；小程序开发版勾"不校验合法域名"，`config/env.js` 指向 `http://<内网IP>:8000` 或内网穿透地址
  - 体验版/正式版：`config/env.js` 指向 `https://api.你的域名.cn`
- **独立分支**：两仓库均以 `master`（或 `main`）为生产分支；开发分支 `dev`；功能分支 `feature/xxx`

---

## 6. 云服务器与部署方案

### 6.1 云服务厂商选型

**首推：腾讯云 Lighthouse（轻量应用服务器）**

| 项目 | 推荐配置 | 说明 |
| --- | --- | --- |
| 厂商 | 腾讯云 | 微信生态亲和、备案与小程序审核天然打通 |
| 规格 | **2 核 4G / 80G SSD / 4Mbps** | 最小起步；CPU <2C 会偶发 OOM |
| 镜像 | **Docker 基础镜像（Base on Ubuntu 22.04）** | 省掉装 Docker 步骤；SSH 进去即可用 |
| 地域 | 上海 / 广州 / 北京（三选一，不能改） | 选离主要用户最近的一个 |
| 时长 | 1 年（新客折扣最大） | 99-199 元/年区间常有活动价 |
| 防火墙 | 开放 22(SSH) / 80(HTTP) / 443(HTTPS)；其他全部关闭 | 安全第一 |

备选：阿里云轻量应用服务器（如果你已有阿里云账号/备案体系）。

### 6.2 开通步骤（20 分钟）

1. 注册 https://cloud.tencent.com/ （微信扫码 + 个人身份证实名）
2. 搜索"轻量应用服务器"→ 购买
3. 购买配置参考上表；镜像选择 **Docker 基础镜像**
4. 控制台 → 重置 root 密码或绑定 SSH Key
5. SSH 登录：`ssh root@公网IP`
6. 验证：`docker --version && docker compose version` 都应返回版本号

### 6.3 域名 & 备案

- 购买一个 `.cn` 或 `.top` 域名（腾讯云"域名注册"）
- 进入"网站备案"，按照指引完成个人备案（1-3 工作日）
- 配置 DNS：
  - `api.你的域名.cn` → A 记录到服务器公网 IP
  - （二期可加）`admin.你的域名.cn` → 同一 IP（Caddy 通过 SNI 分发）

### 6.4 部署脚手架（后续工程化时按此实施）

`Dockerfile`：
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "apps.backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

`docker-compose.yml`：
```yaml
services:
  app:
    build: .
    restart: unless-stopped
    volumes:
      - ./data:/app/data
    environment:
      - DATABASE_URL=sqlite:////app/data/db.sqlite3
      - CHROMA_PERSIST_DIR=/app/data/chroma_data
      - KIMI_API_KEY=${KIMI_API_KEY}
      - ADMIN_USERNAME=${ADMIN_USERNAME}
      - ADMIN_PASSWORD_HASH=${ADMIN_PASSWORD_HASH}
      - JWT_SECRET=${JWT_SECRET}
      - WECHAT_APP_ID=${WECHAT_APP_ID}
      - WECHAT_APP_SECRET=${WECHAT_APP_SECRET}
    ports:
      - "127.0.0.1:8000:8000"

  caddy:
    image: caddy:2-alpine
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data
      - caddy_config:/config

volumes:
  caddy_data:
  caddy_config:
```

`Caddyfile`：
```
api.你的域名.cn {
    reverse_proxy http://app:8000
}
```

### 6.5 日常部署

```bash
ssh root@服务器
cd /opt/react-agent
git pull
docker compose up -d --build
# 查看日志
docker compose logs -f --tail=100
```

### 6.6 每日备份（Cron 脚本 `backup.sh`）

```bash
#!/bin/bash
BACKUP_DIR="/var/backups/react-agent"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR
sqlite3 /opt/react-agent/data/db.sqlite3 .dump > $BACKUP_DIR/db_$DATE.sql
tar -czf $BACKUP_DIR/chroma_$DATE.tar.gz -C /opt/react-agent/data chroma_data
tar -czf $BACKUP_DIR/uploads_$DATE.tar.gz -C /opt/react-agent/data uploads
# 清理超过 7 天的备份
find $BACKUP_DIR -type f -mtime +7 -delete
# （可选）scp 到对象存储或另一台机器
```
`crontab -e` 加一行：`0 3 * * * /opt/react-agent/backup.sh`

---

## 7. 数据库选型与演进路径

### 7.1 一期（0 - 2000 DAU）

| 类型 | 产品 | 路径 | 费用 |
| --- | --- | --- | --- |
| 业务数据库 | SQLite | `./data/db.sqlite3` | 0 |
| 向量库 | ChromaDB（文件模式） | `./data/chroma_data/` | 0 |
| 文件存储 | 本地目录 | `./data/uploads/` | 0 |
| 缓存 | FastAPI `lru_cache` + Chroma 内存缓存 | 无独立服务 | 0 |

### 7.2 二期（2000 - 50000 DAU）

| 类型 | 产品 | 切换成本 |
| --- | --- | --- |
| 业务数据库 | PostgreSQL（Docker 同机） | 10 分钟：`pgloader sqlite:///data.db.sqlite3 postgresql:///appdb`；改 `DATABASE_URL` |
| 向量库 | Qdrant（Docker 或 Qdrant Cloud Free Tier 500MB） | 低：重新 embedding 导入一次 |
| 文件存储 | 腾讯云 COS / 阿里云 OSS | 很低：SDK 一行调用 |
| 缓存 | Redis（Docker） | 很低，但除非 QPS 过千否则不用 |

### 7.3 三期（规模化）

- 云托管 PostgreSQL / MySQL RDS
- 云托管向量库（Qdrant Cloud / Milvus 云）
- 多机 + 负载均衡（Caddy/Nginx 反向代理到多 app 容器）

---

## 8. 后端 API 最小接口清单

### 8.1 鉴权

| 方法 | 路径 | 请求 | 响应 | 说明 |
| --- | --- | --- | --- | --- |
| POST | `/api/v1/auth/wx-login` | `{ code }` | `{ token, user: {id, nickname, avatar, quota:{used,total}} }` | 微信 code 换 openid，签发 JWT |

### 8.2 个人

| 方法 | 路径 | 请求 | 响应 |
| --- | --- | --- | --- |
| GET | `/api/v1/me/profile` | - | `{id, nickname, avatar, quota}` |
| PUT | `/api/v1/me/profile` | `{ nickname, avatar }` | `{...}` |

### 8.3 聊天

| 方法 | 路径 | 请求 | 响应 |
| --- | --- | --- | --- |
| GET | `/api/v1/chat/sessions` | - | `[{id, title, last_msg_at, message_count}]` |
| POST | `/api/v1/chat/sessions` | `{ title? }` | `{ id, title }` |
| DELETE | `/api/v1/chat/sessions/{id}` | - | 200 |
| GET | `/api/v1/chat/sessions/{id}/messages` | - | `[{id, role, content, refs:[...], created_at}]` |
| POST | `/api/v1/chat/sessions/{id}/messages` | `{ content, document_id? }` | `{ id, role: "assistant", content, refs:[{document_id, title, snippet, score}] }` |

> 注：`document_id` 可选；不传则走全库检索；传则限定在该文档内检索（给"基于此文档提问"按钮用）

### 8.4 文档 / 知识库

| 方法 | 路径 | 请求 | 响应 |
| --- | --- | --- | --- |
| GET | `/api/v1/documents?domain=&keyword=` | - | `[{id, title, domain, size, chunk_count, created_at}]` |
| GET | `/api/v1/documents/{id}` | - | `{ id, title, ..., summary, status }` |
| POST | `/api/v1/documents` | multipart/form-data(file + domain + tags) | `{ id, title, status:"parsing" }` |
| DELETE | `/api/v1/documents/{id}` | - | 200 |

### 8.5 搜索

| 方法 | 路径 | 请求 | 响应 |
| --- | --- | --- | --- |
| GET | `/api/v1/search?q=&top_k=&domain=` | - | `[{id, title, snippet, score, document_id}]` |

### 8.6 推荐问题

| 方法 | 路径 | 响应 | 说明 |
| --- | --- | --- | --- |
| GET | `/api/v1/suggestions` | `["问题1","问题2",...]` | 一期可硬编码；二期由后台配置 |

### 8.7 后台管理（SQLAdmin 自动生成，无需手写）

| 路径 | 说明 |
| --- | --- |
| `/admin` | 后台首页（需 Basic Auth 或独立登录） |
| `/admin/user/list` | 用户列表 |
| `/admin/document/list` | 文档列表 + 上传（可由后台上传） |
| `/admin/message/list` | 消息审计 |
| `/admin/feedback/list` | 用户反馈 |

> 路由规范：**所有面向小程序的接口统一以 `/api/v1/` 开头**（版本号前缀），便于后端做破坏性升级时平滑过渡（`/api/v2/...`）与做访问控制 / 日志分析。

---

## 9. 小程序方案详解

### 9.1 技术栈

| 层 | 方案 |
| --- | --- |
| 框架 | 微信原生小程序（WXML/WXSS/JS） |
| UI 组件库 | Vant Weapp（有赞开源） |
| 状态管理 | `app.globalData` + `wx.setStorageSync`（不用 Vuex/Pinia） |
| 网络层 | `wx.request` 手动封装 |
| 构建工具 | 微信开发者工具 + `miniprogram_npm` |
| 代码仓库 | 同仓库 `apps/miniprogram/` 或独立 `react-agent-miniprogram` |

### 9.2 页面清单

| 路径 | 页面 | 主要功能 |
| --- | --- | --- |
| `pages/index/index` | 首页 | Banner + 搜索框 + 推荐问题卡片 + 最近文档 |
| `pages/chat/chat` | 对话页 | 气泡列表、输入框、"AI 思考中"指示器、引用卡片 |
| `pages/knowledge/knowledge` | 知识库 | Tab（全部/按领域）、搜索、文档列表 |
| `pages/knowledge-detail/knowledge-detail` | 文档详情 | 标题、摘要、"基于此文档提问"按钮 |
| `pages/me/me` | 我的 | 头像/昵称、会话列表、配额、关于/反馈 |

### 9.3 组件清单

| 组件 | 功能 |
| --- | --- |
| `components/message-bubble` | 用户气泡（右对齐）、AI 气泡（左对齐） |
| `components/thinking-dots` | "AI 正在思考..."动效 |
| `components/doc-ref-card` | 引用文档小卡片，点击跳详情页 |

### 9.4 工具 & 服务

- `utils/request.js`：统一请求封装，自动带 `Authorization: Bearer {token}`，自动处理 401 清 token 并跳转
- `utils/auth.js`：`wx.login` → `POST /api/auth/wx-login` → 存 token/user
- `services/chat.js` / `document.js` / `search.js`：按领域分组的接口封装

### 9.5 配置文件 `config/env.js`

```js
module.exports = {
  API_BASE_URL: 'https://api.你的域名.cn', // 开发版可勾"不校验合法域名"用 http://本地穿透
  APP_NAME: 'XX智能助手',
  DAILY_QUOTA: 50,
};
```

### 9.6 鉴权流程图

```
小程序                  后端(FastAPI)                 微信服务器
  │                        │                               │
  │ wx.login()             │                               │
  │ → code                 │                               │
  │ POST /api/v1/auth/wx-login{code}                           │
  │ ─────────────────────▶ │                               │
  │                        │ code2session(appid,secret,code)│
  │                        │ ─────────────────────────────▶ │
  │                        │ openid, session_key ◀────────── │
  │                        │ upsert User(openid)            │
  │                        │ sign JWT(user_id, exp)         │
  │ {token,user,quota} ◀───│                               │
  │ wx.setStorageSync(token)                                │
  │                                                       后续请求：
  │ GET/POST /api/v1/...                                       │
  │ Header: Authorization: Bearer <token>                   │
  │ ──────────────────────────────────────────────────────▶│
  │                         decode JWT → user_id            │
  │                      业务处理 ◀──────────────────────── │
  │                        response  ◀────────────────────── │
```

`AppSecret` 只能在后端使用，严禁写进小程序包。

### 9.7 引用文档渲染方案（一期 vs 二期）

一期（快速上线）：
- 后端 `POST /api/chat/sessions/{id}/messages` 同步返回 `{ content, refs:[...] }`
- 小程序用原生 `<view>` 渲染纯文本（`white-space: pre-wrap` 保留换行）
- `refs` 用 `<components/doc-ref-card>` 渲染为气泡下方可点击小卡片

二期（体验升级）：
- 后端流式返回（SSE / WebSocket），前端做打字机效果
- 接入 `towxml` 做 Markdown 渲染
- 支持语音输入、图片识别

### 9.8 小程序账号开通与审核要点

**开通**
1. mp.weixin.qq.com → 个人身份证注册小程序（免费）
2. 刷脸实名
3. 获取 AppID + AppSecret（只展示一次，保存到后端 .env）

**配置服务器域名**
- 小程序后台 → 开发管理 → 开发设置 → 服务器域名
- request / uploadFile / downloadFile 合法域名均填 `https://api.你的域名.cn`
- **必须 HTTPS + 备案域名**；localhost / IP / HTTP 在正式版不可用；开发版勾"不校验合法域名"可调试

**隐私协议**
- 设置 → 服务内容声明 → 填写用户隐私保护指引（用微信模板，声明收集 openid、文本输入）

**服务类目选择**
- 选「**工具 → 效率**」或「**工具 → 办公**」
- 不要选「教育 / 医疗 / 金融」（要资质）

**审核提交描述**
- 描述文案不要出现"AI""大模型""聊天机器人"
- 改写成：「提供 XX 领域知识检索与问答服务，基于运营方上传的文档进行引用式回答」
- 准备 1-2 张真实截图（首页、对话页、知识库页）

---

## 10. ReAct Agent 线上改造要点

### 10.1 按用户隔离

- `ReActAgent.run_for_user(user_id, session_id, query)`：
  - 短期记忆按 `session_id` 隔离（内存字典或 SQLite 缓存）
  - 长期记忆按 `user_id` 前缀过滤（Chroma collection 加 metadata `user_id`）
- 默认 `MAX_ITERATIONS` 线上从 10 降到 3-5，避免单次请求超时 30s

### 10.2 返回引用

- `ReActAgent` 在推理完成后，把检索到的 top-k chunks 作为 `refs` 字段附加到响应
- 返回字段：`{ role, content, refs:[{document_id, title, snippet, score}] }`

### 10.3 超时保护

- 单次 `/api/v1/chat/sessions/{id}/messages` 响应时间若预计 > 25s：先返回 `{status:"thinking", thinking_id}`，前端轮询 `GET /api/v1/chat/thinking/{thinking_id}` 拿结果（二期做 SSE）
- 一期可通过降低 `MAX_ITERATIONS` 简化

### 10.4 内容安全

- 后端收到用户 `content` 后，先调文本安全检测；命中敏感词直接拒绝
- AI 回答输出前也做一次检测（防止 prompt injection 后模型输出违禁内容）
- 一期先用关键词黑名单 + 正则；二期接 DashScope 文本安全 API（免费额度够用）

---

## 11. 运维 & 安全

### 11.1 安全 checklist

- [ ] 服务器只开放 22 / 80 / 443；其他端口不开
- [ ] SSH 用 key 登录而非密码（或保留强密码并启用 fail2ban）
- [ ] Caddy 自动续签证书，HTTPS 全站强制
- [ ] `.env` 不在 Git 仓库（在 `.gitignore`）
- [ ] AppSecret / API Key 仅后端可见，绝不在小程序端
- [ ] 数据库文件 `*.sqlite3` 也在 `.gitignore`
- [ ] 后台管理 `/admin` 加独立鉴权（HTTP Basic 或独立 session 登录）
- [ ] 用户每日配额（默认 50/天）限制滥用
- [ ] 文本内容安全检测接入（一期关键词，二期 API）

### 11.2 监控 & 日志

- **Sentry Free Tier**：后端 `sentry_sdk.init(dsn=...)` 捕获异常并邮件告警
- **应用日志**：`docker compose logs -f app` 实时查看
- **服务器健康**：`htop` / `df -h` / `du -sh data/` 定期检查磁盘与内存
- 推荐一个纯文本监控：`uptime` + 邮箱告警（10 行脚本），不需要上 Prometheus/Grafana

### 11.3 应急手册

| 场景 | 处理 |
| --- | --- |
| LLM API 失效（Kimi 挂掉或额度用完） | 改 `.env` 中的模型/API Key，`docker compose restart app` |
| 向量库损坏 | 从最近备份 `chroma_*.tar.gz` 恢复；或重新解析所有文档（脚本重跑 ingest） |
| SQLite 损坏 | 执行 `sqlite3 db.sqlite3 ".recover" > new.sql`，重建并重启 |
| 被刷量 / 恶意攻击 | 在后台封禁用户；临时提高配额阈值；加 IP 限频（Caddy 或 `slowapi`） |
| 小程序审核被拒 | 按拒绝原因改描述/类目；同时在后台加一条"含违规关键词则拒绝回答"规则 |

---

## 12. 成本估算（单人可承受）

| 项目 | 月度费用（¥） | 备注 |
| --- | --- | --- |
| 2C4G 腾讯云 Lighthouse | 8-17（年付折算月） | 新客 99-199/年 |
| 域名 | 1-5 | `.cn` 首年低价，续费约 30-50/年 |
| Kimi LLM API 调用 | 20-200 | 按 token 计费；200 用户约此范围 |
| 内容安全检测 | 0-30 | 免费额度或低额付费 |
| 监控 / Sentry | 0 | Free Tier |
| 对象存储（二期） | 1-10 | 可选 |
| **合计（一期）** | **≈ 30-250 元/月** | 起步非常轻 |

---

## 13. 分阶段实施计划

### Phase 0 - 基础设施（1 天）

- [ ] 注册腾讯云 + 购买 2C4G Lighthouse（Docker 镜像）
- [ ] 购买域名 + 启动备案（等待备案通过的同时可并行开发）
- [ ] SSH 登录并验证 Docker / docker compose
- [ ] 在服务器 `git clone` 项目仓库
- [ ] 创建 `Dockerfile` / `docker-compose.yml` / `Caddyfile` 并本地跑通 `docker compose up`

### Phase 1 - 后端骨架（2-3 天）

- [ ] 创建 `apps/backend/`（main/config/database/models/schemas/dependencies/auth）
- [ ] 接入 SQLAdmin，注册 User/Document/Message ModelView，后台登录可访问
- [ ] `/api/v1/auth/wx-login` 接口（wx.login code → openid → JWT）
- [ ] `/api/v1/chat/sessions` 与 messages 基本 CRUD
- [ ] `/api/v1/documents` 上传 + markitdown 解析 + 入库（BackgroundTasks 异步）
- [ ] `/api/v1/search` 语义搜索
- [ ] `/api/v1/me` 个人信息与配额
- [ ] 内容安全（关键词过滤 + 可选 API）
- [ ] 每日配额（按 `user_id + date` 计数）

### Phase 2 - 小程序（3-4 天）

- [ ] 注册小程序账号，拿到 AppID
- [ ] 微信开发者工具新建原生项目
- [ ] 安装 Vant Weapp 并构建 npm
- [ ] 5 个页面骨架 + TabBar
- [ ] `utils/request.js` / `utils/auth.js` / `services/*.js`
- [ ] 核心对话页（气泡、引用卡片、thinking-dots）
- [ ] 首页推荐问题（点击跳对话并带入问题）
- [ ] 知识库列表与详情页
- [ ] 我的（会话历史、配额、关于）

### Phase 3 - 联调与审核（1-2 天）

- [ ] 用内网穿透（cpolar / natfrp）把本地 8000 映射到 HTTPS 地址
- [ ] 小程序勾"不校验合法域名"联调后端
- [ ] 完整走通：登录 → 上传文档 → 搜索 → 对话 → 查看引用
- [ ] 服务器部署正式版本，备案通过后把小程序合法域名切到 `https://api.你的域名.cn`
- [ ] 准备审核截图与描述（参考 §9.8）
- [ ] 提交审核（1-2 工作日）；准备迎审账号

### Phase 4 - 种子用户与迭代（上线后）

- [ ] 邀请 20-100 个种子用户进群试用
- [ ] 一周内每天检查 Sentry 异常日志 + 对话内容，快速迭代
- [ ] 收集反馈，确定二期优先级
- [ ] 逐步上线流式响应、Markdown、语音等体验功能

### 总工期

- **20 个工作日左右（约 1 个月）**
- 关键路径：后端骨架 → 小程序 → 联调 → 审核

---

## 14. 关键风险与应对

| 风险 | 概率 | 影响 | 应对 |
| --- | --- | --- | --- |
| 备案慢 / 小程序审核被拒 | 中 | 高 | 提前备案（和开发并行）；选"工具/效率"类目；描述规避"AI"字样 |
| LLM 回答幻觉 / 不可靠 | 高 | 中 | 强制引用 + 限定领域 + 降低 `MAX_ITERATIONS` + 每日人工抽查 |
| 单人精力不足，功能膨胀 | 高 | 高 | 严格执行 MVP 范围；所有"想加的功能"写进文档但不编码 |
| SQLite 并发写锁 | 低 | 中 | 2000 DAU 以内一般够用；到阈值切 PostgreSQL（10 分钟迁移） |
| Chroma 向量检索效果差 | 中 | 中 | 哈希 embedding 先用；线上切换到 Kimi embedding API 立即可提升 |
| 被刷量攻击 | 低 | 中 | 每日配额 + IP 限频（slowapi 或 Caddy）+ 后台封禁用户 |

---

## 15. 开发规范

- **分支**：`master` 为生产分支；新功能从 `master` 切 `feature/xxx`，PR 合入 master
- **提交信息**：`feat: xxx` / `fix: xxx` / `docs: xxx`
- **配置**：所有密钥、域名、模型参数来自环境变量（`.env`），禁止 hardcode
- **数据库迁移**：一期 SQLite 可用手写 SQL 脚本；二期 PostgreSQL 上 Alembic
- **日志**：重要操作（登录、文档解析、LLM 调用、错误）统一 `logging.info/warn/error`
- **代码组织**：`apps/backend/` 与现有 `agent/`、`knowledge/`、`memory/` 解耦——后端只通过 Service 层调用核心模块

---

## 16. 里程碑交付清单

| 里程碑 | 交付物 | 判定通过标准 |
| --- | --- | --- |
| M0 基础设施 | 服务器、域名、Docker Compose 骨架 | `docker compose up` 能看到 `Hello from FastAPI` |
| M1 后端骨架 | FastAPI + SQLite + Chroma + SQLAdmin + 全部 API | Postman / curl 能走通登录/上传/搜索/对话 |
| M2 小程序 | 5 页 + TabBar + Vant Weapp | 真机可完整体验"登录→搜索→提问→看引用" |
| M3 后台与安全 | SQLAdmin、内容安全、配额、封禁 | 后台可管理，安全检查通过 |
| M4 上线 | 小程序通过审核 + 服务器部署成功 | 外部用户可在微信发现栏搜索到并正常使用 |

---

## 17. 相关文档

- 本仓库：`docs/KNOWLEDGE_IMPORT_GUIDE.md` / `docs/MARKITDOWN_INTEGRATION.md` / `docs/ChromaDB学习报告.md` / `docs/ReAct学习报告.md`
- 外部参考：FastAPI 文档、SQLAdmin 文档、Vant Weapp 文档、微信小程序文档、微信 code2session API

---

> 版本：v1.0（初始版）
> 更新日期：2026-06-12
> 维护人：项目开发者（1 人）
> 生效范围：所有后续线上化开发工作须按本文档执行；重大变更请更新本文档
