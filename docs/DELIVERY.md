# local-shop 开发验证版交付索引

2026-10-13。交付等级：**DEV_REVIEW_READY**，不是PILOT_READY，也没有部署或微信提审。该等级只表示核心业务源码可复现、隔离自动测试通过和代码远端可核对；页面视觉与正式身份仍有明确未完事项。

## 版本证据

- 业务与Linux交付累计PR #1–#18已合并。
- 最后运行代码：b665273600146732647e9ac7b270ef7641b84d4f。
- Linux报告提交：af8948c700402f036155a5b2d433b55238f2f64b。
- PR #18实际合并：406ab69be3313b906834efa9cecddad5f194d878；fetch后树29dfe1869498e814c95fd70d0d9251c32708cd0f与功能分支一致。
- 本交付索引/交接更新只改文档。最终源码ZIP从其合并后的确切提交以git archive生成，ZIP comment保存该提交SHA；附件文件名和独立校验说明记录最终SHA/ZIP SHA256。未声称最终纯文档提交重新跑了业务测试。

## 交付内容

完整单仓库源码：原生TypeScript/WXML/WXSS小程序、Vue3/TS管理端、FastAPI服务；真实生成的Python/npm锁文件、配置样例、0001–0009迁移、仅开发环境使用的合成种子；测试代码/真实结果；Linux候选服务和TLS代理、离线备份恢复工具。

ZIP包括Git跟踪的隐藏配置文件，项目文件直接位于ZIP根目录；不包含.git、.env、真实客户数据、凭据、数据库备份、node_modules、venv、PostgreSQL/Nginx二进制或生成的dist。依赖安装和前端编译按README执行。没有另设收费托管服务，没有部署到用户服务器。

### 先看哪里

1. [阶段验收](ACCEPTANCE.md)：已实现范围、复现命令、未验收项与下一阶段输入。
2. [README](../README.md)：安装、配置、启动与测试。
3. [PROGRESS](PROGRESS.md)：唯一当前状态；[TESTING](TESTING.md)：历次实测索引。
4. [最新远端复核](evidence/linux-delivery/RESULT_20261013.md)：213 Python/18 Web/54原生与HTTP/恢复/TLS证据。
5. [原生小程序](MINIPROGRAM.md)：导入/模拟限制/13页与真实微信边界。
6. [部署候选](DEPLOYMENT.md)：Linux步骤、占位替换、发布门禁、授权与回滚。
7. [备份恢复](RECOVERY.md)：停写、一致性、可信自生成包、新空库和新图片目录、失败不自动覆盖。

## 核验源码包

在收到的ZIP上计算SHA256并与随包校验说明比较。ZIP完整性、文件清单和每个Git blob应与明确提交一致，不只比较文件数。

可使用自己选择的Python3环境读取ZIP版本标记（只读，不执行包内代码）：

```sh
python3 -c 'import sys,zipfile; z=zipfile.ZipFile(sys.argv[1]); print("commit:", z.comment.decode()); print("bad entry:", z.testzip()); print("files:", sum(not i.is_dir() for i in z.infolist()))' local-shop-dev-review-<SHA>.zip
```

`bad entry: None`只证明ZIP CRC完整，不代替SHA256/来源核对，也不证明业务测试通过。正式版本与源码GitHub提交链接以交付消息中实际核验值为准。

## 已验证与待验证

实测213 Python（154真实PG、59非PG），18 Web控制器、54原生模拟wx；真实HTTP/PG重启；CLI恢复21表92合成行3图；Nginx TLS1.2/1.3、413/429、私图权限和幂等。没有重复累计HTTP中再次运行的18 Web测试。

未完成/阻塞：正式身份适配器与管理端登录、真实AppID/安全凭据与微信工具/真机、完整DOM/WXML视觉交互、扫码分享/消息/隐私、主体/类目/备案、systemd与生产Linux生命周期、目标环境容量/灾备及发布批准。详见ACCEPTANCE和EXTERNAL_DEPENDENCIES。

当前不自动续增MVP外功能。下一阶段先补正式身份与真实微信验收条件，继续沿用独立分支/测试/PR与已获准自查合并流程；部署等额外授权不扩大。
