# 浏览器有限排障：2026-10-14

基准640148dd84d6241eea399ccfc5552d0d324fc001。先读m2失败报告，再检查同机Chromium154.0.8037.57和Playwright1.64。

本阶段唯一一次独立启动探测：`chromium.launch({executablePath:"/usr/bin/chromium", headless:true, chromiumSandbox:true, timeout:15000})`，07:19:07UTC，退出码2。

失败仍在浏览器启动阶段：process_singleton_posix.cc:297 socket() failed: Operation not permitted；另有crashpad目录/参数错误。没有执行DOM断言、没有访问页面，实际截图/轨迹不可获得。见attempt.txt。没有使用no-sandbox、改宿主权限、换浏览器执行环境或放宽API开发认证。

到此结束浏览器排障。本阶段真实浏览器BLOCKED，后续Vue DOM组件测试明确标为jsdom，不代替浏览器或微信验收；继续可独立实现的页面和业务改进。
