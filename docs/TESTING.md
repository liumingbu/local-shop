# TESTING｜验收矩阵与真实结果

**M1–M4及平台模块已有真实后端/PG/HTTP验证；原生与Web控制器逻辑已测；浏览器DOM、WXML/微信真机和部署未验收。**

文档包的文件/链接/格式检查属于“制品检查”，与Dot环境验证、API、数据库、微信和部署测试严格分开。

## 1. 分层测试

| 层次 | 方法 | 不代表什么 |
|---|---|---|
| 文档包 | 文件存在、Markdown结构、链接、压缩包完整性 | 不代表Dot可运行代码 |
| 静态 | 类型/语法/lint/构建 | 不代表真实API/微信可用 |
| 单元 | 状态机、输入校验、权限策略 | 不代表PG事务、微信登录成功 |
| 数据库/接口 | 真实PostgreSQL迁移、API请求、事务与鉴权 | 不代表真机页面通过 |
| Web端到端 | 浏览器操作管理工作台 | 不等于原生WXML界面或微信能力 |
| 微信工具/真机 | 官方工具和实际设备流程 | 需记录版本、设备、网络、步骤 |
| 部署/恢复 | 清洁安装、启动、备份恢复与回滚 | 需真实目标环境或明确测试环境 |

默认全部在Dot自身环境执行能执行的部分；不得擅自启用Actions或其他执行器。必须人工参与的微信验收单独安排，不依赖用户Mac长期开机开发。

## 2. 核心测试矩阵

| ID | 验收点 | 当前验证状态（按层区分） |
|---|---|---|
| ENV-01 | Dot终端/运行时/最小程序+测试+远端提交 | PASS（基础六项测试与接口提交；非终端 push） |
| CFG-01 | 必填配置缺失明确失败、生产禁用假登录 | PASS（M1自动测试） |
| DB-01 | 空PG库迁移可重复、种子隔离、重启持久化 | PASS（当前PG16.15隔离开发实例；旧报告16.2保留） |
| TEN-01 | A/B列表、详情、写入、关联对象互不可越权 | PASS（已实现后端，M2–M4a） |
| TEN-02 | 私有图片、历史、导出（如实现）同样隔离 | PASS（已实现历史/私图，M4a/M4b；导出未实现） |
| AUTH-01 | 顾客只能看本人记录，电话/姓名无法冒认代录 | PASS（固定开发身份；M4a，非真实微信） |
| AUTH-02 | 平台管理鉴权及审计，普通商户不能调用 | PASS（PR #13/14真实PG/HTTP；开发身份，非正式运营身份） |
| REC-01 | 代记→确认→备货→自提完成、配送完成 | PASS（M2真实PG/HTTP） |
| REC-02 | 询货回复不自动备货，显式转换且不重复 | PASS（M4a真实PG/HTTP） |
| REC-03 | 重复提交幂等、同键不同内容冲突、事务失败回滚 | PASS（已实现接口，M2–M4a） |
| REC-04 | 版本冲突、非法跳状态、终态保护 | PASS（已实现状态机，M2–M4a） |
| REC-07 | 原始需求与确认修订分开、重新确认、时间/单位快照 | PASS（M4d真实PG16.15/HTTP；商户记录一致意见，非微信电子确认） |
| REC-06 | 顾客取消意向、商户决定、待处理保护、留痕/并发/回滚 | PASS（M4c真实PG16.15/HTTP；UI未验收） |
| REC-05 | Decimal数量/单位、无商品自由文本、历史快照 | PASS（M2/M3a/M4a） |
| CAT-01 | 分类商品多图、上下架、跨租户引用拒绝 | PASS（后端，M3a/M3b；维护UI未验收） |
| FILE-01 | 类型/大小/访问、公开与私有图分开、恶意路径拒绝 | PASS（已实现公图/私图后端，M3b/M4b；微信上传未测） |
| UI-01 | 商户Web记单、待办筛选、详情与异常恢复 | BLOCKED（Chromium Unix socket权限/云浏览器连接限制） |
| UI-02 | 原生顾客TS逻辑、草稿/中断/网络契约 | PASS（当前54项模拟wx；真实HTTP/PG协议流程）；WXML/真机NOT_RUN |
| WX-01 | 微信真实登录、过期/拒绝/缺凭据失败处理 | NOT_RUN |
| WX-02 | 分享/码带店铺、无效店铺不串店、草稿隔离 | NOT_RUN |
| WX-03 | 请求/图片真机网络、iOS/Android基础流程 | NOT_RUN |
| WX-04 | 隐私同意/拒绝与消息授权/失败状态 | NOT_RUN |
| OPS-01 | 安装、迁移、备份恢复、日志脱敏 | PASS（Dot隔离开发范围：真实PG+图片备份恢复；生产/异机另验） |
| PERF-01 | 合成数据与有限并发测试，记录真实性能 | PARTIAL（5–10并发一致性PASS；目标规模/性能未测） |

## 3. 每次执行记录格式

```text
run_id:
日期与时区:
执行者: Dot（或明确人工/当前会话）
实际机器/环境:
分支:
被测代码SHA:
未提交变更: 无 / 差异摘要及文件
前置条件:
执行命令:
退出码:
通过/失败/跳过数量:
结果: PASS / FAIL / SKIP / NOT_RUN / BLOCKED
覆盖测试ID:
脱敏日志位置:
未覆盖内容:
提交/PR证据:
```

原始日志保存于 `docs/evidence/` 或经审阅的附件；避免保存token、客户数据、完整本机环境变量。真实测试命令以实现后的工具为准，不提前伪造日志。

## 4. 完成门槛

功能必须覆盖成功、失败和权限；所有适用测试通过才能说该层通过。关键安全测试不能用skip当作通过。未具备微信工具可报告后端已测、小程序未测，不能报告全流程已通过。

每次报告引用测试时的代码SHA。之后只修改报告文档可用不同提交，不必制造自引用SHA。合并或改动业务代码后需要重新执行受影响测试。

## 5. 现有结果索引

- `evidence/BOOTSTRAP_ATTEMPT_20261012.md`：当前会话GitHub真实检查与403结果，不是Dot验证。
- `evidence/PACKAGE_VALIDATION_20261012.json`：本包生成后的制品检查记录，不是业务测试。

- `ENVIRONMENT_CHECK.md`：Dot 实际基础环境报告，六项测试于 14:23 UTC 重跑通过，远端提交 7bd637bf 已核验。
- 本轮制品导入检查另见 evidence/FOUNDATION_IMPORT_20261012.md；业务、数据库和微信测试仍 NOT_RUN。

- 2026-10-12 14:58 UTC：[PG预检查](evidence/POSTGRES_PREFLIGHT_20261012.md)，启动BLOCKED；无数据库集成测试执行，业务测试仍NOT_RUN。

- 2026-10-13 M1：33项Python测试、PG重启持久化、真实HTTP、前端与小程序类型/构建初验通过。正式结果：evidence/m1/RESULT_20261013.md，远端被测SHA cddfd9b6，干净检出33/33通过，无跳过。

- 2026-10-13 M2：后端真实PG测试、HTTP闭环及API/PG重启持久化通过；Web/小程序类型与构建通过。Chromium启动权限阻塞，三项Playwright测试均未进入页面断言。被测SHA751dc278；56项测试，正式结果及干净检出日志见evidence/m2/RESULT_20261013.md。

- 2026-10-13 M3a：代码5889f341干净检出74项测试通过（48真实PG），HTTP公开目录/归档与重启持久化、TS/构建PASS；详见evidence/m3a/RESULT_20261013.md。多图/UI/微信未计通过。

- 2026-10-13 M3b：代码1338e9a4干净检出90项测试通过（64真实PG），真实图片文件及HTTP重启字节验证PASS；evidence/m3b/RESULT_20261013.md。UI/顾客私图/真实微信未计通过。

- 2026-10-13 M4a：代码013e524d干净检出109项测试（83真实PG）与HTTP/重启/构建PASS，evidence/m4a/RESULT_20261013.md。仅开发顾客身份，微信和私图未验收。

- 2026-10-13 M4b：代码e1b94a7d干净检出122项测试（96真实PG）、真实私图文件及HTTP权限/重启验证PASS，evidence/m4b/RESULT_20261013.md。浏览器/微信仍未验收。

- 2026-10-13 PostgreSQL16.15：官方源码校验编译，main89e7a595干净检出122项及HTTP重启回归通过，见evidence/pg1615/RESULT_20261013.md。
- 2026-10-13 M4c：代码c812e496干净检出139项（113真实PG16.15）及取消HTTP/重启、TS/构建PASS，见evidence/m4c/RESULT_20261013.md；不是微信/浏览器验收。

- 2026-10-13 M4d：代码af376a55干净检出152项（126真实PG16.15）及确认修订HTTP/重启、TS/构建PASS，evidence/m4d/RESULT_20261013.md。业务原生UI/微信/浏览器未验收。

- 2026-10-13 M4e：代码812a2d02干净检出152项Python/23项Node、TS与构建通过；原生TS通过模拟wx调用真实HTTP/PG完成顾客流程，evidence/m4e/RESULT_20261013.md。严格不等同WXML/微信工具/真机/分享验收。

## M4f 商户原生页面逻辑（2026-10-13）

代码a8b05853远端干净检出：152项Python（126真实PG）+37项Node、Ruff/TS/构建、原生商户页面通过模拟wx传输调用真实HTTP/PG闭环及旧重启回归均PASS。见[evidence/m4f/RESULT_20261013.md](evidence/m4f/RESULT_20261013.md)。WXML/微信真机仍未测；首次HTTP断言措辞不符已修复并复核。

## M4g 原生目录维护（2026-10-13）

代码b50e5e51远端干净检出：152项Python（126真实PG）+50项Node、Ruff/TS/构建、目录多图/Logo的真实HTTP与旧重启回归通过。见[evidence/m4g/RESULT_20261013.md](evidence/m4g/RESULT_20261013.md)。微信运行时未验收。

## 平台基础管理（2026-10-13）

代码99d41f55远端干净检出：171项Python（145真实PG，19项平台专项）+50项Node、Ruff/TS/构建、实际HTTP/PG和重启回归均通过。邀请/收件人接受/审核/启停/审计、平台与业务权限分离、并发/回滚/暂停锁验证见[evidence/platform/RESULT_20261013.md](evidence/platform/RESULT_20261013.md)。平台界面和正式身份未完成。

## 平台Web和本人邀请（2026-10-13）

代码3e23f683远端干净检出：171项Python、10项Web控制器Node、54项原生模拟wx、Ruff/TS/构建与真实HTTP/PG及重启通过。见[evidence/platform-ui/RESULT_20261013.md](evidence/platform-ui/RESULT_20261013.md)。浏览器DOM/WXML/真机未验收。

## Web商品批量维护

PR #15远端代码0d9de702独立干净检出175 Python（149真实PG）、18 Web控制器、54原生模拟wx与Ruff/TS/构建/真实HTTP及PG重启均退出0，0失败/跳过；见[evidence/web-catalog/RESULT_20261013.md](evidence/web-catalog/RESULT_20261013.md)。覆盖全批前置校验、部分成功、原请求恢复、版本冲突停止、真实POST/PUT已提交后丢响应重放与租户隔离。Vue父页面完整交互和浏览器DOM未验收。

## 图片接收与数据库等待限时

PR #16代码58b38b40独立远端干净检出193 Python（154真实PG、39非PG）、18 Web、54原生及Ruff/TS/构建/真实慢TCP上传/HTTP和PG重启全部退出0。新增18项验证总截止时间、超限/断开、真实语句/锁/池超时及恢复、事务回滚/租户锁释放与错误脱敏；见[evidence/bounded-io/RESULT_20261013.md](evidence/bounded-io/RESULT_20261013.md)。不代表完整限流或生产容量验收。

## 数据库与图片离线恢复

PR #17代码ca64e8a5远端独立干净检出206 Python（154真实PG、52非PG）、18 Web、54原生及Ruff/TS/构建/HTTP重启全部退出0；实际CLI pg_dump/pg_restore到另一个空库，21表/92合成行/3图在重启后通过HTTP、字节与权限/幂等核对。损坏包、缺图、原库/非空库/已有目录均拒绝；见[evidence/recovery/RESULT_20261013.md](evidence/recovery/RESULT_20261013.md)。没有上传备份，生产/异机恢复未测。

## Linux TLS代理与生产发布门禁

PR #18代码b6652736独立远端干净检出213 Python（154真实PG、59非PG）、18 Web、54原生与Ruff/TS/构建/HTTP/恢复通过。真实Nginx1.30.5 TLS1.2和1.3/413/429/访问日志/私图鉴权通过，见[evidence/linux-delivery/RESULT_20261013.md](evidence/linux-delivery/RESULT_20261013.md)。systemd-analyze因/run/systemd只读BLOCKED；全套明确--skip-systemd，并未运行系统服务或生产部署。正式身份/微信/DOM仍未验收。

## 工作包A现有页面交互（2026-10-14）

开发入口「记单与待办」与「商品维护」：持久化代记/原提交恢复、详情与明确确认、完整店铺字段、分类创建、退出与隐藏时私有内容清理。执行与失败修复记录见[evidence/workbench-ui/RESULT_20261014.md](evidence/workbench-ui/RESULT_20261014.md)。Vue/jsdom补充事件验证不等同真实浏览器；浏览器唯一迭代BLOCKED且已停止。后续B/C/D证据见下文。

## 工作包B 日常闭环

见[evidence/daily-workbench/RESULT_20261014.md](evidence/daily-workbench/RESULT_20261014.md)：主工作树221 Python、18控制器、11 Vue组件、57原生模拟wx、5 Vue/jsdom真实HTTP场景及重启通过；保留初次空库降级失败与修复。精确远端a574b0fa20c3df6897420ecaa92984188d69bc02独立检出同套回归通过。原生真机/浏览器仍未验收。

## 工作包C正式身份

见[evidence/verified-identity/RESULT_20261014.md](evidence/verified-identity/RESULT_20261014.md)。正式身份外部HTTPS替身+真实PG18专项，其中真实HTTP上的Vue正式登录事件；完整Python初次238通过后又增加1项权限隔离，远端7e386292393c9d792b3095395a4ec8cf93df1fc2独立检出239项（180真实PG）通过，0失败/跳过。59原生模拟wx/18控制器/11Vue组件通过。真实AppID/微信/浏览器未验收，失败与修复保留。

## 工作包D运行与交付

见[evidence/runtime-delivery/RESULT_20261014.md](evidence/runtime-delivery/RESULT_20261014.md)：主工作树242 Python（183 PG）、18控制器/11Vue组件/59原生及实际HTTP通过；同机10并发/500读请求前后0错误，旧0009→0011真实升级和启动停止重启已执行；保留旧幂等兼容失败和修复。TLS代理通过，systemd明确跳过。最终精确远端0afbd497955dde0b8d661cd633b9854e319cee5b干净独立检出同套完整回归、备份恢复、10并发规模/升级/生命周期全部退出0，详见该报告最终段和remote-full.txt。

## 2026-10-16 H1正式代理来源

PR25代码79b83d4444e1eff95419ad38b837196c171d94de独立干净检出254 Python（183 PG）、真实Nginx/TLS来源隔离/伪造头/直连计数及既有Linux组件均通过；systemd明确跳过，真实微信/浏览器不变。详见[evidence/auth-proxy/RESULT_20261016.md](evidence/auth-proxy/RESULT_20261016.md)。

## 2026-10-16 E开店准备/CSV

主工作树13真实PG专项、60原生逻辑/资源、11Vue组件、6Vue真实HTTP事件及旧重启通过；200行参考和0011→0012升级见evidence/merchant-preparation。最终被测远端SHA结果随后追加；不把原生资源检查或jsdom当视觉/真机验收。

E远端最终：9bd3219精确检出267 Python（196真实PG）、18控制器/13Vue组件/60原生、6Vue真实HTTP及升级通过。备份脚本旧版本断言失败后仅补断言，1cdb68d精确检出备份/恢复和重复200行参考通过；应用/测试/锁文件与9bd经git diff一致。详见[evidence/merchant-preparation/RESULT_20261016.md](evidence/merchant-preparation/RESULT_20261016.md)，不隐去串行退出1与修复。

## F主工作树验证（2026-10-16）

7真实PG专项、13Vue组件和7Vue实际HTTP场景、类型/构建、原有重启以及0012→0013含半途CSV任务升级通过；精确远端复核待追加，见evidence/fulfillment/RESULT_20261016.md。实际打印/浏览器/WXML另验。

F精确远端5ce8e2ed7e008e6104fad58f16a7fba52f67476f：274Python（203PG）、18控制器/13jsdom/60原生、7真实VueHTTP、26旧表97行3图升级与28表92行3图恢复通过。首次超时及原码重复验证见evidence/fulfillment/RESULT_20261016.md，未跳过失败或放宽限制。

## G新增针对性证据

见evidence/communications/RESULT_20261016.md及失败记录。主工作树15PG、63原生模拟、14jsdom、8Vue事件真实HTTP/PG、0013→0014旧数据升级。精确远端仍待，不把替身外部接受写成送达。

G精确远端a1bd092904e0703dd603251c8b326118a0ad3c57：52通信/顾客/正式身份PG相关回归、18控制器/14jsdom/64原生、8真实VueHTTP及27旧表98行3图升级通过。详见evidence/communications最终追加及registry中断说明；不是全套仅52项。H将完成完整回归。
