# 部署交付｜生产尚未实施

**业务源码与本机运行/测试已存在；生产部署和真实微信仍未验收。** 本文件是部署交付要求，不能直接当成生产操作命令。实际数据库+图片恢复工具及本机演练见[RECOVERY.md](RECOVERY.md)；Linux服务/反向代理候选和验证边界见第8节。

## 1. 目标

单台Linux运行API、数据库、管理Web和受控图片存储；原生小程序发布在微信。可用反向代理+Docker Compose，也可提供进程方式；不预先采购云数据库、对象存储、Kubernetes或负载均衡。

选择实际硬件前测量资源消耗，不声称任意2核2G必定满足。Dot云电脑只负责开发，不视作长期在线的生产托管。

## 2. 开发运行交付

仓库需要真实运行时版本、锁文件、配置示例、迁移、合成种子、启动、停止、测试和清理命令。必须明确所在工作目录，区分开发和生产。

配置样例仅允许占位；开发可使用合成用户，生产必须禁用模拟身份、弱口令和调试页面。开发用数据库不与真实库混用。

## 3. 上线前必须提供

应用制品/提交SHA、配置字段说明、数据库迁移顺序、健康检查、端口与反向代理、TLS配置位置、公开图/私有图访问方式、日志与磁盘检查、权限和备份、恢复步骤及证据。

记录未通过的微信/隐私/资质事项，不能只因为API启动就建议正式营业。

## 4. 数据库

提供版本化迁移，不只给一段手工建表SQL。空库初始化与已有库升级分别验证；初始化不能默认清空用户已有数据。

测试清库只允许明确的合成测试库。生产迁移/删除另行批准，执行前备份与验证回滚策略，破坏性迁移不得默认运行。

## 5. 图片与备份

数据库和私有/公开上传文件都需备份，记录版本与一致性处理。不能只备份DB遗漏图片。备份不可在公开静态目录或GitHub库，选择保存地点由用户确认。

必须至少在隔离测试环境做一次恢复演练，记录备份来源、恢复目标、验证记录数量与附件读取结果。

## 6. 回滚

代码回滚到明确SHA/镜像；配置版本与迁移兼容性同时检查。不可逆数据库变更须另有恢复方案。回滚不是简单重启旧容器或删除数据。

## 7. 授权

生成部署文件不等于授权上线。连接服务器、改防火墙、绑定域名、写生产数据、发送真实消息、提交微信审核和发布均在用户明确授权后执行。

本新项目不自动使用以前佳琪服务器IP、旧AnyService环境或历史AppID。

## 8. Linux候选交付（2026-10-13）

当前可执行交付是开发验证包，不是可直接营业的发布版。`scripts/production_preflight.py`在配置有效后仍以`BLOCKED_REAL_WECHAT_ACCEPTANCE`和退出码2拒绝生产服务启动：正式身份代码虽已实现，真实微信/真机/隐私与发布验收仍缺；缺少身份配置时更早以BLOCKED_CONFIGURATION拒绝。模板通过`ExecStartPre`调用它，不能删除检查或用开发登录绕过。直接手工启动Python进程不受这个服务门禁保护，属于不支持的发布方式。

文件：

- `infra/production.env.example`：配置字段，占位值不得写入真实凭据。
- `infra/systemd/local-shop-api.service.template`：候选API服务，只允许回环监听；专用非特权用户、只读系统目录、仅媒体目录可写、私有临时目录、0077 umask和有限重启。
- `infra/nginx/local-shop.conf.template`：放入Nginx的http上下文。TLS1.2/1.3、固定域名HTTP跳转、2MiB正文上限、每IP 10r/s和20突发/连接限制、API超时、关闭代理重试；私图经API鉴权，无上传目录静态映射。
- `scripts/linux_delivery_check.py`：创建并清理独立合成PG/API/Nginx实例，实测代理、TLS和限制；不连接既有数据库，不安装服务。

版本基线：Python3.12.14、Node24.19.0、PostgreSQL16.15、Nginx1.30.5；Python与npm使用仓库实际锁文件。Nginx1.30.5是本轮实测版本，不把模板兼容性泛化到发行版旧Nginx；`http2 on`需相应版本支持。

### 将来获得部署授权后的准备顺序

以下是待在授权目标Linux执行并复核的操作清单，本轮没有执行：

1. 确认新项目正式身份/微信/隐私/主体条件及发布批准；完成门禁后续代码与测试，不提供“跳过验收”开关。
2. 确认目标主机、DNS和合法TLS证书、PG备份位置/保留期、运行账户与端口。凭据通过安全配置渠道交付，不进聊天/Git/日志。
3. 以已核验提交建立只读版本目录，例如`/srv/local-shop/releases/<SHA>`；在该版本创建venv，按requirements.lock安装，检查`PYTHONPATH=apps/api`。媒体独立放`/srv/local-shop/shared/media`，不与版本目录一起删除。
4. 配置文件例如`/etc/local-shop/api.env`只允许受权账户读取。API使用业务专用PG账户，迁移账户权限单独审核；模板不创建账户或授予权限。数据库仅内网/本机可达，不默认开放公网5432/8000。
5. 替换服务模板所有占位：SERVICE_USER/GROUP、APP_ROOT、ENV_FILE、MEDIA_ROOT。环境中的媒体路径须与ReadWritePaths一致；实际用户/路径/PG服务名称须核对，不把样例当作已存在。
6. 替换代理所有占位：API_ADDRESS回环API、HTTP_BIND/HTTPS_BIND、SERVER_NAME、PUBLIC_ORIGIN固定HTTPS域名、TLS_CERT完整证书链、TLS_KEY及ACCESS_LOG。禁止把用户输入拼进模板；不得留下`@@`。云测试脚本的临时自签证书只用于测试，不可发布或导入系统信任。
7. 使用目标主机Nginx执行`nginx -t`，使用`systemd-analyze --man=no verify <service文件>`静态核验；通过后才在部署授权内安装并启动服务。服务生命周期、重启、开机启动、日志轮转、磁盘配额/容量和监控须在该目标真实测试。
8. 首次空库：用受保护环境执行`alembic -c apps/api/alembic.ini upgrade head`，检查current为0009_platform；不得运行开发seed。已有库升级：先停写并按RECOVERY.md生成/verify一致备份，检查当前版本与升级内容，再迁移。不把有数据的降级当成可靠回滚。
9. 真实TLS健康检查、正式登录、租户隔离、图像权限、重复请求、代理限流/超时、关闭API/数据库后的故障及恢复逐项验收。就绪检查是DB SELECT 1，不证明迁移版本、全部业务或微信可用。
10. 目前Web只有开发身份入口，本模板不向公网提供Web构建目录。正式平台管理员登录/授权和Web交付需单独完成；小程序真实工具编译/真机不可由Vite/TS代替。

### 日志与代理边界

访问日志为JSON且只记URI路径，不记查询串、Authorization、请求体或IP；API默认关闭Uvicorn访问日志，避免另一路记录查询参数。Nginx错误日志不受此自定义格式约束，运维仍须限制权限、保留期并脱敏，不能声称全部日志绝无隐私。禁止在URL中传凭据。

10r/s是实测初始限制，不是容量承诺。同一出口IP多用户会共享限额，正式试用应结合授权的合成负载测试调整；429携带Retry-After，客户端保留原幂等请求，不生成新业务请求重试。当前模板只直接面向客户端；若将来增加CDN/多级代理，须重新审查可信来源配置，不盲信X-Forwarded-For。

### 回滚与失败

失败先停写、保留证据。仅当旧代码与当前schema明确兼容才切回已核验版本；否则按RECOVERY.md恢复到新空库和新媒体目录、复核后再切换受保护配置。原库/文件不自动清空或覆盖。服务模板切换、生产恢复和真实数据迁移仍须授权。

### 当前实际验证边界

同一Dot云电脑已运行Nginx、真实TLS1.2/1.3和PG/API合成集成。Nginx采用单进程组件方式；生产master/worker管理、systemd启停/开机启动均NOT_RUN。
`systemd-analyze verify`实际失败：`Failed to create directory '/run/systemd/': Read-only file system`。未改系统安全设置。`--skip-systemd`只允许重跑其他组件并明确输出NOT_RUN，不能当成完整Linux服务验证通过。

上游依据：[Nginx官方下载](https://nginx.org/en/download.html)、[签名公钥](https://nginx.org/en/pgp_keys.html)、[HTTP核心指令](https://nginx.org/en/docs/http/ngx_http_core_module.html)、[代理指令](https://nginx.org/en/docs/http/ngx_http_proxy_module.html)。

## 增量升级与开发生命周期补充

同机开发运行由scripts/dev_stack.py start/status/diagnose/stop统一管理，数据保存在受控var/dev-stack，停止不清库；仅回环/合成身份，不能当生产服务。Dot执行调用可能隔离PID/网络，控制通过近期实例心跳与停止请求，不能把localhost链接当可公开访问地址。
正式升级仍先停写、备份、检查恢复路径，再alembic upgrade head；旧的已成功幂等请求必须还能安全重放。0010新联系字段默认空、0011新邀请账号码默认空时兼容旧成功载荷摘要；任何新增非空联系信息或改变命令仍冲突，不能借升级覆盖旧操作。旧成功响应快照保留，客户端随后读取最新详情。
scripts/upgrade_drill.py实际由0009旧后端生成合成数据，再升级0011，逐表比较所有旧字段值、图片字节、原始/确认/事件、旧幂等响应和权限，最后重启复核。真实升级/发布仍未授权；回退涉及业务数据时不能用破坏性downgrade代替恢复计划。
