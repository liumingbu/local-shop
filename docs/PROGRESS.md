# PROGRESS｜任务状态唯一台账

更新时间：2026-10-14 UTC。以实际代码、远端和测试为依据；原包历史检查记录保留在evidence/package-original。

## 当前基准

- PR #1–#20已合并并fetch核对；本阶段起点main：640148dd84d6241eea399ccfc5552d0d324fc001。
- 当前工作包A分支feat/workbench-interaction-foundation，PR #21；代码916b7554086fcf345900db62cd99f36b32f104ec已推送并核对树；独立检出回归已通过，报告提交后按授权合并。下方旧轮次保留各自历史时间与范围。
- 用户已授权Dot自行测试审查后合并常规PR，阶段性回报。生产、凭据/权限、费用和环境变更仍需确认。
- 仅Dot自身云电脑；未使用Mac、Codex任务、Actions、Codespaces或其他云。未部署。
- GitHub API提交/PR/合并可用且fetch树核验；终端直接push认证未建立，不能混称终端push通过。

## 阶段状态

| 阶段 | 当前状态 | 已实现与证据 | 尚缺条件 |
|---|---|---|---|
| 文档基线 | DONE | PR #1，导入原包及隐藏配置，保留原记录 | 无 |
| M0 | DONE（开发范围） | 终端/运行时/文件/最小程序、真实PG及GitHub读写，ENVIRONMENT_CHECK | 不含微信/生产 |
| M1 | DONE | PR #2工程/配置/迁移/健康检查/合成身份，evidence/m1 | 无 |
| M2 | IN_PROGRESS（后端闭环通过） | PR #3及后续修订：代记→确认→备货→交付历史；租户/版本/幂等/事件；evidence/m2、m4c、m4d、m4f | 浏览器/原生UI实际运行未验收 |
| M3 | IN_PROGRESS（后端与原生逻辑通过） | PR #4/#5/#12/#15：分类/商品/多图/Logo/公开店铺/Web批量维护；evidence/m3a、m3b、m4g、web-catalog | DOM/WXML/真机未验收 |
| M4 | IN_PROGRESS（代码与协议逻辑通过） | PR #6–#14：顾客询货/需求/本人历史/私图/取消/修订；13原生页面；商户端与平台邀请审核/启停/审计；evidence/m4a–m4g、platform、platform-ui | 浏览器/微信真实运行、真实身份 |
| M5 | BLOCKED_EXTERNAL / CODE_PENDING | 模拟身份隔离、分享路径与网络封装有代码；没有声称微信实测通过 | 新项目AppID/凭据、正式身份接入、微信工具/真机、主体类目隐私/消息/域名条件；见EXTERNAL_DEPENDENCIES |
| M6 | IN_PROGRESS | PR #16上传/DB等待限时，evidence/bounded-io；PR #17恢复工具/演练已合并；本轮Linux组件专项通过 | 开发验证源码交付见DELIVERY；systemd/微信/生产仍阻塞；systemd/生产/异机灾备另验 |

## 阶段交付

- PR #17恢复工具已合并核验，真实CLI演练21表/92合成行/3图，206 Python/18 Web/54原生通过，见evidence/recovery。
- PR #18已自查合并并fetch核验；新增Nginx1.30.5 TLS代理、systemd候选、生产配置样例和fail-closed发布检查；真实身份未完成时服务门禁拒绝启动。
- 同一Dot源码构建Nginx，真实TLS1.2/1.3、固定域名跳转、私图权限、代理幂等、413/429及无查询串访问日志的组件专项已通过；213 Python（154真实PG）+18 Web+54原生及Ruff/TS/构建/HTTP/恢复/代理检查在代码b6652736远端干净检出全部通过；见evidence/linux-delivery/RESULT_20261013.md。
- systemd-analyze实际因/run/systemd只读失败：BLOCKED。组件重跑显式--skip-systemd，不把静态检查/服务启停视为通过。

## 测试与未验收

真实测试索引统一在TESTING.md；历史结果不覆盖。当前PG16.15，旧16.2报告保留其原始时间与范围。
浏览器DOM受当前浏览器运行/连接条件阻塞；原生测试使用模拟wx生命周期，真实HTTP仅证明协议和服务端往返。没有运行WXML编译/微信开发者工具/真机，没有真实微信登录、扫码、消息、审核或发布。

## 下一步

开发验证版达到DEV_REVIEW_READY，交付索引DELIVERY.md、验收入口ACCEPTANCE.md。源码包按最终合并提交导出/核验；不再扩展MVP外功能。用户于2026-10-14明确确认本项目暂无AppID、后续再补，真实微信接入延期，暂不继续催要。正式身份代码按本阶段C先行实现；外部条件补齐后完成真实微信验证。M5外部条件缺失保留阻塞，不沿用旧佳琪配置，不让这项阻塞替代独立模块开发。

## 本轮检查（2026-10-14）

远端main及分支已fetch核对，工作树起点干净，开放PR查询为0。只修改Markdown；运行代码相对b6652736无差异，历史213 Python/18 Web/54原生结果属于2026-10-13，本轮未重跑业务测试（NOT_RUN）。本轮执行文档差异/链接检查；没有登录微信或启用额外环境。已交付ZIP仍对应7dc4d313，无需为状态备注重新打包。

## 2026-10-14 下一阶段授权与F01—F11核对

基准main640148dd84d6241eea399ccfc5552d0d324fc001；已fetch全部远端分支，开放PR=0，起点工作树干净。用户授权A—D工作包（页面/日常闭环/正式身份代码/性能交付），AppID仅阻塞真实微信联调。历史213/18/54测试不计作本轮执行。

| 需求 | 已有API/模型 | 现有操作入口 | 已执行证据（历史） | 当前缺口与安排 |
|---|---|---|---|---|
| F01租户权限 | access/identity、Tenant/Member、平台启停 | 开发Web登录、原生入口/邀请/选店 | m2、platform、native HTTP：PG隔离/禁用 | 正式微信/管理身份未实现→C；真实页面未验收→A |
| F02店铺资料 | records Store、Logo关联 | Web简版店名；原生shopsettings完整字段 | m3b/m4g、真实HTTP/图片 | Web字段入口与保存反馈不足；长名称/失效状态→A |
| F03商品分类多图 | catalog/media、Category/Product/Media | 原生catalog/productedit；Web批量表 | m3a/m3b/m4g/web-catalog | Web大表移动端可操作性/空分类提示，页面事件覆盖→A；不重做API |
| F04询货 | customers/inquiries/replies | 顾客compose、商户merchantdetail | m4a/m4f、客户/商户HTTP | 原生真实交互未验收；Web无完整询货处理入口→A/B |
| F05顾客登记 | CustomerReservation、归属/快照/私图 | compose/records/detail | m4a–m4e、私图HTTP | 联系/配送信息字段和入口需补；日期备注不猜截止→B |
| F06老板代记 | NewReservation、来源/小数/幂等 | 原生merchant；Web快速代记 | m2/m4f、真实HTTP闭环 | Web草稿刷新丢失、未确认请求持久化不足；联系方式→A/B |
| F07确认交付 | records/confirmations/cancellations、版本事件 | 原生merchantdetail完整；Web仅按钮+事件 | m4c/m4d/m4f、PG并发/回滚 | Web缺确认候选/取消意向入口；需明确二次确认与冲突反馈→A/B |
| F08待办历史 | 当前只按状态分页；逐状态查询计数 | merchant列表/计数；Web状态筛选 | m2/m4f有限逻辑 | 日期/交付方式/逾期、搜索业务号、复制新需求、刷新计数均缺完整闭环→B/D |
| F09分享 | 原生store/product分享参数、scene路由 | 原生分享/最近浏览；首页UUID为开发入口 | m4e路由/模拟wx | UUID输入须限开发模式→A；真实码/分享/配置边界→C，真测待AppID |
| F10平台 | platform邀请/接受/审批/启停/审计 | WebPlatformPanel、原生invitations | platform/platform-ui，真实HTTP | 正式平台身份→C；审批/启停DOM交互与空态→A |
| F11保障 | 错误/幂等/上传DB限时/恢复/候选部署 | 开发错误提示、隐私说明、脚本 | bounded-io/recovery/linux-delivery | 真实页面/正式身份、参考规模性能、统一启动诊断/旧数据升级→A/C/D；systemd/微信另验 |

浏览器本轮有限排障已结束：启动被Unix socket权限拒绝，未放宽sandbox或API认证，见evidence/browser-20261014。之后不重复尝试。第一改进在既有Web工作台实现持久化代记与正确上下文隔离、清晰模式/导航/错误反馈，补实际Vue组件事件测试；不新增另一套系统。

## 工作包A现有页面交互（2026-10-14）

开发入口「记单与待办」与「商品维护」：持久化代记/原提交恢复、详情与明确确认、完整店铺字段、分类创建、退出与隐藏时私有内容清理。执行与失败修复记录见[evidence/workbench-ui/RESULT_20261014.md](evidence/workbench-ui/RESULT_20261014.md)。Vue/jsdom补充事件验证不等同真实浏览器；浏览器唯一迭代BLOCKED且已停止。后续B/C/D继续；正式身份不能等待AppID才编码。
