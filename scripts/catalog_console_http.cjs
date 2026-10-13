/** Compiled Web controller against real HTTP and PostgreSQL; not a DOM/browser test. */
const assert=require('node:assert/strict');
const {CatalogConsole,catalogState}=require('../tests/admin/.compiled/catalog.js');
const {request}=require('../tests/admin/.compiled/api.js');
const origin=process.argv[2],networkFetch=global.fetch;
if(origin!=='http://127.0.0.1:8000')throw Error('Isolated runner origin required');
global.fetch=(url,options)=>networkFetch(typeof url==='string'&&url.startsWith('/')?origin+url:url,options);
(async()=>{
 const token=(await request('/api/v1/dev/session','','POST',{identity:'merchant-a'})).access_token;
 const uid=(await request('/api/v1/dev/me',token)).user_id;
 const tid='10000000-0000-4000-8000-000000000001',root=`/api/v1/merchant/tenants/${tid}`;
 const category=await request(root+'/categories',token,'POST',{name:'合成批量维护分类',sort_order:0,status:'ACTIVE'},crypto.randomUUID());
 const saved=new Map(),storage={getItem:k=>saved.get(k)||null,setItem:(k,v)=>saved.set(k,v)};
 let lose=false;const writes=[];const transport=async(p,m,b,k)=>{if(m)writes.push({p,m,b,k});const result=await request(p,token,m,b,k);if(m&&lose){lose=false;throw Error('Synthetic response loss after actual server commit');}return result;};
 let state=catalogState(),controller=new CatalogConsole(state,transport,storage,uid,tid);await controller.load();assert.equal(state.ready,true,state.error);
 const make=(name)=>({id:'',version:0,category_id:category.id,name,description:'合成数据',unit:'斤',spec:'分小袋',reference_price:'',status:'DRAFT',supply_status:'CONFIRM',sort_order:'0',selected:true,rowKey:name});
 state.rows=[make('合成批量商品一'),{...make('合成批量商品二'),reference_price:'0.50'}];lose=true;await controller.submit();assert.equal(state.uncertain,true,state.error);assert.equal(state.done,0);controller.dispose();
 state=catalogState();controller=new CatalogConsole(state,transport,storage,uid,tid);await controller.load();assert.equal(state.locked,true);await controller.resume();assert.equal(state.locked,false,state.error);assert.equal(state.results.length,2);assert.deepEqual(writes[0],writes[1]);
 const [first,second]=state.results;let p1=await request(root+'/products/'+first.id,token),p2=await request(root+'/products/'+second.id,token);assert.equal(p1.version,1);assert.equal(p1.reference_price,null);assert.equal(p2.reference_price,'0.50');assert.equal(p1.status,'DRAFT');
 // Lost PUT acknowledgement must replay snapshot, not increment twice.
 state.rows=[{...make('合成批量改名'),id:p1.id,version:p1.version}];lose=true;await controller.submit();assert.equal(state.uncertain,true);await controller.resume();assert.equal(state.locked,false,state.error);p1=await request(root+'/products/'+p1.id,token);assert.equal(p1.version,2);assert.deepEqual(writes.at(-1),writes.at(-2));
 // Another editor wins. Batch preserves successful prefix and stops at stale row.
 await request(root+'/products/'+p2.id,token,'PUT',{category_id:category.id,name:'合成其他编辑者',unit:'盒',expected_version:p2.version,status:'DRAFT'});
 state.rows=[{...make('合成第一项保存'),id:p1.id,version:p1.version},{...make('不应覆盖他人'),id:p2.id,version:p2.version},make('不应发送第三项')];const before=writes.length;
 await controller.submit();assert.equal(state.done,1);assert.equal(state.blocked,'VERSION_CONFLICT');assert.equal(state.uncertain,false);assert.equal(writes.length-before,2);await controller.discardKnownFailure(true);assert.equal(state.locked,false);
 p2=await request(root+'/products/'+p2.id,token);assert.equal(p2.name,'合成其他编辑者');assert.equal(p2.unit,'盒');
 const other=(await request('/api/v1/dev/session','','POST',{identity:'merchant-b'})).access_token;
 await assert.rejects(request(root+'/products/'+p1.id,other),{status:404});
 await assert.rejects(request(root+'/products/'+p1.id,other,'PUT',{category_id:category.id,name:'不能修改A',unit:'盒',expected_version:3},crypto.randomUUID()),{status:404});
 console.log('PASS compiled Web catalog controller + REAL HTTP/PG: sequential create/update, lost POST/PUT acknowledgement replay, nullable/decimal reference price, version conflict stops remaining rows, partial results, tenant read/write isolation.');
 console.log('Browser DOM rendering NOT_RUN; synthetic response loss injected only after real HTTP response.');
})().catch(e=>{console.error(e.code==='ERR_ASSERTION'?e.stack:(e.code||e.message));process.exitCode=1;});
