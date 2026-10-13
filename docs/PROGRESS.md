# PROGRESS｜任务状态唯一台账

更新时间：2026-10-13。更新者：Dot；原包记录已归档，以下区分基础验证和业务开发。

## 当前摘要

PR #1–#13已合并；M2代记闭环、M3商品/图片与M4顾客/询货/私图后端已有真实测试。完整业务界面仍在开发，浏览器交互BLOCKED；微信真机和部署未完成。

## 状态约定

`TODO` 未开始；`IN_PROGRESS` 在做；`BLOCKED` 条件缺失；`READY_FOR_REVIEW` 代码/文档及证据已推送待审；`DONE` 完成该项验收且需要时已合并。测试另外用PASS/FAIL/SKIP/NOT_RUN，不从任务状态推导。

| ID | 事项 | 当前状态 | 证据/说明 |
|---|---|---|---|
| DOC-01 | 初始化文档包 | DONE | PR #1已合并，main基准ccac6eb6 |
| M0-01 | 仓库检查 | DONE | main 62be6e58；旧验证分支 7bd637bf；任务分支开始时不存在；初始无打开 PR |
| M0-02 | Dot开发环境验证 | DONE（开发范围） | 本机TCP运行PG与33项测试通过；微信/生产另验 |
| M0-03 | Dot真实提交/PR验证 | DONE | 远端导入提交 1e1aa561 及草稿 PR #1 已实际创建；55文件逐字节核验通过 |
| M0-04 | main基线和文档PR | DONE | PR #1已合并，ccac6eb6 |
| M1 | 工程初始化 | DONE | PR #2已合并，main 3fd71df5；33项测试证据见evidence/m1/RESULT_20261013.md |
| M2 | 老板代记闭环 | IN_PROGRESS（后端已测，浏览器BLOCKED） | PR #3已合并，main d63ee77a；代码751dc278；干净检出56项测试、真实HTTP及重启持久化PASS；浏览器BLOCKED；evidence/m2/RESULT_20261013.md |
| M3 | 商品与店铺 | IN_PROGRESS | M3a PR #4已合并；M3b PR #5代码1338e9a4干净检出90项测试和HTTP重启图片字节验证PASS，见evidence/m3b/RESULT_20261013.md；原生维护页面开发中；WXML/浏览器未验收 |
| M4 | 顾客与小程序 | IN_PROGRESS | M4a PR #6已合并；M4b PR #7已合并，main89e7a595；代码e1b94a7d干净检出122项测试及HTTP私图/重启PASS，见evidence/m4b/RESULT_20261013.md；取消与确认修订后端已测；原生顾客逻辑已测，商户页面开发中，真机未完成 |
| M5 | 微信真实接入 | BLOCKED_EXTERNAL | AppID/运行条件与主体待确定 |
| M6 | 集成交付 | TODO | 无部署 |

## 本轮基准与证据

- M2起点main：3fd71df522643bf015013061ac1eed0b79af8e9a；初始工作树干净。
- 工作分支：feat/platform-console-invitations。
- M1合并已核验，旧验证与原包归档保留。
- 用户授权Dot自行审查和测试后合并常规PR；生产/权限/费用仍需单独授权。
- 后端使用真实PG测试，不使用SQLite。浏览器启动失败不计为业务断言失败，也不计PASS。

## 下一步

M2 PR #3已合并；保留浏览器BLOCKED。M3a PR #4已合并，main c41fb90d。M3b PR #5已合并，main 93b6afda。M4a PR #6已合并，main 09fe8a74。M4b PR #7已合并，main89e7a595。PG16.15编译后122项及HTTP重启回归通过。M4c PR #8已合并main b722d2d3，代码c812e496干净检出139项测试及HTTP/构建通过。M4d PR #9已合并main10a512d8；代码af376a55干净检出152项/HTTP重启/构建通过。M4e原生顾客7页、分身份/店铺草稿和网络重试已实现；23项模拟wx逻辑测试及真实HTTP/PG客户端流程初验通过，PR #10代码812a2d02干净检出152项Python+23项Node及构建/真实HTTP复核通过，见evidence/m4e/RESULT_20261013.md；已合并main 2a4dd1b6。M4f商户工作台/处理详情/店铺资料三页实现，PR #11代码a8b05853独立远端检出152项Python、37项Node与TS/构建/真实HTTP及重启复核全部通过，见evidence/m4f/RESULT_20261013.md，已合并main e355ac91。M4g目录/多图/Logo维护代码完成，PR #12代码b50e5e51远端干净检出152项Python+50项Node、Ruff/TS/构建与真实HTTP/PG重启复核全部通过，见evidence/m4g/RESULT_20261013.md，已合并main 1da285fd。平台邀请审核/启停/审计后端与0009迁移已实现，PR #13代码99d41f55远端干净检出171项Python（145真实PG）+50项Node及Ruff/TS/构建/HTTP重启全部通过，见evidence/platform/RESULT_20261013.md，已合并main 2eb23d87；Web平台控制台/原生本人邀请页已实现，PR #14代码3e23f683远端171项Python、10项Web控制器Node、54项原生逻辑与Ruff/TS/构建/真实HTTP及重启全通过，见evidence/platform-ui/RESULT_20261013.md，待自查合并；随后Web目录维护/M5/M6。
两顾客本人记录与商户边界已有专门测试，身份仍为开发模拟，真实微信另验。
