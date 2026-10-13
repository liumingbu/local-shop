# local-shop｜实体商户店铺与预订备货助手

**开发准备文档包 v0.1 · 2026-10-12**

仓库：`https://github.com/liumingbu/local-shop`

一个微信小程序承载多个商户，各店独立展示、管理询货和需求登记、安排备货与交付。顾客可以自行提交，老板也可以代记微信、电话、到店产生的需求。**不接入在线支付。**

## 当前状态：文档基线，不是可运行的软件

本包已生成产品需求、开发约束、架构建议和验收计划；没有业务源码、依赖锁文件或真实应用运行结果。

- main 基准已核验：`62be6e588b375c2cab90364472322b96f8c5f9e8`。
- Dot 云电脑文件操作、程序运行及六项 Python/Node 测试通过；GitHub 接口提交已回读验证。见 [真实环境报告](docs/ENVIRONMENT_CHECK.md)。
- 原环境验证分支 `env-check/20261012` 及其提交 `7bd637bf3b0c90852285048ed08d76db0c7ddb44` 保留。
- 本轮仅在 `chore/project-foundation` 导入文档，未实现业务程序、未部署、未合并 main。
- 数据库、依赖安装、微信、浏览器和业务测试仍为 NOT_RUN；终端直接 git push 认证仍未通过，发布使用 GitHub 接口。
- 包生成时的旧状态保留于 [原始记录](docs/evidence/package-original/README.md)，不能作为当前状态。

## 先读这些文档

| 文件 | 用途 |
|---|---|
| [START_HERE](docs/START_HERE.md) | 用户如何上传文档并启动 Dot |
| [DOT_LONG_TERM_TASK](docs/DOT_LONG_TERM_TASK.md) | 可以直接交给 Dot 的完整长期任务 |
| [AGENTS](AGENTS.md) | 所有开发轮次必须遵守的约束 |
| [HANDOFF](HANDOFF.md) | 当前工作位置与恢复入口 |
| [PRD](docs/PRD.md) | 用户、功能、页面和首版范围 |
| [ARCHITECTURE](docs/ARCHITECTURE.md) | 推荐技术基线与运行方式 |
| [DATA_MODEL](docs/DATA_MODEL.md) | 多租户、需求状态、数据约束 |
| [API_CONTRACT](docs/API_CONTRACT.md) | 接口草案与权限约定 |
| [ROADMAP](docs/ROADMAP.md) | 分阶段任务、依赖与验收 |
| [PROGRESS](docs/PROGRESS.md) | 任务状态唯一台账 |
| [TESTING](docs/TESTING.md) | 测试矩阵、结果登记与真实性规则 |
| [ENVIRONMENT_CHECK](docs/ENVIRONMENT_CHECK.md) | Dot 环境验证格式与门槛 |
| [GITHUB_WORKFLOW](docs/GITHUB_WORKFLOW.md) | 空仓库初始化、分支、提交与 PR |
| [SECURITY](docs/SECURITY.md) | 租户隔离、身份、隐私与文件访问 |
| [EXTERNAL_DEPENDENCIES](docs/EXTERNAL_DEPENDENCIES.md) | 微信、备案、凭据与上线阻塞 |
| [DEPLOYMENT](docs/DEPLOYMENT.md) | 部署交付要求；当前不是已验证命令 |
| [DECISIONS](docs/DECISIONS.md) | 已确定约束与建议决策 |

## 开发方式

只在 Dot 自己的云电脑编写、运行和测试。GitHub 保存已提交的版本；不得依赖用户 Mac 在线，不得擅自使用 Codex Cloud、本地 Codex、ChatGPT Work、Codespaces、其他计算环境或第三方付费任务。GitHub Actions 默认不启用。

普通读写文件、安装不额外收费的开发依赖、开发分支提交与创建 PR 可以在授权范围内进行。主分支写入/合并、生产部署、真实数据删除、凭据变更、付费服务和外部执行环境必须事先确认。

## 首个业务闭环

先完成：**商户 A 创建店铺 → 代记一条电话需求 → 确认 → 备货 → 完成 → 查历史；商户 B 无权访问 A 的任何私有记录。**

先用自动化接口测试和 Web 工作台证明核心逻辑真实可用，再接入顾客小程序和微信真实能力。

## 如何运行

目前没有可运行程序。Dot 在 M1 实现工程后，必须用真实执行结果替换本节，提供依赖安装、数据库迁移、启动、测试和演示数据初始化命令。不要猜测不存在的 `npm run` 或脚本。

## 数据和许可证

仅提交合成演示数据。不得上传真实客户资料、身份证件、电话地址、AppSecret、数据库备份或令牌。仓库可见性由用户决定，公开仓库也不代表已选定开源许可证；本包未添加开源授权。
