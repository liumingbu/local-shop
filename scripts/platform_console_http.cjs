/** Execute compiled native page logic against real HTTP/PG through a simulated wx transport.
 * This does NOT run WXML, developer tools, a WeChat account, camera or real sharing.
 */
const assert=require('node:assert/strict');const fs=require('node:fs');const path=require('node:path');
const {setup,page,idle,input}=require('../tests/miniprogram/harness.cjs');
const {client,state,config}=setup();config.apiOrigin=process.argv[2];
const fixture=process.argv[3],downloadDir=process.argv[4];
if(!fixture||!downloadDir)throw new Error('Isolated fixture and output directory required');
let downloadCount=0;
wx.request=options=>{
  state.calls.push(options);
  void (async()=>{
    try{
      const response=await fetch(options.url,{method:options.method,headers:options.header,redirect:'manual',signal:AbortSignal.timeout(10000),
        ...(options.data===undefined?{}:{body:options.data instanceof ArrayBuffer?options.data:JSON.stringify(options.data)})});
      const data=await response.json();options.success({statusCode:response.status,data,header:{},cookies:[]});
    }catch{options.fail({errMsg:'HTTP request failed'});}
  })();return{abort(){}};
};
wx.downloadFile=options=>{
  void(async()=>{try{const response=await fetch(options.url,{headers:options.header,redirect:'manual'});const bytes=Buffer.from(await response.arrayBuffer());
    assert.equal(response.status,200);assert.equal(bytes[0],255);assert.equal(bytes[1],216);
    const file=path.join(downloadDir,`native-private-${++downloadCount}.jpg`);fs.writeFileSync(file,bytes);
    options.success({statusCode:200,tempFilePath:file});}catch{options.fail({errMsg:'Private image unavailable'});}})();return{abort(){}};
};
wx.chooseMedia=options=>options.success({tempFiles:[{tempFilePath:fixture,size:fs.statSync(fixture).size}]});
wx.compressImage=options=>options.success({tempFilePath:options.src}); // Fixture, not actual WeChat compression.
wx.getFileSystemManager=()=>({readFile(options){const bytes=fs.readFileSync(options.filePath);options.success({data:bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength)});}});
const {PlatformConsole,platformState}=require('../tests/admin/.compiled/platform.js');
const {request:adminRequest}=require('../tests/admin/.compiled/api.js');
const networkFetch=global.fetch;global.fetch=(url,options)=>networkFetch(typeof url==='string'&&url.startsWith('/')?config.apiOrigin+url:url,options);
(async()=>{
  const adminToken=(await adminRequest('/api/v1/dev/session','','POST',{identity:'platform-admin'})).access_token;
  const uid=(await adminRequest('/api/v1/dev/me',adminToken)).user_id;
  const saved=new Map(),storage={getItem:key=>saved.get(key)||null,setItem:(key,value)=>saved.set(key,value)};
  const control=platformState(),controller=new PlatformConsole(control,(path,method,body,key)=>adminRequest(path,adminToken,method,body,key),storage,uid);
  await controller.load();assert.equal(control.ready,true,control.error);
  await controller.invite('00000000-0000-4000-8000-000000000003','合成Web控制台邀请店','合成后台邀请记录');assert.equal(control.locked,false,control.error);
  let invitation=control.invitations.find(x=>x.proposed_name==='合成Web控制台邀请店');assert.ok(invitation);assert.equal(invitation.status,'INVITED');
  await controller.review(invitation,'APPROVED','不应跳过收件人');assert.equal(control.error,'INVITATION_REVIEW_NOT_ALLOWED');
  await client.login('customer-b');const wrong=page('invitations');wrong.onLoad();await idle(wrong);assert.equal(wrong.data.items.some(x=>x.id===invitation.id),false);
  await client.login('customer-a');const mine=page('invitations');mine.onLoad();await idle(mine);assert.ok(mine.data.items.some(x=>x.id===invitation.id),mine.data.error);
  await mine.respond({currentTarget:{dataset:{id:invitation.id,decision:'ACCEPTED'}}});assert.equal(mine.data.locked,false,mine.data.error);assert.equal(mine.data.items.find(x=>x.id===invitation.id).status,'ACCEPTED');
  await controller.load();invitation=control.invitations.find(x=>x.id===invitation.id);await controller.review(invitation,'APPROVED','合成审核通过');assert.equal(control.error,'',control.error);
  invitation=control.invitations.find(x=>x.id===invitation.id);assert.equal(invitation.status,'APPROVED');await mine.load();mine.enter({currentTarget:{dataset:{id:invitation.id}}});assert.ok(state.navigation.at(-1).endsWith(`store_id=${invitation.tenant_id}`));
  const store=await client.request(`/api/v1/merchant/tenants/${invitation.tenant_id}/store`);assert.equal(store.published,false);
  let tenant=control.tenants.find(x=>x.id===invitation.tenant_id);await controller.status(tenant,'SUSPENDED','合成暂停核验');tenant=control.tenants.find(x=>x.id===invitation.tenant_id);assert.equal(tenant.status,'SUSPENDED');
  await assert.rejects(client.request(`/api/v1/merchant/tenants/${tenant.id}/store`),{status:404});await controller.status(tenant,'ACTIVE','合成恢复');assert.equal(control.tenants.find(x=>x.id===tenant.id).status,'ACTIVE');
  assert.ok(control.audit.some(x=>x.action==='INVITE_SHOP_OWNER'));controller.dispose();assert.deepEqual(control.audit,[]);
  console.log('PASS compiled Web platform controller + native invitation page with REAL HTTP/PG: invite/recipient isolation/explicit accept/review/default private store/pause/resume/audit');
  console.log('Node controller and SIMULATED wx page lifecycle only; browser DOM and WXML/device remain NOT_RUN.');
})().catch(error=>{console.error(error.code==='ERR_ASSERTION'?error.stack:(error.code||error.message||'Platform console HTTP failed'));process.exitCode=1;});
