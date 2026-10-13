# 初始化文档导入记录

日期：2026-10-12 UTC。执行地点：Dot 当前云电脑。

## 启动核查

- 远端 main：62be6e588b375c2cab90364472322b96f8c5f9e8。
- 远端 env-check/20261012：7bd637bf3b0c90852285048ed08d76db0c7ddb44。
- chore/project-foundation 开始时不存在；无打开 PR。
- 新克隆工作树初始干净，从 main 创建本任务分支。
- 旧环境验证工作区有未跟踪 ENVIRONMENT_CHECK.md 与 __pycache__/；原样保留，没有清理或覆盖。

## 导入与同名比较

- 安全检查 ZIP 路径和符号链接，移除包的单层目录前缀，README.md、AGENTS.md、HANDOFF.md、docs/ 与隐藏配置均放在仓库根下。
- 不提交 ZIP，不创建根目录 local-shop-bootstrap/。
- main 原 README 与包 README 已 diff 比较。将简短占位说明扩展为包内项目说明，原文另存 MAIN_README_BEFORE_IMPORT.md。
- 包内 docs/ENVIRONMENT_CHECK.md 是旧待验证模板，与真实报告不一致。当前路径保留已发布报告的全部原文，字节比较通过；原模板和完整原包文本归档在 package-original/，保留历史审计及相对链接。
- README、HANDOFF、PROGRESS、TESTING、EXTERNAL_DEPENDENCIES、START_HERE 仅按已核验事实更新。原包校验和与制品检查记录作为历史证据保留，不冒充当前检查。
- AGENTS 和长期任务文档仅导入；本轮没有启动长期业务开发。

## 实际验证

原包校验和25项逐项通过。根目录布局、隐藏文件、UTF-8/LF、Markdown代码围栏、相对文档链接、git diff --check、环境报告字节一致检查通过；数量见 FOUNDATION_VALIDATION_20261012.json。

此前基础程序和6项 smoke 测试的真实结果见 ../ENVIRONMENT_CHECK.md。文档导入不能证明业务程序、PostgreSQL、依赖下载、微信真机或部署通过，这些仍 NOT_RUN。

## 发布与边界

发布通过已授权 GitHub 接口创建树、提交和更新本任务分支。终端直接 git push 认证没有重新配置，不能宣称其通过。

本轮 PR 目标 main，草稿、不合并。提交 SHA、PR URL 和最终远端文件逐字节核验结果在实际发布完成后记录。没有调用其他执行环境，没有创建或运行 GitHub Actions。

## 发布后实际核验（2026-10-12 14:31 UTC）

- 导入提交：1e1aa561c330daa17938d618d5e8a39ebc636602。
- PR：https://github.com/liumingbu/local-shop/pull/1；draft=true，state=open，merged=false，head=chore/project-foundation，base=main。
- 云电脑 git fetch 后，55个远端文件与本地逐字节一致。main 仍为62be6e58，原验证分支仍为7bd637bf；环境报告完全保留。
- 本地分支对齐已发布提交后工作树干净。本节与进度/交接是后续状态补记，不声称包含自身SHA。
