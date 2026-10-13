# PostgreSQL 前置验证：BLOCKED

时间：2026-10-12 14:55–14:58 UTC。环境：Dot 当前云电脑。
基准代码/文档 SHA：6f4c99bf3f34b50fa74aa3a1140639c2164bc2c8；开始时工作树干净。
本轮只做独立环境验证，未创建 M1 工程分支或业务源码。

## 实际执行

1. PATH 查找 psql/postgres/initdb/pg_ctl/pg_config/docker 均未发现；不据此断言整个磁盘没有安装。
2. apt-get download postgresql-17 postgresql-client-17 libpq5：退出100；提示配置文件读取受限及无法定位包。未更改系统APT配置。
3. python3 -m venv local-shop-tools/venv：退出0。
4. 通过 PyPI 在该虚拟环境安装 pgserver==0.1.4、psycopg[binary]：退出0；锁定结果见 pg-preflight-requirements.txt。没有安装外部执行器。
5. 包内 postgres --version：PostgreSQL 16.2，退出0。该旧补丁二进制仅用于能力探测，不是选定的生产版本，也不代表当前受支持补丁版已锁定。
6. initdb -D local-shop-tools/pg-smoke-data -A trust --no-locale --encoding=UTF8：退出0。仅合成隔离数据，未配置TCP监听，未建立生产凭据。
7. pg_ctl -D local-shop-tools/pg-smoke-data -l local-shop-tools/postgres.log -o "-k local-shop-tools/pg-socket -h '' -p 55432" -w start：退出1。
8. 在同一云电脑通过允许的提权通道重试同一启动命令：退出1；未更换执行环境。

以上路径在实际命令中均使用云电脑工作目录的绝对路径。本记录相对路径用于说明，不是承诺可以从任意工作目录复制执行。

## 错误证据

```text
could not create Unix socket ...: Operation not permitted
FATAL: could not create any Unix-domain sockets
database system is shut down
```

数据库进程两次均退出，没有可连接的运行实例。详细脱敏日志：postgres-startup-20261012.txt。

## 判定

- Python虚拟环境及所列PyPI依赖安装：PASS。
- PostgreSQL二进制运行及initdb：PASS。
- PostgreSQL服务启动：BLOCKED（本地socket操作被拒绝）。
- 连接、事务、SQLAlchemy/Alembic迁移、租户数据库测试：NOT_RUN。
- 并非SQLite或mock验证；未声明数据库集成通过。
- 文档PR #1仍open/draft/未合并；main仅初始README，因此M0整体仍未满足，M1依赖基线等待审批。

## 下一步

用户审阅合并PR #1，或明确授权合并。之后可推进无数据库依赖的配置、存活检查和单元测试。真实PG集成需要在同一云电脑具备允许的本地服务运行能力；不自行切换环境或绕过限制。
