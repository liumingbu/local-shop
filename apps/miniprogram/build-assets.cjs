const fs = require('node:fs');
const path = require('node:path');
for (const file of ['app.json', 'app.wxss', 'pages/index/index.json', 'pages/index/index.wxml', 'pages/index/index.wxss']) {
  const target = path.join('dist', file);
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.copyFileSync(file, target);
}
console.log('Assets copied; this is not a WeChat runtime test.');
