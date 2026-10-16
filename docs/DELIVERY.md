# local-shop 下一阶段交付索引

2026-10-14。等级DEV_REVIEW_READY，不是PILOT_READY，没有部署或微信提审。A—D覆盖既有页面交互、老板日常闭环、正式身份代码及可复现交付；仍须独立完成真实浏览器/微信/隐私/正式发布验收。

## 版本与证据

- PR21：已有工作台交互/草稿恢复，精确代码916b7554086fcf345900db62cd99f36b32f104ec。
- PR22：日常筛选/联系/复制/聚合统计，精确代码a574b0fa20c3df6897420ecaa92984188d69bc02。
- PR23：正式身份与工作台会话，精确代码7e386292393c9d792b3095395a4ec8cf93df1fc2。
- PR24：性能、启动、升级与交付，精确代码0afbd497955dde0b8d661cd633b9854e319cee5b；本轮D代码与最终远端复核见[evidence/runtime-delivery/RESULT_20261014.md](evidence/runtime-delivery/RESULT_20261014.md)，源码包从最终实际合并SHA导出，ZIP comment和随包验收说明记录SHA/ZIP哈希；不把报告自身的纯文档提交说成另一次业务测试。

## 包含什么

完整单仓库原生TypeScript/WXML/WXSS、Vue3/TS、FastAPI模块化单体；实际生成Python/npm依赖锁、隐藏配置样例、0001—0011迁移、合成种子、测试与脱敏结果、启动/停止/诊断、性能参考、旧版升级、只读维护检查、Linux候选部署与恢复说明。
ZIP项目直接根目录，不额外套目录；包括所有Git跟踪隐藏文件。不含.git、.env、真实客户/凭据/备份、node_modules、venv、PG/Nginx二进制或dist。安装构建见README。不是另一套项目或收费托管环境。

两版本对照脚本需要明确历史Git提交；源码ZIP无.git，需另从已授权仓库克隆历史才能重跑对比。普通安装/启动/单版本测试不依赖Git历史。

## 最短验收路径

1. [README](../README.md)：锁依赖安装、dev_stack启动/状态/诊断/停止。
2. [ACCEPTANCE](ACCEPTANCE.md)：工作台操作入口及未验收条件。
3. [PROGRESS](PROGRESS.md)：唯一F01—F11差异/状态；[TESTING](TESTING.md)：真实测试索引。
4. [MINIPROGRAM](MINIPROGRAM.md)：原生页面与开发工具导入，Web不能替代微信验收。
5. [DEPLOYMENT](DEPLOYMENT.md)、[RECOVERY](RECOVERY.md)：发布硬门禁、停写备份/独立恢复、增量升级及只读候选检查。

## 核验源码

ZIP注释为完整提交SHA；先比对随包SHA256，再验证ZIP CRC及逐Git blob清单。只有CRC正确不代表业务可用。最终代码/合并SHA、PR和远端文件核验以交付消息及最新证据报告为准。

## 外部未验收条件

本项目AppID后补，不复用旧配置、不反复索取。正式身份代码使用外部HTTPS替身和真实PG/HTTP验证；真实微信登录/扫码分享/消息、正式隐私、WXML/工具/真机、浏览器视觉截图/轨迹仍待验。首次真实管理员授予、实际生产部署/数据迁移/删除、付费、外部环境和微信提审须单独批准。systemd服务与目标生产容量/异机灾备未验收，云开发电脑不承诺永久在线。

完成本次A—D后提交阶段验收，等待用户查看成果，不擅自扩展MVP或发布。

## 2026-10-16 E—H补充交付范围

后续源码在A—D上新增0012—0014对应CSV草稿导入、用途化备货交付清单和站内更新/联系元数据（实际迁移ID以migrations目录为准）。操作指南见MERCHANT_QUICKSTART，合成三店核对与反馈见PILOT_ACCEPTANCE，针对性边界见PILOT_SECURITY_REVIEW。旧A—D源码包不代表包含本次修改。

最终提供的ZIP以明确Git提交为准，根目录直接源码/隐藏配置样例；校验文件单独列精确SHA与ZIP SHA256。没有真实凭据、备份、客户数据或私图；.env.example仅配置示例。尚未达到PILOT_READY，完整未验收项见PILOT_ACCEPTANCE。

E—H最终被测业务SHA：ceb12e9ef0dd1d31b7efd699166319d49da48850，PR25—29。最终开发回归与故障/升级/恢复报告见evidence/pilot-closeout。源码归档从PR29实际合并后的main生成，逐Git blob、CRC和SHA256核对；准确归档SHA在ZIP注释与交付校验文件中，不把报告自身的文档提交算成重新测试业务。
