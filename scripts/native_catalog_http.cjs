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
    state.lastImageStatus=response.status;assert.equal(response.status,200);assert.equal(bytes[0],255);assert.equal(bytes[1],216);
    const file=path.join(downloadDir,`native-private-${++downloadCount}.jpg`);fs.writeFileSync(file,bytes);
    options.success({statusCode:200,tempFilePath:file});}catch{options.fail({errMsg:'Private image unavailable'});}})();return{abort(){}};
};
wx.chooseMedia=options=>options.success({tempFiles:[{tempFilePath:fixture,size:fs.statSync(fixture).size}]});
wx.compressImage=options=>options.success({tempFilePath:options.src}); // Fixture, not actual WeChat compression.
wx.getFileSystemManager=()=>({readFile(options){const bytes=fs.readFileSync(options.filePath);options.success({data:bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength)});}});
(async()=>{
  await client.login('merchant-a');const tenants=await client.request('/api/v1/merchant/tenants'),A=tenants.items[0].id,base=`/api/v1/merchant/tenants/${A}`;
  const catalog=page('catalog');catalog.onLoad({store_id:A});await idle(catalog);assert.equal(catalog.data.authorized,true,catalog.data.error);catalog.input(input('原生目录合成分类','name'));await catalog.save();assert.ok(catalog.data.lastCategory,catalog.data.error);const categoryId=catalog.data.lastCategory;
  const edit=page('productedit');edit.onLoad({store_id:A,category_id:categoryId});await idle(edit);assert.equal(edit.data.form.status,'DRAFT');edit.input(input('原生维护合成商品','name'));edit.input(input('斤','unit'));edit.input(input('0.5斤袋装','spec'));await edit.save();assert.ok(edit.data.productId,edit.data.error);const id=edit.data.productId;
  assert.equal((await fetch(config.apiOrigin+`/api/v1/stores/${A}/products/${id}`)).status,404);
  await edit.upload();await edit.upload();assert.equal(edit.data.images.length,2,edit.data.error);const [first,second]=edit.data.images.map(x=>x.id);assert.notEqual(first,second);
  await edit.saveImages();assert.equal(edit.data.imagesDirty,false,edit.data.error);edit.status({detail:{value:'1'}});await edit.save();assert.equal(edit.data.form.status,'PUBLISHED',edit.data.error);
  let publicProduct=await (await fetch(config.apiOrigin+`/api/v1/stores/${A}/products/${id}`)).json();assert.equal(publicProduct.reference_price,null);assert.deepEqual(publicProduct.images.map(x=>x.id),[first,second]);
  assert.equal((await fetch(config.apiOrigin+publicProduct.images[0].url)).status,200);
  edit.move({currentTarget:{dataset:{index:1,delta:-1}}});await edit.saveImages();publicProduct=await client.request(`/api/v1/stores/${A}/products/${id}`);assert.deepEqual(publicProduct.images.map(x=>x.id),[second,first]);
  edit.remove({currentTarget:{dataset:{index:1}}});await edit.saveImages();assert.equal((await fetch(config.apiOrigin+`/api/v1/stores/${A}/products/${id}/images/${first}`)).status,404);
  catalog.archived({detail:{value:['archived']}});await catalog.save();assert.equal(catalog.data.form.status,'ARCHIVED',catalog.data.error);assert.equal((await fetch(config.apiOrigin+`/api/v1/stores/${A}/products/${id}`)).status,404);
  catalog.archived({detail:{value:[]}});await catalog.save();assert.equal((await fetch(config.apiOrigin+`/api/v1/stores/${A}/products/${id}`)).status,200);
  edit.status({detail:{value:'2'}});await edit.save();assert.equal((await fetch(config.apiOrigin+`/api/v1/stores/${A}/products/${id}`)).status,404);edit.status({detail:{value:'1'}});await edit.save();
  // Concurrent update must not overwrite another save. Refresh explicitly reconciles it.
  const fresh=await client.request(base+`/products/${id}`);await client.request(base+`/products/${id}`,'PUT',{category_id:fresh.category_id,name:fresh.name,unit:fresh.unit,spec:fresh.spec,status:fresh.status,expected_version:fresh.version});
  edit.input(input('不应覆盖的陈旧编辑','name'));await edit.save();assert.equal(edit.data.locked,true);await edit.load();assert.equal(edit.data.locked,false);assert.equal(edit.data.form.name,'原生维护合成商品');
  const settings=page('shopsettings');settings.onLoad({store_id:A});await idle(settings);const originalLogo=settings.data.form.logo_media_id;await settings.uploadLogo();const logo=settings.data.form.logo_media_id;assert.ok(logo);await settings.save();assert.equal((await fetch(config.apiOrigin+`/api/v1/stores/${A}/logo`)).status,200);
  settings.removeLogo();await settings.save();assert.equal((await fetch(config.apiOrigin+`/api/v1/stores/${A}/logo`)).status,404);settings.setData({form:{...settings.data.form,logo_media_id:originalLogo}});await settings.save();
  await client.login('merchant-b');await assert.rejects(client.request(base+`/products/${id}`),{status:404});await assert.rejects(client.privateImage(base+`/media/${second}/content`),{code:'IMAGE_UNAVAILABLE'});assert.equal(state.lastImageStatus,404);
  console.log('PASS native catalog logic + REAL HTTP/PG: category create/archive/restore, product draft/publish/archive, null reference price, two images/order/unlink/public access, stale version rejection, Logo upload/remove, cross-tenant product/media denial');
  console.log('SIMULATED wx media picker/compression and page lifecycle; WXML and real WeChat device remain NOT_RUN.');
})().catch(error=>{console.error(error.code==='ERR_ASSERTION'?error.stack:(error.code||'Native catalog HTTP scenario failed'));process.exitCode=1;});
