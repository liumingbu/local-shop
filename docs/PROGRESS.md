# PROGRESS｜任务状态唯一台账

更新时间：2026-10-12。更新者：Dot；原包记录已归档，以下区分基础验证和业务开发。

## 当前摘要

文档PR #1已合并；M1代码和33项Python测试已执行，真实PG及前端构建可用；M2业务闭环、微信真机、部署未完成。

## 状态约定

`TODO` 未开始；`IN_PROGRESS` 在做；`BLOCKED` 条件缺失；`READY_FOR_REVIEW` 代码/文档及证据已推送待审；`DONE` 完成该项验收且需要时已合并。测试另外用PASS/FAIL/SKIP/NOT_RUN，不从任务状态推导。

| ID | 事项 | 当前状态 | 证据/说明 |
|---|---|---|---|
| DOC-01 | 初始化文档包 | DONE | PR #1已合并，main基准ccac6eb6 |
| M0-01 | 仓库检查 | DONE | main 62be6e58；旧验证分支 7bd637bf；任务分支开始时不存在；初始无打开 PR |
| M0-02 | Dot开发环境验证 | DONE（开发范围） | 本机TCP运行PG与33项测试通过；微信/生产另验 |
| M0-03 | Dot真实提交/PR验证 | DONE | 远端导入提交 1e1aa561 及草稿 PR #1 已实际创建；55文件逐字节核验通过 |
| M0-04 | main基线和文档PR | DONE | PR #1已合并，ccac6eb6 |
| M1 | 工程初始化 | READY_FOR_REVIEW（Dot自查） | PR #2；cddfd9b6干净检出33项测试与构建通过，详见evidence/m1/RESULT_20261013.md |
| M2 | 老板代记闭环 | TODO | 无业务测试 |
| M3 | 商品与店铺 | TODO | 无业务测试 |
| M4 | 顾客与小程序 | TODO | 无业务测试 |
| M5 | 微信真实接入 | BLOCKED_EXTERNAL | AppID/运行条件与主体待确定 |
| M6 | 集成交付 | TODO | 无部署 |

## 本轮基准与证据

- 起点main：ccac6eb6bf9ca5c7acaf72c817e6dfb750db4e1f；初始工作树干净。
- 工作分支：feat/m1-engineering-foundation。
- 当前用户已授权长期开发和自行审查后合并常规PR，阶段性回报。
- 既有env-check及原始导入记录保留；数据库Unix socket旧阻塞通过本机TCP替代路径解决。
- M1被测代码cddfd9b656092c3b73ae2823a66980688bc54a49；PR #2；干净检出验证见evidence/m1/RESULT_20261013.md。

## 下一步

M1远端保存和干净检出回归已完成，按用户授权自主审查合并后进入M2老板代记及租户隔离。生产/微信真实性不能从M1测试推出。
