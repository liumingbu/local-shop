# GitHub 工作流与空仓库处理

## 1. 准入规则

目标仓库仅 `liumingbu/local-shop`。不得自动换仓库、fork、公开/私有切换或把结果提交到邻近项目。角色元数据不替代实际写入验证。

## 2. 完全空仓库

分支列表为空时没有正常PR比较基线。推荐用户在GitHub网页建立一个最小README提交到main；这是用户的直接操作，不是Dot的长期main权限。

用户也可明确授权“仅一次创建初始README到main”。Dot须先确认远端确实仍空，再执行最小初始化，读回SHA，后续文档/代码全部走分支与PR。没有授权就等，不直接推main。

禁止把main直接指到包含全部尚未审阅功能的提交，冒充初始化。不要制造无共同祖先的孤立分支再强行合并。

## 3. 分支约定

- `chore/environment-check`：真实Dot环境报告。
- `chore/project-foundation`：本次文档基线。
- `feat/m1-foundation`：工程基础。
- `feat/merchant-records`、`feat/catalog`等：可验收功能。
- `fix/<问题>`：缺陷。

命名可按实际调整。每次分支创建之前检查同名分支，不覆盖已有工作；工作树不干净时先识别来源。

## 4. 正常流程

读取远端main和现有PR → 创建功能分支 → 实现与测试 → 更新必要文档 → 检查diff和敏感信息 → commit → push → 读取远端核对SHA → 创建PR → 用户审阅合并。

允许一个PR承载一组密切相关的子任务，避免人为把每一步拆碎。主分支写入/合并、强推、删分支需要确认。

## 5. PR内容

功能目标、关联需求ID、实际改变、测试命令与结果、未测试内容、风险、迁移/回滚、下一步依赖。模板位于 `.github/pull_request_template.md`。

PR创建失败但推送成功，提供分支和真实commit链接，记录PR权限阻塞；不得同时宣称PR完成。

前一个PR尚未合并而下一个依赖它时，等待或做无依赖任务。未经批准不使用堆叠PR/长期集成分支规避审批。

## 6. 恢复与保全

每轮结束前提交可保存的代码和交接，未完成分支/PR标注WIP；不把不通过测试的模块标记完成。推送失败则保存补丁或文件包，并记录基准SHA和恢复方式。

不得通过reset --hard、强推、覆写工作目录解决不明冲突。清理测试产物仅针对可再生的项目测试目录。

## 7. 凭据和集成权限

GitHub连接器、Dot云浏览器登录、Git凭据各自独立验证；读权限不代表写权限。出现403应报告并请求正确权限，不连续重试或绕过。

GitHub官方将“Resource not accessible by integration”归于相应token权限不足；可检查应用授予的仓库范围和写入权限。不要把用户账号具有admin角色等同于应用token可以写。

参考：https://docs.github.com/en/rest/using-the-rest-api/troubleshooting-the-rest-api

## 8. 执行额度

本包不包含Actions workflow，不启用自动CI，不创建Codespaces。后续需要CI先确认运行资源、触发方式和额度；即使获得批准，CI结果仍不替代Dot云电脑环境检查。
