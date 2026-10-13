# HANDOFF

2026-10-13 UTC。用户授权Dot自查测试后合并常规PR；环境/费用/生产边界不变。

- PR #1–#16已合并并fetch核验；当前main起点98daed9c191254a4c6e11442144b84432a0d68c7，起点工作树干净。
- feat/backup-restore-delivery：新增local_shop.recovery离线备份/核验/恢复CLI及scripts/backup_restore_drill.py，迁移仍0009。RECOVERY.md明确停写、可信包、独立空库、无覆盖/删除、失败保留/不启服。
- 206 Python（154真实PG）+18 Web+54原生及Ruff/TS/构建/HTTP/PG重启/恢复演练本地通过；PR #17代码ca64e8a5独立远端干净检出全部复核通过，CLI恢复21表/92合成行/3图片；见evidence/recovery/RESULT_20261013.md，待自查合并。
- 备份包含PG custom archive和规范UUID图片，检查DB中的大小/哈希；恢复到另一库及新图片目录，再重启PG/API检验记录/私图权限/幂等。临时包不上传。
- 浏览器DOM/WXML/微信真实能力、正式身份与生产部署仍未验收。没有沿用旧项目AppID；官方微信文档访问返回不可用页面，不能据此称M5验证通过。
- 下一步完成当前分支远端检出/证据/合并，补Linux交付与真实可执行检查，再形成源码验收包；保持真实微信和生产阻塞。
