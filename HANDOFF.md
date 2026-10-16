# HANDOFF

2026-10-16；E—H新增授权来源docs/PILOT_PREPARATION_TASK_20261016.md。起点main265bf0a2a256f45b50e85fe7a327d00bdc9eb11e，开放PR0，起点工作树干净；A—D保留复用。

当前fix/formal-auth-proxy-boundary：H1真实Nginx TLS→API/PG复现共享回环限频（来源A10次后来源B429）。最小修复仅正式计数采纳显式确切代理IP下由Nginx覆盖的专用来源头，默认关闭，与开发身份互斥；request.client/Uvicorn不变。不信XFF/X-Real-IP，不改真实权限或部署。对照复测来源B201且A伪造头仍429；非可信直连改变头仍429。

PR25代码79b83d4444e1eff95419ad38b837196c171d94de远端干净检出254 Python（183PG）与真实代理/Linux专项全部退出0。报告后按授权合并H1。E已在同机local-shop-pilot工作树独立实施开店准备/CSV，下一步合入最新main并重新验证；不切换执行环境。F备货导出、G站内更新/人工联系、H故障收口依次推进。PROGRESS为唯一状态表；不得因历史交付停止本轮授权任务。

不再尝试浏览器排障，不切换执行环境；真实浏览器/WXML/微信工具与真机/真实AppID交换/外部消息/systemd/生产未验收。用户普通PR自查测试合并已授权；生产、真实凭据权限/删除、费用/外部环境、微信提审仍另确认。E—H最终交付商户指南、合成场景、源码及未验清单后停止扩展。
