# 云端开发环境验证报告

日期：2026-10-12 UTC
目标仓库：https://github.com/liumingbu/local-shop
测试分支：env-check/20261012

## 结论

基础开发运行环境验证通过。重新配置 GitHub 授权后，已通过连接的 GitHub 接口成功初始化 README 并创建独立测试分支。本报告通过同一接口发布；发布后的提交、分支及文件回读由助手另行核验。

没有启动额外 Codex Cloud、ChatGPT Work 或本地 Codex 任务，没有使用用户本地电脑，没有切换开发环境。此结论不表示已完成业务项目开发，也不对套餐计费作保证。

## 实际检查

| 项目 | 结果 |
| --- | --- |
| 云端终端 | 可用 |
| Git | 2.52.0 |
| Node.js | v24.19.0 |
| npm | 11.9.0 |
| Python | 3.12.14 |
| 创建、修改、回读代码文件 | 成功 |
| Python 最小程序 | 输出 cloud smoke verified: 5，退出码 0 |
| Python unittest | 3/3 通过 |
| Node.js test，经 npm test 执行 | 3/3 通过 |
| 本地 Git 初始化及提交 | 成功 |
| GitHub 仓库读取 | 成功 |
| GitHub 权限元数据 | pull/push/admin/maintain/triage 均为 true；不等同于全部操作均已测试 |
| GitHub README 写入 | 成功，提交 62be6e588b375c2cab90364472322b96f8c5f9e8 |
| GitHub 独立测试分支创建 | 成功 |
| 终端直接 git push 认证 | 未通过；此前 dry-run 返回 fatal: unable to get password from user |

2026-10-12 14:23 UTC 再次运行 Python 程序与两套测试，全部通过。npm 有 Unknown env config "http-proxy" 警告，但退出码为 0。

本地四个验证文件的测试提交：563d9d3694cbd2224bf217404e3c37da4380ff79（仅本地提交，不是 GitHub 提交链接）。

## 授权和发布过程

- 初次检查仓库为 public、没有任何提交或分支；用户明确允许向当前公开仓库提交报告，并允许先在 main 初始化 README。
- 首次 GitHub 接口写入返回 HTTP 403，Resource not accessible by integration，未成功写入。
- 用户随后表示已配置授权并要求重新验证。
- 重试 README 写入成功，再从该提交创建 env-check/20261012 分支。
- 开发运行发生在助手当前云电脑；远端发布使用已连接 GitHub 接口。不能把这表述成终端 git push 已成功。

## 可复现的最小验证文件

smoke.py：

```python
def add(a, b):
    return a + b

if __name__ == '__main__':
    print('cloud smoke verified:', add(2, 3))
```

test_smoke.py：

```python
import unittest
from smoke import add

class SmokeTests(unittest.TestCase):
    def test_positive(self): self.assertEqual(add(2, 3), 5)
    def test_zero(self): self.assertEqual(add(0, 0), 0)
    def test_negative(self): self.assertEqual(add(-2, 3), 1)

if __name__ == '__main__': unittest.main()
```

smoke.test.cjs：

```javascript
const test = require('node:test');
const assert = require('node:assert/strict');
function add(a, b) { return a + b; }
test('positive', () => assert.equal(add(2, 3), 5));
test('zero', () => assert.equal(add(0, 0), 0));
test('negative', () => assert.equal(add(-2, 3), 1));
```

package.json：

```json
{"name":"local-shop-env-smoke","private":true,"version":"0.0.0","scripts":{"test":"node --test smoke.test.cjs"}}
```

执行命令：

```sh
python3 smoke.py
python3 -m unittest -v
npm test
```

## 验证边界

本次未验证业务功能、第三方依赖下载、数据库、浏览器 UI、生产部署、长期后台运行、跨会话文件持久性或 GitHub Actions CI。测试没有安装任何外部依赖。没有修改仓库可见性或合并测试分支。

## 后续补查：2026-10-12 14:58 UTC

基础验证原文和结果保留。新验证：虚拟环境和PyPI依赖安装成功；PostgreSQL 16.2二进制及initdb成功，但服务启动因Unix socket Operation not permitted失败，提权重试也失败。真实数据库连接、事务与迁移未运行；DB_INTEGRATION_OK不成立。该二进制仅做预检查，不作为生产版本建议。

详见 [数据库预检查](evidence/POSTGRES_PREFLIGHT_20261012.md)。文档PR #1仍待合并，因此M0整体未完成。

## 2026-10-13补查：本机TCP可用

Unix socket失败历史保留。本轮实际Uvicorn在127.0.0.1监听、HTTP存活200/数据库不可用时就绪503通过；PG16.2禁用Unix socket、使用127.0.0.1 TCP启动成功。独立命令结束后后台进程不可假定仍在，故使用scripts/test_with_postgres.py统一启动、测试、停止。

同一测试生命周期下：重启持久化通过，33项Python测试（含7项真实PG集成）通过。PG迁移升级/重复升级/降级重升、种子幂等、事务回滚、外键/角色约束、真实数据库就绪接口已测试。没有SQLite替代。前端和原生小程序TS/构建通过，微信工具/真机仍未测试。

这证明当前开发与数据库测试条件可用，不证明生产补丁/部署/长期在线条件可用。最终被测SHA与日志见M1报告。

## 2026-10-13补查：PostgreSQL16.15真实构建及回归

在同一Dot云电脑从官方16.15源码校验、编译、安装成功；新二进制在本机TCP上跑通122项测试（其中96项PG）和全部既有真实HTTP/重启检查，退出0。后续开发改用16.15，旧16.2结果不修改。
被测main SHA 89e7a595d04a49a12604e8335436f196e7eb5a77；来源/校验/构建命令与完整日志见[evidence/pg1615/RESULT_20261013.md](evidence/pg1615/RESULT_20261013.md)。浏览器和微信条件未因数据库升级改变。

## 2026-10-13补查：Nginx/TLS与systemd边界

同一Dot云电脑从官方源码编译Nginx1.30.5，openssl3.5.7/gcc14.2；启用http_ssl/http_v2模块。源码SHA256为6c20565aa2325cb82216ae804f4a4ff1875179014759a381c42ddc8e11c4906d。官方签名经隔离GPG验证退出0，匹配官方列出的Sergey Kandaurov公钥D6786CE303D9A9022998DC6CC8464D549AF75C0A；未改变全局信任，UID未有独立信任链认证。导入公钥曾因gpg-agent不可启动返回2，随后no-autostart签名校验成功，两者不混淆。

实际本机TCP运行Nginx+API+PG并分别握手TLS1.2/1.3，使用临时测试证书且仅本进程显式信任。代理权限/私图/幂等、HTTP固定域名跳转、正文413、限流429与查询串不落访问日志通过。单进程运行只证明组件，不证明正式服务管理。

systemd-analyze257.13已存在，但真实verify失败：Failed to create directory '/run/systemd/': Read-only file system。静态验证BLOCKED，systemd启停/开机启动NOT_RUN；未绕过文件系统限制。测试脚本可明确--skip-systemd重跑其他组件，必须保留这一遗漏。未部署、未新建外部计算环境。

## 2026-10-16 E—H本轮观察

再次实际执行：Git2.52.0、Node24.19.0、npm11.9.0、Python3.12.14、PostgreSQL16.15；终端/文件/实际PG实例和HTTP均用于本轮验证。远端写入采用已授权GitHub接口创建树/提交/分支/PR及自查后合并，随后Git fetch与树/SHA回读；未将本地commit或终端push推测为远端成功。H1/E/F实测证据分别见auth-proxy、merchant-preparation、fulfillment，G/H最新执行结果以TESTING为准。

浏览器没有重试，没有用户Mac、Codespaces、Actions、其他执行环境或额外Codex/Work任务。真实微信和生产仍未验证。F首次遇到PG连接超时、正式Vue等待超时和原生HTTP网络不确定，原码分别复测通过；资源快照不足以证明根因，记录为环境下的偶发现象，不据此放宽认证或生产超时。命令时间使用date -u；部分PG日志自身显示JST，不能与用户UTC+8混用。
