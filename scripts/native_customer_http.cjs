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
  await client.login('merchant-a');const tenants=await client.request('/api/v1/merchant/tenants');const A=tenants.items[0].id;
  const base=`/api/v1/merchant/tenants/${A}`;
  const cat=await client.request(base+'/categories','POST',{name:'原生逻辑HTTP分类'},'native-http-category');
  const product=await client.request(base+'/products','POST',{name:'原生逻辑HTTP商品',unit:'斤',spec:'合成规格',category_id:cat.id,status:'PUBLISHED',reference_price:'9.80'},'native-http-product');
  await client.login('customer-a');
  const shop=page('store');shop.onLoad({store_id:A});await idle(shop);assert.equal(shop.data.store.tenant_id,A);assert.ok(shop.data.products.some(x=>x.id===product.id));
  const item=page('product');item.onLoad({store_id:A,product_id:product.id});await idle(item);assert.equal(item.data.product.name,product.name);item.quantity(input('0.5'));item.add();assert.match(item.data.notice,/尚未提交/);
  const compose=page('compose');compose.onLoad({store_id:A,kind:'reservation'});await idle(compose);assert.equal(compose.data.draft.items.length,1);
  compose.input(input('原生页逻辑真实HTTP合成需求','raw_text'));compose.consent({detail:{value:['accepted']}});await compose.upload();assert.equal(compose.data.draft.media_ids.length,1);await compose.submit();assert.equal(compose.data.done,true,compose.data.error);
  const url=new URL('https://synthetic.invalid'+state.navigation.at(-1));const recordId=url.searchParams.get('record_id');assert.ok(recordId);
  const detail=page('detail');detail.onLoad({store_id:A,record_id:recordId});await idle(detail);assert.equal(detail.data.row.items[0].quantity,'0.5');assert.ok(detail.data.images[0].path);assert.ok(fs.existsSync(detail.data.images[0].path));
  detail.reason(input('合成取消意向'));await detail.cancel();assert.equal(detail.data.row.status,'PENDING_CONFIRMATION');assert.equal(detail.data.row.cancellation_requests[0].status,'REQUESTED');
  const requested=detail.data.row;detail.onHide();assert.equal(detail.data.row,null);
  await client.login('customer-b');await assert.rejects(client.request(`/api/v1/me/records/reservation/${recordId}`),{status:404});
  await client.login('merchant-b');await assert.rejects(client.request(base+`/reservations/${recordId}`),{status:404});
  await client.login('merchant-a');await client.request(base+`/reservations/${recordId}/cancellation-requests/${requested.cancellation_requests[0].id}/decision`,'POST',{
    expected_version:requested.version,decision:'ACCEPTED',response_note:'合成商家同意取消'},'native-http-cancel-decision');
  await client.login('customer-a');detail.onShow();await idle(detail);assert.equal(detail.data.row.status,'CANCELLED');
  const history=page('records');history.onLoad({store_id:A});await idle(history);assert.ok(history.data.items.some(x=>x.id===recordId));
  const inquiry=page('compose');inquiry.onLoad({store_id:A,kind:'inquiry',product_id:product.id});await idle(inquiry);inquiry.input(input('合成商品是否有货？','raw_text'));inquiry.consent({detail:{value:['accepted']}});await inquiry.submit();assert.equal(inquiry.data.done,true,inquiry.data.error);
  const inquiryId=new URL('https://synthetic.invalid'+state.navigation.at(-1)).searchParams.get('record_id');
  const inquiryDetail=page('detail');inquiryDetail.onLoad({store_id:A,record_id:inquiryId,kind:'inquiry'});await idle(inquiryDetail);assert.equal(inquiryDetail.data.row.product_snapshot.id,product.id);
  console.log('PASS compiled native customer logic + REAL HTTP/PG: store/product/decimal draft/private image/submit/history/cancel/tenant isolation/inquiry');
  console.log('SIMULATED wx transport, picker/compression and page lifecycle; NOT WeChat runtime, WXML, sharing or real identity validation.');
})().catch(error=>{console.error(error.code||error.message||'Native HTTP scenario failed');process.exitCode=1;});
