# 开发验证版验收入口

本交付定位：**DEV_REVIEW_READY**。已实现核心源码、合成自动回归、数据恢复及Linux代理组件；尚不能作为正式微信试用/营业版本。真实状态以PROGRESS与各被测SHA证据为准。

## 1. 本轮可以检查什么

- 老板无商品库代记电话/微信/到店需求；小数与单位、原始需求和确认候选分开；确认→备货→待自提/配送→完成→历史。
- 商户A/B服务端隔离，顾客只能访问已验证身份的本人记录；老板手填姓名电话不会自动认领账号。
- 分类/商品/多图/Logo、公开/草稿/归档；参考价不产生应付，不显示伪造库存。
- 询货回复与确定需求分离；私有图片、取消申请、明确确认与状态留痕；重复请求与并发版本保护。
- 一个原生小程序13页涵盖顾客、商户、本人邀请；Web用于代记、平台管理和商品批量维护。Web完成不代表微信完成。
- 平台定向邀请→本人接受/谢绝→人工批准/拒绝；店铺启停、操作审计；管理员身份与商户身份分离。
- 停写数据库+图片离线备份、完整性核验、另一空库/新目录恢复及重启后HTTP验证；不自动覆盖/删除原数据。

这些功能的服务端与客户端逻辑已测；页面视觉、完整浏览器DOM交互、微信渲染/工具/真机不在已通过范围。

## 2. 复现入口

从精确交付SHA或源码包开始，先按README安装锁定依赖。只使用明确隔离的开发目录和合成数据库。npm包和Python依赖未打进源码ZIP，首次安装需官方包源网络；PostgreSQL/Nginx二进制也不是源码包内置服务。

```sh
.venv/bin/ruff check apps/api tests scripts
npm run test:admin
npm run test:native
npm run typecheck
npm run build
PG_BIN=/path/to/postgresql-16.15/bin .venv/bin/python scripts/test_with_postgres.py
PG_BIN=/path/to/postgresql-16.15/bin .venv/bin/python scripts/e2e_with_postgres.py --http-only --native-client
PG_BIN=/path/to/postgresql-16.15/bin .venv/bin/python scripts/backup_restore_drill.py
PG_BIN=/path/to/postgresql-16.15/bin NGINX_BIN=/path/to/nginx-1.30.5/sbin/nginx .venv/bin/python scripts/linux_delivery_check.py
```

最后一个检查在当前Dot遇到systemd验证只读限制；可显式附加`--skip-systemd`运行其他组件，遗漏必须记NOT_RUN。不要把命令退出0等同所有外部项目通过。

原生构建导入说明在MINIPROGRAM.md；目前默认API为空、开发假登录关闭。测试脚本在受控回环环境设置合成身份，不能把模拟登录开放到公网。Web未配置正式身份入口，也不适合直接静态发布。

## 3. 测试覆盖与遗漏

最新完整自动回归索引见TESTING.md。Python含真实PostgreSQL（不使用SQLite替代）；Node原生测试模拟wx，HTTP回归则连接真实API/PG。两者共同不证明微信API本身可用。

仍缺：

- 正式微信登录适配器的实现与实测，以及正式平台管理员身份流程。
- 本项目有效AppID、安全服务端凭据、允许的微信工具/真机验证条件。
- 真正扫码/分享、合法域名/图片、隐私授权与消息模板能力。
- 完整浏览器页面与微信WXML渲染/交互、iOS/Android验证。
- systemd静态核验和真实生命周期、生产Nginx多进程、授权目标Linux部署/容量/灾备。
- 主体/类目/备案/资质、隐私文本与保留策略、投诉联系方式、发布批准。

当前云电脑的浏览器进程/连接条件及systemd只读限制均已记录；没有偷偷换用户Mac或外部环境完成它们。正式配置不沿用旧佳琪项目。

## 4. 下一阶段最小输入

先确认这是哪个新小程序的AppID、主体和拟用类目，以及可获准的微信开发者工具/真机验收方式。AppSecret、服务器密码等不发聊天，待需要时使用安全交付渠道。仅提供AppID也不等同授权部署或权限变更。

确认后先完成正式身份代码和隔离测试，再在获准条件下实测。若仍要求只在当前Dot执行，则保留当前不支持的微信工具/真机项目为BLOCKED，不让另一环境代跑后冒充Dot验收。

用户已授权常规PR自主合并，不必逐个审阅；部署、收费、环境/安全权限变更、真实数据操作和微信提审仍单独确认。
