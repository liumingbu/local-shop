# 使用说明｜把文档交给 Dot

## 先明确本包是什么

这是 `local-shop` 的初始化文档包，不是应用源码包。Markdown 是项目正式文件，解压后要放入仓库根目录，不要只把 ZIP 存进仓库，也不要套一层 `local-shop-bootstrap/` 目录。

本包包含隐藏文件 `.gitignore`、`.env.example`、`.editorconfig`、`.gitattributes` 和 `.github/`。提交时也要检查这些文件。

## 推荐路径：由用户建立最小基线，Dot 导入其余文档

1. 打开 `https://github.com/liumingbu/local-shop`，先确认仓库可见性是否符合你的打算。当前会话检查时为 Public；不会自动替你更改。
2. 如果 Dot 已有真实提交，先查看它的报告和分支，不重复初始化。
3. 如果仍完全为空，在 GitHub 页面点击创建新文件的入口（通常是“creating a new file”），新建 `README.md`，内容可先写 `# local-shop`。由你本人完成首个 main 提交。
4. 将本 ZIP 上传到 Dot 对话，发送下方“导入文档指令”。Dot 必须使用自己的云电脑，不在你的 Mac 操作。
5. 查看文档 PR 的文件差异，确认仓库根目录能看到 `AGENTS.md`、`HANDOFF.md`、`README.md` 和 `docs/`，再由你审阅合并。
6. 将 `docs/DOT_LONG_TERM_TASK.md` 的完整内容发送给 Dot。后续用 GitHub 文档和 PR 保存状态，不依赖此对话历史。

如果环境验证尚未通过，Dot 先补验证；不能以文件上传成功代替程序运行/测试能力。

## 导入文档指令

```text
请使用你自己的 Dot 云电脑，将我上传的 local-shop 初始化文档包导入
https://github.com/liumingbu/local-shop。

先检查当前仓库、分支、未提交改动和你之前环境验证的真实结果。
不要调用 Codex、Work、Actions、Codespaces 或我的 Mac。

如果远端已有 main，从 main 创建 chore/project-foundation；若该分支已存在，
核对是否属于本任务再继续，不覆盖其他工作。如果 main 仍不存在，停止并让我
建立初始 README，未经明确授权不要直接写 main。

将压缩包内的 README.md、AGENTS.md、HANDOFF.md、docs/ 及隐藏配置文件
放在仓库根目录；不是把 ZIP 本身作为项目文件，也不要套额外目录。
保留已有环境验证报告和用户已有内容；有内容冲突先做差异核对。

核对文档中的初始状态，补充你的真实环境报告，不把未测项改成通过。
本包记录的是之前一次检查，不代表你现在的环境或仓库状态。

提交并推送分支，创建指向 main 的 PR，不合并；返回真实提交 SHA、PR 链接
和远端文件核验结果。权限不足就给出错误、保留文件，不切换开发环境。
```

## 备选：完全由网页上传

若 Dot 仍无法写入，你可以解压包后在 GitHub 上传文件，不需要安装开发环境。

已有 main 时使用 Add file → Upload files，拖入包内文件和 `docs/`、`.github/` 文件夹，保持目录结构，选择创建新分支 `chore/project-foundation` 并发起 PR。文件选择器可能隐藏以点开头的文件，提交前检查是否遗漏；也可以分别用 Create new file 建立缺失文件。

完全空仓库先按前面的步骤建立 README。不要在未经检查的情况下覆盖 Dot 已创建的源码或报告。

## 关于权限错误

读取到仓库 `permissions.push=true` 反映的访问上下文，与某次连接器写入请求能否成功不是同一个验证结果。本次真实写入返回 403；不能靠改提示词给连接器增加权限。

可以检查 GitHub 已安装应用所允许的仓库和写入操作；如果应用本身没有请求写权限，勾选仓库也未必足够。Dot 自己的云浏览器登录、Git 凭据和当前 ChatGPT 连接器是不同路径，必须各自实际验证。不要在聊天或仓库中粘贴令牌。

若使用 Dot 云浏览器人工登录，由你接管并完成登录/验证后交还控制，不能把你自己浏览器的登录状态当作 Dot 已登录。

## 外部参考（查询日期 2026-10-12）

- OpenAI：Getting started with your dot。云电脑、应用连接和本地访问分别控制；实际可用性仍要测试。https://help.openai.com/en/articles/20001530-getting-started-with-your-dot
- GitHub：Troubleshooting the REST API，Resource not accessible。https://docs.github.com/en/rest/using-the-rest-api/troubleshooting-the-rest-api
- GitHub：Adding a file to a repository。https://docs.github.com/en/repositories/working-with-files/managing-files/adding-a-file-to-a-repository

本包不承诺额度免费、活动持续时间或自动获得写权限。
