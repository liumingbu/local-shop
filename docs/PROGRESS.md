# PROGRESS｜任务状态唯一台账

更新时间：2026-10-13。更新者：Dot；原包记录已归档，以下区分基础验证和业务开发。

## 当前摘要

文档PR #1、M1 PR #2已合并。M2后端老板代记闭环与租户隔离已实现并测试；Web构建通过、真实浏览器交互BLOCKED。微信真机和部署未完成。

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
| M3 | 商品与店铺 | IN_PROGRESS | M3a PR #4代码5889f341干净检出74项测试与HTTP/构建PASS，见evidence/m3a/RESULT_20261013.md；多图和维护界面未完成 |
| M4 | 顾客与小程序 | TODO | 无业务测试 |
| M5 | 微信真实接入 | BLOCKED_EXTERNAL | AppID/运行条件与主体待确定 |
| M6 | 集成交付 | TODO | 无部署 |

## 本轮基准与证据

- M2起点main：3fd71df522643bf015013061ac1eed0b79af8e9a；初始工作树干净。
- 工作分支：feat/m3-catalog。
- M1合并已核验，旧验证与原包归档保留。
- 用户授权Dot自行审查和测试后合并常规PR；生产/权限/费用仍需单独授权。
- 后端使用真实PG测试，不使用SQLite。浏览器启动失败不计为业务断言失败，也不计PASS。

## 下一步

M2 PR #3已合并；保留浏览器BLOCKED。M3a保存和干净检出回归后自查合并，随后增加图片处理及商品维护界面。
两客户本人隔离在M4实现与测试，不从当前两商户隔离推导。
