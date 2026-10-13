const fs=require('node:fs'); const path=require('node:path');
if(process.argv.includes('--clean')) { fs.rmSync('dist',{recursive:true,force:true}); process.exit(0); }
const app=JSON.parse(fs.readFileSync('app.json','utf8'));
const files=['app.json','app.wxss',...app.pages.flatMap(page=>['json','wxml','wxss'].map(ext=>`${page}.${ext}`))];
for(const file of files){const target=path.join('dist',file);fs.mkdirSync(path.dirname(target),{recursive:true});fs.copyFileSync(file,target);}
console.log(`Copied ${files.length} native assets; this is NOT a WeChat runtime test.`);
