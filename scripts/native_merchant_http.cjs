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
(async()=>{
  await client.login('merchant-a');const tenants=await client.request('/api/v1/merchant/tenants'),A=tenants.items[0].id,base=`/api/v1/merchant/tenants/${A}`;
  const settings=page('shopsettings');settings.onLoad({store_id:A});await idle(settings);assert.ok(settings.data.authorized,settings.data.error);
  // Save the current public profile unchanged; this does not disturb earlier restart assertions.
  const oldVersion=settings.data.form.version;await settings.save();assert.equal(settings.data.form.version,oldVersion+1,settings.data.error);
  const work=page('merchant');work.onLoad({store_id:A});await idle(work);assert.equal(work.data.tenantId,A,work.data.error);assert.equal(work.data.counts.length,6);
  work.input(input('合成电话顾客','customer_label'));work.input(input('不要商品库，先记0.5斤合成商品，明天下午来取','raw_text'));work.input(input('合成内部备注','internal_note'));await work.create();assert.ok(work.data.lastId,work.data.error);
  const id=work.data.lastId,detail=page('merchantdetail');detail.onLoad({store_id:A,record_id:id});await idle(detail);assert.equal(detail.data.row.status,'PENDING_CONFIRMATION',detail.data.error);assert.equal(detail.data.row.items.length,0);
  const original=detail.data.row.raw_text;detail.input(input('合成规格0.75斤，改到后天','summary'));detail.input(input('电话再次沟通','changeReason'));detail.addItem();detail.item(input('合成商品','name',0));detail.item(input('0.75','quantity',0));detail.item(input('斤','unit',0));detail.date({detail:{value:'2026-10-15'}});await detail.propose();assert.equal(detail.data.row.confirmation_revisions.length,1,detail.data.error);assert.equal(detail.data.row.raw_text,original);
  await detail.transition({currentTarget:{dataset:{status:'CONFIRMED'}}});assert.match(detail.data.error,/重新确认/);
  detail.check({detail:{value:['agreed']}});await detail.transition({currentTarget:{dataset:{status:'CONFIRMED'}}});assert.equal(detail.data.row.status,'CONFIRMED',detail.data.error);
  for(const status of ['PREPARING','READY','COMPLETED']){await detail.transition({currentTarget:{dataset:{status}}});assert.equal(detail.data.row.status,status,detail.data.error);}
  work.filter({currentTarget:{dataset:{status:'COMPLETED'}}});await idle(work);assert.ok(work.data.records.some(x=>x.id===id),work.data.error);
  detail.onHide();assert.equal(detail.data.row,null);assert.equal(detail.data.images.length,0);
  await client.login('merchant-b');await assert.rejects(client.request(base+`/reservations/${id}`),{status:404});await assert.rejects(client.request(base+`/reservations/${id}/transitions`,'POST',{expected_version:6,target_status:'CANCELLED'},'native-merchant-cross-write'),{status:404});
  const denied=page('merchant');denied.onLoad({store_id:A});await idle(denied);assert.equal(denied.data.form,null);assert.match(denied.data.error,/授权范围/);
  await client.login('customer-a');await assert.rejects(client.request(`/api/v1/me/records/reservation/${id}`),{status:404});
  const inquiry=await client.request(`/api/v1/stores/${A}/inquiries`,'POST',{raw_text:'合成咨询，是否能预留？',privacy_accepted:true},'native-merchant-inquiry');
  const wanted=await client.request(`/api/v1/stores/${A}/reservations`,'POST',{raw_text:'合成取消流程',privacy_accepted:true},'native-merchant-cancel-record');
  await client.request(`/api/v1/me/reservations/${wanted.id}/cancellation-requests`,'POST',{expected_version:wanted.version,reason:'合成改期'},'native-merchant-cancel-intent');
  await client.login('merchant-a');const q=page('merchantdetail');q.onLoad({store_id:A,record_id:inquiry.id,kind:'inquiry'});await idle(q);q.input(input('合成内部询问库存记录','replyText'));await q.reply();assert.equal(q.data.row.status,'NEW',q.data.error);assert.equal(q.data.row.converted_reservation_id,null);
  q.input(input('合成公开答复，请确认规格','replyText'));q.check({detail:{value:['visible']}});await q.reply();assert.equal(q.data.row.status,'REPLIED',q.data.error);assert.equal(q.data.row.converted_reservation_id,null);
  q.input(input('合成顾客','customerLabel'));q.input(input('已明确需要合成规格一份','conversionText'));await q.convert();assert.ok(q.data.row.converted_reservation_id,q.data.error);const converted=await client.request(base+`/reservations/${q.data.row.converted_reservation_id}`);assert.equal(converted.status,'PENDING_CONFIRMATION');assert.equal(converted.raw_text,inquiry.raw_text);await q.close();assert.equal(q.data.row.status,'CLOSED');
  const cancelled=page('merchantdetail');cancelled.onLoad({store_id:A,record_id:wanted.id});await idle(cancelled);assert.equal(cancelled.data.actions.length,0);cancelled.input(input('合成商户同意改期取消','responseNote'));await cancelled.decision({currentTarget:{dataset:{decision:'ACCEPTED'}}});assert.equal(cancelled.data.row.status,'CANCELLED',cancelled.data.error);
  await client.login('customer-a');const publicView=await client.request(`/api/v1/me/records/inquiry/${inquiry.id}`);assert.equal(publicView.replies.length,1);assert.equal(publicView.replies[0].text,'合成公开答复，请确认规格');
  console.log('PASS compiled native merchant logic + REAL HTTP/PG: store version update/manual phone record/decimal confirmation/explicit agreement/prepare/ready/complete/history/tenant read+write denial/inquiry reply+convert/cancel decision');
  console.log('SIMULATED wx transport and page lifecycle; NOT WeChat runtime, WXML, real identity, device or sharing validation.');
})().catch(error=>{console.error(error.code==='ERR_ASSERTION'?error.stack:(error.code||'Native merchant HTTP scenario failed'));process.exitCode=1;});
