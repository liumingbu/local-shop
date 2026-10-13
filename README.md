# local-shop｜实体商户店铺与预订备货助手

**开发准备文档包 v0.1 · 2026-10-12**

仓库：`https://github.com/liumingbu/local-shop`

一个微信小程序承载多个商户，各店独立展示、管理询货和需求登记、安排备货与交付。顾客可以自行提交，老板也可以代记微信、电话、到店产生的需求。**不接入在线支付。**

## 当前状态：M1 工程基础已实现，业务闭环未实现

文档 PR #1 已按用户授权合并，基准 main：ccac6eb6bf9ca5c7acaf72c817e6dfb750db4e1f。

M1 提供 FastAPI 健康检查、严格配置校验、固定开发演示身份、用户/租户/成员模型与 Alembic 迁移、合成演示数据、Vue 工作台骨架及原生小程序 TypeScript 工程。当前分支 feat/m1-engineering-foundation，提交/合并结果以 PROGRESS 为准。

PostgreSQL 已在同一云电脑通过本机回环 TCP 运行；此前 Unix socket 失败记录保留。基础测试与数据库集成已执行，正式结果见 docs/TESTING.md。微信开发者工具、真机与生产部署仍 NOT_RUN。

## 先读这些文档

| 文件 | 用途 |
|---|---|
| [START_HERE](docs/START_HERE.md) | 用户如何上传文档并启动 Dot |
| [DOT_LONG_TERM_TASK](docs/DOT_LONG_TERM_TASK.md) | 可以直接交给 Dot 的完整长期任务 |
| [AGENTS](AGENTS.md) | 所有开发轮次必须遵守的约束 |
| [HANDOFF](HANDOFF.md) | 当前工作位置与恢复入口 |
| [PRD](docs/PRD.md) | 用户、功能、页面和首版范围 |
| [ARCHITECTURE](docs/ARCHITECTURE.md) | 推荐技术基线与运行方式 |
| [DATA_MODEL](docs/DATA_MODEL.md) | 多租户、需求状态、数据约束 |
| [API_CONTRACT](docs/API_CONTRACT.md) | 接口草案与权限约定 |
| [ROADMAP](docs/ROADMAP.md) | 分阶段任务、依赖与验收 |
| [PROGRESS](docs/PROGRESS.md) | 任务状态唯一台账 |
| [TESTING](docs/TESTING.md) | 测试矩阵、结果登记与真实性规则 |
| [ENVIRONMENT_CHECK](docs/ENVIRONMENT_CHECK.md) | Dot 环境验证格式与门槛 |
| [GITHUB_WORKFLOW](docs/GITHUB_WORKFLOW.md) | 空仓库初始化、分支、提交与 PR |
| [SECURITY](docs/SECURITY.md) | 租户隔离、身份、隐私与文件访问 |
| [EXTERNAL_DEPENDENCIES](docs/EXTERNAL_DEPENDENCIES.md) | 微信、备案、凭据与上线阻塞 |
| [DEPLOYMENT](docs/DEPLOYMENT.md) | 部署交付要求；当前不是已验证命令 |
| [DECISIONS](docs/DECISIONS.md) | 已确定约束与建议决策 |

## 开发方式

只在 Dot 自己的云电脑编写、运行和测试。GitHub 保存已提交的版本；不得依赖用户 Mac 在线，不得擅自使用 Codex Cloud、本地 Codex、ChatGPT Work、Codespaces、其他计算环境或第三方付费任务。GitHub Actions 默认不启用。

普通读写文件、安装不额外收费的开发依赖、开发分支提交与创建 PR 可以在授权范围内进行。主分支写入/合并、生产部署、真实数据删除、凭据变更、付费服务和外部执行环境必须事先确认。

## 首个业务闭环

先完成：**商户 A 创建店铺 → 代记一条电话需求 → 确认 → 备货 → 完成 → 查历史；商户 B 无权访问 A 的任何私有记录。**

先用自动化接口测试和 Web 工作台证明核心逻辑真实可用，再接入顾客小程序和微信真实能力。

## 如何运行

要求 Python 3.12、Node.js 24（实测24.19.0）；依赖锁文件已实际生成。

```sh
python3 -m venv .venv
.venv/bin/pip install -r apps/api/requirements.lock
npm ci
```

在仓库根目录复制 .env.example 为 .env，填写自己的隔离开发数据库地址（postgresql+psycopg://...）和至少32位随机 APP_SECRET_KEY，禁止将凭据提交或发进聊天。默认开发身份关闭。可在本机生成密钥：

```sh
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

准备好实际 PostgreSQL 数据库后，在仓库根目录执行：

```sh
.venv/bin/alembic -c apps/api/alembic.ini upgrade head
PYTHONPATH=apps/api .venv/bin/python -m local_shop
npm run dev -w apps/admin
```

API 默认只监听127.0.0.1:8000；工作台代理健康检查到此地址。/health/live 仅表示API存活；/health/ready 需要数据库SELECT 1成功，否则503，不表示业务或微信可用。

需要合成身份时，仅在本机开发 .env 中开启 DEV_AUTH_ENABLED=true，然后执行：

```sh
PYTHONPATH=apps/api .venv/bin/python -m local_shop.seed
```

种子仅生成商户A/B及两店租户成员，不包含真实顾客；生产/未显式开启开发身份时拒绝执行。开发会话 /api/v1/dev/session 只接受 merchant-a 或 merchant-b，15分钟到期，不代表微信登录。官方启动入口关闭代理头信任，部署不得擅自放开开发身份。

### 实际测试入口

```sh
.venv/bin/ruff check apps/api scripts
.venv/bin/python scripts/http_smoke.py
.venv/bin/pytest -q
npm run typecheck
npm run build
```

无 TEST_DATABASE_ADMIN_URL 时，7项真实PG测试明确跳过，不能视为全通过。完整验证用已安装可信PostgreSQL二进制路径：

```sh
PG_BIN=/absolute/path/to/postgresql/bin .venv/bin/python scripts/test_with_postgres.py
```

该脚本在同一进程生命周期内创建临时数据库簇，仅监听127.0.0.1，测试重启持久化、迁移和接口，最后停止并清理自身临时数据。使用本机trust认证仅限无真实数据的隔离开发测试，不可用于生产。

小程序构建产物在 apps/miniprogram/dist；工程配置暂用 touristappid，占位不代表有效AppID。TS编译不等于微信工具/真机通过。Web也只有工程骨架，没有记单业务。

## 数据和许可证

仅提交合成演示数据。不得上传真实客户资料、身份证件、电话地址、AppSecret、数据库备份或令牌。仓库可见性由用户决定，公开仓库也不代表已选定开源许可证；本包未添加开源授权。

## M2 老板代记验证

启动 API、迁移和演示种子后，运行 `npm run dev --workspace apps/admin`，
浏览器访问本机 Vite 地址。A/B 仅为合成开发身份，令牌只保存在页面内存。
工作台支持店名、无商品代记、状态流转和历史；不提供真实客户登录。
代记 API 支持小数数量、单位、规格和原始文本；页面当前使用自由文本表单。
相对时间保留在原文中并有创建时间，不推断为已确认的交付日期。

独立启动临时 PostgreSQL、API、Vite，并通过真实 HTTP 验证闭环与重启持久化：

```bash
PG_BIN=/path/to/postgresql/bin .venv/bin/python scripts/e2e_with_postgres.py --http-only
```

该脚本仅创建临时合成测试库，绑定本机回环地址并在退出时清理。
浏览器自动化：相同命令去掉 `--http-only`；需要可启动 Chromium。
当前 Dot 命令环境 Chromium 启动被 Unix socket 权限阻塞；浏览器三项测试未执行到页面断言，
不能用 HTTP 或构建通过代替浏览器通过。已有云浏览器连接本机服务亦返回连接拒绝。
