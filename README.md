# local-shop｜实体商户店铺与预订备货助手

**开发验证源码 · 生产与微信真实能力尚未验收**

仓库：`https://github.com/liumingbu/local-shop`

一个微信小程序承载多个商户，各店独立展示、管理询货和需求登记、安排备货与交付。顾客可以自行提交，老板也可以代记微信、电话、到店产生的需求。**不接入在线支付。**

## 当前开发范围

后端已实现老板代记闭环、商品分类与多图、顾客询货/本人记录、私有附件与基础平台管理，并经真实PostgreSQL/HTTP验证。原生顾客与商户页面、Web平台管理和商品批量维护已有代码与客户端逻辑测试；正式身份、浏览器DOM、微信工具/真机仍待验收。各模块最新状态与代码证据只在[PROGRESS](docs/PROGRESS.md)和[TESTING](docs/TESTING.md)维护。

开发数据库现使用同一Dot云电脑从官方源码编译的PostgreSQL16.15，构建和实际回归见[环境证据](docs/evidence/pg1615/RESULT_20261013.md)。浏览器交互受环境限制，微信开发者工具/真机与生产部署未验收。

阶段交付索引见[DELIVERY](docs/DELIVERY.md)，验收与复现入口见[ACCEPTANCE](docs/ACCEPTANCE.md)。

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

普通读写文件、安装不额外收费的开发依赖、开发分支提交与创建 PR 可以在授权范围内进行。用户已授权Dot自行检查测试后合并本项目常规PR；直接写main、生产部署、真实数据删除、凭据变更、付费服务和外部执行环境仍必须先确认。

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

种子生成商户A/B、两店租户成员、初始无商户权限的顾客A/B，以及没有商户成员权限的平台演示管理员，均为合成身份；生产/未显式开启开发身份时拒绝执行。开发会话 /api/v1/dev/session 接受 merchant-a、merchant-b、customer-a、customer-b、platform-admin，15分钟到期，不代表微信登录。官方启动入口关闭代理头信任，部署不得擅自放开开发身份。

### 实际测试入口

```sh
.venv/bin/ruff check apps/api scripts
.venv/bin/python scripts/http_smoke.py
.venv/bin/pytest -q
npm run typecheck
npm run build
```

无 TEST_DATABASE_ADMIN_URL 时，所有需要真实PG的测试明确跳过，不能视为全通过。完整验证用已安装可信PostgreSQL二进制路径：

```sh
PG_BIN=/absolute/path/to/postgresql/bin .venv/bin/python scripts/test_with_postgres.py
```

该脚本在同一进程生命周期内创建临时数据库簇，仅监听127.0.0.1，测试重启持久化、迁移和接口，最后停止并清理自身临时数据。使用本机trust认证仅限无真实数据的隔离开发测试，不可用于生产。

小程序构建产物在 apps/miniprogram/dist；工程配置暂用 touristappid，占位不代表有效AppID。TS编译不等于微信工具/真机通过。Web现有基础代记工作台，但构建通过不代表浏览器交互验收通过。

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

## M3 图片接口（开发验证范围）

MEDIA_ROOT 是后端受控本机目录，不得将目录整体挂载为公开静态站点。
应用账号需要该目录读写权限；数据库与文件必须一起备份。

- 上传：POST /api/v1/merchant/tenants/{tenant_id}/media?purpose=PRODUCT 或 LOGO。
  Authorization: Bearer、Idempotency-Key 必需；请求体直接为图片二进制，Content-Type 为 image/jpeg、image/png 或 image/webp。
- 上限2 MiB、1200万解码像素；拒绝SVG/HTML/动画/伪图片。真实解码后缩至最长边1600，统一JPEG并移除EXIF等元数据。
- PUT .../products/{product_id}/images，提交 media_ids（最多8个有序且不重复）与expected_version；空数组移除商品关联，不删除图片文件。
- 店铺PUT的logo_media_id只接受本店LOGO图片；null移除Logo。
- 上传成功不意味着公开：仅当前发布店铺、发布商品、有效分类、已关联有效商品图片可通过公开URL获取。
- PATCH .../media/{id} 可凭expected_version设置ACTIVE/ARCHIVED，归档可恢复；不物理删除真实文件。

HTTP脚本已包含上传、归一化、排序、公开下载及重启后图片字节一致性验证。
图片维护页面及微信上传接口适配尚待后续实现，不能据后端通过声称真机图片已验证。

## M4a 顾客与询货（受控开发身份）

演示种子新增 customer-a / customer-b，两者没有商户成员权限。
仍须本机回环、DEV_AUTH_ENABLED=true，生产禁止。它们不代表真实微信登录。

- 顾客可以在已发布且开放相应交付方式的店铺提交文本/商品需求。
- 询货与需求是独立记录。商户答复“有货”不会创建需求或备货；必须显式转换。
- 本人记录由认证主体和记录归属匹配，无法凭姓名、未验证电话或客户端user_id认领老板代记。
- 询货内部备注不出现在顾客回复或事件中；需求内部备注不出现在本人接口。
- 期望时间可提供带时区expected_at，未提供时保持未知；原始需求与转换后的确认文字分别保存。
- 请求要求 privacy_accepted=true，记录开发隐私草案版本；这只是开发流程，不是正式法律文本或微信隐私能力验收。

私图及取消申请见后续接口章节。完整原生小程序业务界面和真实微信接入仍待完成。
迁移0005的降级如发现会丢弃的顾客/询货/新增时间内容会拒绝；生产恢复须先核验备份，不强制降级或清空数据。

## M4b 私有需求图片

- 顾客上传：POST /api/v1/stores/{store_id}/private-media?privacy_accepted=true，Bearer与Idempotency-Key必需，原始图片二进制体；与商品图一样限制、真实解码及去元数据。
- 老板代记私图：POST /api/v1/merchant/tenants/{tenant_id}/private-media。
- 顾客/商户提交需求或顾客询货时可附media_ids，最多5张、不重复；顾客支持仅图片。只能关联本人上传、当前店铺的PRIVATE图片，保持提交顺序。
- 顾客刚上传但尚未提交的图片不可由商户读取。提交后，仅对应商户及该顾客有权读取；匿名/其他顾客/其他店铺拒绝。
- 顾客图片GET /api/v1/me/media/{id}/content?store_id=...，携带Bearer；没有公开私图静态地址或URL令牌。
- 转需求保留原询货附件顺序。商户在转换时添加的内部图片默认不对顾客展示。
- PRIVATE不能作为商品图或Logo，不能修改用途绕过访问限制。

尚未确定真实资料保留期和删除流程，不启用自动清理真实旧文件。开发测试仅合成图片；正式收集资料前仍须完成隐私政策与微信相关核验。

## M4c 取消意向

顾客可对非终态需求提交取消申请；申请本身不会将记录标成取消。有待处理申请时，后端阻止商家继续推进状态，必须明确接受或拒绝并填写对客答复。接受后取消，拒绝保留原状态，原始需求及所有申请/决定留存。已完成/取消的记录不再受理。
接口、版本、幂等、停店历史处理及权限范围见[API契约](docs/API_CONTRACT.md)。具体测试结果以TESTING索引为准。

## 确认结果与原始需求

商户可在备货前添加完整确认候选（说明、数量/单位、明确交付时间），后端保留原始需求与所有旧候选。改动后回到待确认，商户需明确记录已与顾客沟通确认，再进入备货。该记录不是微信顾客电子确认。期望时间与确认时间不混用，未确认候选不能显示为已承诺。

## 原生顾客页面

代码与执行边界见[MINIPROGRAM](docs/MINIPROGRAM.md)。`npm run test:native`验证编译后页面逻辑（模拟wx）；`e2e_with_postgres.py --http-only --native-client`将同一逻辑连接真实HTTP/PG。两者都不代表微信工具、WXML渲染或真机验收通过。默认API未配置、开发登录关闭。

## 平台开发控制台与本人邀请

受控本机Web入口新增platform-admin演示选项，经服务端/platform/me确认角色后显示邀请、审核、商户启停和审计。管理员填写已存在账号UUID；收件人可在原生小程序“本人开店邀请”页接受/谢绝，接受后管理员才能批准。批准不自动公开店铺。

控制台POST在本机localStorage按已验证账号保存原请求，未知结果可同键重试；不保存登录令牌。存储失败不发送写请求，身份过期时允许重新登录同一账号并保留请求。操作理由只用合成说明，不填凭据或证件原文。清除浏览器数据前先核对未确认操作。

`npm run test:admin`运行Web控制器Node逻辑测试，不能替代浏览器DOM测试；`npm run test:native`运行模拟wx逻辑，不替代微信运行时。`scripts/e2e_with_postgres.py --http-only --native-client`还会执行编译后的Web平台控制器和原生邀请页，通过真实HTTP/PG验证往返流程。

### Web商品批量维护（开发验证）

商户登录后可在商品表编辑本页商品，也可新增草稿行；每页20件，每批最多50件。保存所选项时逐件提交，显示成功数量和商品ID。遇到版本冲突先停止，核对已保存项后可明确放弃剩余项；网络结果未知则使用“重试／继续原批次”，不要清理浏览器站点数据。重新登录同一身份保留原请求；已受邀并获准账号可选择自己的授权店铺。
当前类别、多图和Logo维护以原生商户页面为主。Web控制器有Node及真实HTTP/PG测试；浏览器DOM与微信WXML/真机仍未验收。

### 等待上限

图片总接收默认15秒（MEDIA_RECEIVE_TIMEOUT_SECONDS），数据库每条语句默认10000ms（DB_STATEMENT_TIMEOUT_MS）、锁等待3000ms（DB_LOCK_TIMEOUT_MS）、连接池等待5秒（DB_POOL_TIMEOUT_SECONDS）。零值/无限值配置会拒绝启动。图片408后重试原请求，数据库503不代表可以自动换幂等键。以上不是完整限流或全请求CPU截止时间；正式部署仍须入口请求体/连接/超时限制。

### 离线备份恢复演练

```bash
PG_BIN=/path/to/trusted/postgresql-16/bin .venv/bin/python scripts/backup_restore_drill.py
```

只创建临时合成PG和图片，真实pg_dump/pg_restore到另一空库并重新验证HTTP，不接受现有库地址。可复用离线工具为`PYTHONPATH=apps/api .venv/bin/python -m local_shop.recovery`；停写、目标保护、可信备份、凭据与失败处理必须先读[docs/RECOVERY.md](docs/RECOVERY.md)。真实备份不得上传仓库；生产执行和恢复切换另需授权。

## Linux交付候选

服务、TLS代理和配置模板见[DEPLOYMENT](docs/DEPLOYMENT.md#8-linux候选交付2026-10-13)。真实登录未完成，生产门禁主动拒绝启动；不代表已部署。合成组件检查：`PG_BIN=<PG16 bin> NGINX_BIN=<nginx 1.30.5> .venv/bin/python scripts/linux_delivery_check.py`；systemd验证受限时可明确使用`--skip-systemd`，该项仍NOT_RUN。

## 工作台交互验证（下一阶段）

Web开发演示入口须显式设置`VITE_ENABLE_DEVELOPMENT_LOGIN=true npm run dev -w apps/admin`，只在开发构建的localhost/127.0.0.1显示；后端仍要求受控回环和DEV_AUTH_ENABLED，正式构建不自动降级。工作台默认先显示记单/待办，商品维护可切换，草稿和未确认命令按账号/店铺保存在本机；退出清除内存令牌和私有页面，不删除原待确认请求。

`npm run test:dom`编译实际Vue组件，在jsdom执行输入、点击、提交、卸载/恢复事件；不是浏览器渲染。`PG_BIN=<PG16 bin> .venv/bin/python scripts/e2e_with_postgres.py --http-only --native-client --dom-client`另以真实API/PG验证这些组件事件。实际Chromium在本阶段唯一有限排障中仍被Unix socket权限限制，证据在docs/evidence/browser-20261014；没有真实截图，不能将DOM结果当成浏览器或微信验收。

### 正式身份代码与未配置边界

本项目没有真实AppID。默认WECHAT_LOGIN_ENABLED=false，原生config.enableWechatLogin=false；点击正式入口会明确提示未配置。不要借用旧项目值、把密钥写入小程序或聊天。后续安全配置本项目AppID/服务端secret后，原生入口「微信登录」调用wx.login；Web「发起工作台登录」显示短时确认码，在本项目小程序入口明确确认再回网页核对状态。仅使用原有商户/平台权限，首个真实平台角色授予需单独批准。

正式身份专项：`PG_BIN=/path/to/postgresql/bin .venv/bin/python scripts/test_with_postgres.py apps/api/tests/test_formal_identity.py`。外部微信HTTPS响应是唯一身份替身，数据库/会话/权限实际运行；其中另启动同机HTTP执行Vue正式登录事件。无需真实AppID。不能将此报告写作微信真机通过。生产发布门禁仍硬拒绝待外部验收。

### 同机受控开发启动、停止与诊断

先完成上述锁定依赖安装，PG_BIN指向已安装的可信PostgreSQL二进制目录。下面只管理仓库var/dev-stack中的专用合成开发库和图片，拒绝不认识的已有目录；不读取生产连接，不开放公网。

```sh
PG_BIN=/path/to/postgresql/bin .venv/bin/python scripts/dev_stack.py start
.venv/bin/python scripts/dev_stack.py status
.venv/bin/python scripts/dev_stack.py diagnose
.venv/bin/python scripts/dev_stack.py stop
```

start前台运行，默认最长一小时，可用--duration调整；Ctrl+C或stop结束API、Vite和PG，保留该专用库/图片，下次启动迁移到当前版本并幂等补齐合成账号。默认API127.0.0.1:8000、Web127.0.0.1:5173；可显式--api-port/--web-port。只在服务所在执行上下文访问这些地址，不是公开演示链接。

Dot云电脑的不同终端调用可能隔离PID和网络命名空间。status展示拥有该服务进程写入的近期健康心跳；stop通过本项目实例号控制文件请求拥有者结束，不根据其他调用中碰巧同号的PID杀进程。心跳过时不会声称仍在线；会话销毁可能停止服务，不承诺永久托管。没有再次尝试浏览器或切换环境。

实际生命周期回归：`PG_BIN=/path/to/postgresql/bin .venv/bin/python scripts/check_dev_stack.py`，创建合成记录、停止、重启、核对数据和Vite回环代理。专用合成数据保留，不自动清理。

### 规模、升级与只读维护验证

```sh
PG_BIN=/path/to/postgresql/bin .venv/bin/python scripts/benchmark_daily.py --baseline-ref adaef77da60fcd88513fcb97d54e6d801dd2729f --output /tmp/benchmark.json
PG_BIN=/path/to/postgresql/bin .venv/bin/python scripts/upgrade_drill.py --old-ref 640148dd84d6241eea399ccfc5552d0d324fc001 --output /tmp/upgrade.json
```

两个命令只创建新临时合成PG。升级演练用已知旧Git提交的后端先生成数据和图片，再实际增量迁移；源包使用Git archive需本地拥有指定提交，单一源码ZIP没有Git历史时这些两版对比命令BLOCKED，可从已授权仓库克隆获取相应历史；其他启动/测试不依赖Git历史。它们不接收现有生产库地址。

`PYTHONPATH=apps/api .venv/bin/python scripts/maintenance_check.py`只读当前明确配置的库与媒体目录，报告会话过期和未引用文件候选，没有删除/apply选项；不要把候选当作删除许可。真实保留/清理/部署另行审批。
