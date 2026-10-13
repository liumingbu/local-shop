# PROGRESS｜任务状态唯一台账

更新时间：2026-10-13 UTC。以实际代码、远端和测试为依据；原包历史检查记录保留在evidence/package-original。

## 当前基准

- PR #1–#18已自查、合并并fetch核对；main：406ab69be3313b906834efa9cecddad5f194d878。
- 当前分支：chore/development-delivery，从上述main干净创建，仅维护交付索引和交接，无运行代码变更。
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

开发验证版达到DEV_REVIEW_READY，交付索引DELIVERY.md、验收入口ACCEPTANCE.md。源码包按最终合并提交导出/核验；不再扩展MVP外功能。下一阶段待本项目AppID/安全配置与获准的微信验收条件，完成正式身份及真实验证。M5外部条件缺失保留阻塞，不沿用旧佳琪配置，不让这项阻塞替代独立模块开发。
