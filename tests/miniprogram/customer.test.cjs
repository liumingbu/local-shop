const test=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const path=require('node:path');
const {setup,page,idle,input,root}=require('./harness.cjs');
const A='10000000-0000-4000-8000-000000000001', B='10000000-0000-4000-8000-000000000002';
const R='20000000-0000-4000-8000-000000000001';
const record=()=>({id:R,tenant_id:A,raw_text:'合成需求',status:'PENDING_CONFIRMATION',version:1,created_at:'2026-10-13T00:00:00Z',items:[],attachments:[],events:[],cancellation_requests:[],confirmation_revisions:[]});
const event=id=>({currentTarget:{dataset:{id}}});

test('development login is disabled by configuration and always refused for trial/release',async()=>{
  const {client,config,state}=setup();config.enableDevelopmentLogin=false;
  await assert.rejects(client.login('customer-a'),{code:'WECHAT_LOGIN_NOT_CONFIGURED'});
  config.enableDevelopmentLogin=true;for(const env of ['trial','release']){state.env=env;await assert.rejects(client.login('customer-a'),{code:'WECHAT_LOGIN_NOT_CONFIGURED'});}
  assert.equal(state.calls.length,0);
});
test('origin and path are fail-closed; remote plaintext, userinfo and arbitrary URLs refused',()=>{
  const {client,config,state}=setup();for(const value of ['','http://remote.example','https://user:pass@example.com','https://example.com/x','javascript:x']){config.apiOrigin=value;assert.throws(()=>client.origin());}
  config.apiOrigin='https://api.example.com';assert.equal(client.absolute('/api/v1/stores/'+A),'https://api.example.com/api/v1/stores/'+A);
  for(const value of ['https://evil.example','//evil.example','/api/v1/../secret'])assert.throws(()=>client.absolute(value));
  state.env='release';config.apiOrigin='http://127.0.0.1:8000';assert.throws(()=>client.origin());
});
test('invalid share entry does not fall back to a recent store',()=>{
  const {state}=setup();state.storage.set('local-shop.recent',[{id:A,name:'A'}]);const p=page('index');p.onLoad({store_id:'broken'});p.onShow();
  assert.equal(state.navigation.length,0);assert.match(p.data.error,/参数无效/);assert.equal(p.data.recent.length,1);
});
test('login keeps credentials in memory; authenticated identity comes from server me response',async()=>{
  const {client,state}=setup();await client.login('customer-a');assert.equal(client.auth().userId,'00000000-0000-4000-8000-000000000003');
  assert.equal(state.storage.size,0);client.logout();assert.equal(client.auth().authenticated,false);
});
test('late private response after account switch is discarded',async()=>{
  const {client,state}=setup();await client.login('customer-a');let release;state.handler=()=>new Promise(resolve=>{release=resolve;});
  const pending=client.request('/api/v1/me/records');await new Promise(resolve=>setImmediate(resolve));client.logout();release({status:200,data:{secret:'synthetic'}});
  await assert.rejects(pending,{code:'SESSION_CHANGED'});
});
test('drafts are isolated by user and store, and units/specifications never merge',async()=>{
  const {client,drafts}=setup();await client.login('customer-a');drafts.addItem(A,{name:'x',quantity:'0.5',unit:'斤',spec:'袋'});drafts.addItem(A,{name:'x',quantity:'1',unit:'盒',spec:'大盒'});
  assert.equal(drafts.readDraft(A).items.length,2);assert.equal(drafts.readDraft(B).items.length,0);
  await client.login('customer-b');assert.equal(drafts.readDraft(A).items.length,0);
  await client.login('customer-a');assert.equal(drafts.readDraft(A).items[0].quantity,'0.5');
});
test('storage failure prevents sending an unrepeatable business request',async()=>{
  const {client,drafts,state}=setup();await client.login('customer-a');state.calls=[];state.storageFails=true;
  await assert.rejects(drafts.mutate(A,'reservation',`/api/v1/stores/${A}/reservations`,'POST',{raw_text:'x'}),{code:'STORAGE_UNAVAILABLE'});
  assert.equal(state.calls.length,0);
});
test('uncertain retry uses immutable original payload/key and survives success before draft acknowledgement',async()=>{
  const {client,drafts,state}=setup();await client.login('customer-a');state.calls=[];let fail=true;state.handler=()=>{if(fail)throw new Error('offline');return{status:201,data:{id:R}};};
  const url=`/api/v1/stores/${A}/reservations`;await assert.rejects(drafts.mutate(A,'reservation',url,'POST',{raw_text:'original'}));
  const key=drafts.pending(A,'reservation').key;fail=false;
  await drafts.mutate(A,'reservation',url,'POST',{raw_text:'changed'});
  assert.equal(state.calls[1].header['Idempotency-Key'],key);assert.deepEqual(state.calls[1].data,{raw_text:'original'});
  assert.ok(drafts.pending(A,'reservation'));drafts.clearDraft(A);drafts.finishMutation(A,'reservation');assert.equal(drafts.pending(A,'reservation'),undefined);
});
test('validation rejection releases draft, but expired login preserves pending operation',async()=>{
  const {client,drafts,state}=setup();await client.login('customer-a');state.handler=()=>({status:422,data:{code:'INVALID_INPUT'}});
  await assert.rejects(drafts.mutate(A,'reservation',`/api/v1/stores/${A}/reservations`,'POST',{}));assert.equal(drafts.pending(A,'reservation'),undefined);
  state.handler=()=>({status:401,data:{code:'INVALID_TOKEN'}});await assert.rejects(drafts.mutate(A,'reservation',`/api/v1/stores/${A}/reservations`,'POST',{}));assert.ok(drafts.pending(A,'reservation'));
});
test('busy and view generation protect double clicks and late results after hide/show',async()=>{
  const {ui}=setup();let release;const p={alive:true,view:0,data:{busy:false},setData(v){Object.assign(this.data,v);}};let calls=0;
  const first=ui.run(p,async commit=>{calls++;await new Promise(resolve=>release=resolve);commit({private:'old'});});
  await ui.run(p,async()=>calls++);assert.equal(calls,1);p.view++;p.alive=false;p.data.busy=false;p.alive=true;release();await first;assert.equal(p.data.private,undefined);
});
test('decimal validation and explicit UTC+08 display do not invent quantities or dates',()=>{
  const {ui}=setup();for(const v of ['0','-1','1e3','1.0001','NaN',''])assert.equal(ui.quantityValid(v),false);
  for(const v of ['0.5','1.250','999999999.999'])assert.equal(ui.quantityValid(v),true);
  assert.equal(ui.timeText(null),'未确定');assert.equal(ui.timeText('2026-10-13T00:00:00Z'),'2026-10-13 08:00（北京时间）');
});
test('native page registrations, assets and event handlers exist (static, not WXML rendering)',()=>{
  setup();const app=JSON.parse(fs.readFileSync(path.join(root,'app.json')));assert.equal(app.pages.length,15);
  for(const route of app.pages){for(const ext of ['js','json','wxml','wxss'])assert.ok(fs.existsSync(path.join(root,`${route}.${ext}`)));const p=page(route.split('/')[1]);
    const markup=fs.readFileSync(path.join(root,route+'.wxml'),'utf8');for(const match of markup.matchAll(/(?:bind|catch)[a-z]+="([A-Za-z]\w*)"/g))assert.equal(typeof p[match[1]],'function',`${route}:${match[1]}`);
  }
});
test('compose sends only this store draft and clears it only after confirmed success',async()=>{
  const {client,drafts,state}=setup();await client.login('customer-a');state.handler=options=>options.method==='POST'?{status:201,data:record()}:{status:200,data:{name:'A',allow_pickup:true}};
  const p=page('compose');p.onLoad({store_id:A,kind:'reservation'});await idle(p);p.input(input('合成文字','raw_text'));p.consent({detail:{value:['accepted']}});await p.submit();
  assert.equal(p.data.done,true);assert.equal(drafts.readDraft(A).raw_text,'');assert.equal(drafts.pending(A,'reservation'),undefined);
  assert.match(state.navigation.at(-1),/record_id=20000000/);
});
test('compose double-click plus network retry does not replace the original payload',async()=>{
  const {client,state}=setup();await client.login('customer-a');let offline=true;
  state.handler=options=>{if(options.method==='POST'){if(offline)throw new Error('offline');return{status:201,data:record()};}return{status:200,data:{name:'A'}};};
  const p=page('compose');p.onLoad({store_id:A,kind:'reservation'});await idle(p);p.input(input('first','raw_text'));p.consent({detail:{value:['accepted']}});
  await Promise.all([p.submit(),p.submit()]);assert.equal(p.data.locked,true);p.input(input('replacement','raw_text'));assert.equal(p.data.draft.raw_text,'first');
  offline=false;await p.submit();const calls=state.calls.filter(x=>new URL(x.url).pathname.endsWith('/reservations'));assert.equal(calls.length,2);assert.equal(calls[0].header['Idempotency-Key'],calls[1].header['Idempotency-Key']);assert.deepEqual(calls[0].data,calls[1].data);
});
test('leaving compose before response keeps the original pending request and does not navigate later',async()=>{
  const {client,drafts,state}=setup();await client.login('customer-a');let release;state.handler=options=>options.method==='POST'?new Promise(resolve=>release=resolve):{status:200,data:{name:'A'}};
  const p=page('compose');p.onLoad({store_id:A});await idle(p);p.input(input('first','raw_text'));p.consent({detail:{value:['accepted']}});const running=p.submit();await new Promise(resolve=>setImmediate(resolve));
  p.onHide();release({status:201,data:record()});await running;assert.ok(drafts.pending(A,'reservation'));assert.equal(state.navigation.length,0);
});
test('explicit date+time becomes a timezone-aware value; date-only stays a note',async()=>{
  const {client,state}=setup();await client.login('customer-a');state.handler=o=>({status:o.method==='POST'?201:200,data:o.method==='POST'?record():{name:'A'}});
  const p=page('compose');p.onLoad({store_id:A});await idle(p);p.input(input('x','raw_text'));p.consent({detail:{value:['accepted']}});p.date({detail:{value:'2026-10-15'}});p.clock({detail:{value:'17:30'}});await p.submit();
  const body=state.calls.filter(x=>x.method==='POST'&&new URL(x.url).pathname.endsWith('/reservations')).at(-1).data;assert.equal(body.expected_at,'2026-10-15T09:30:00.000Z');
});
test('private detail rejects store mismatch and clears private content on hide',async()=>{
  const {client,state}=setup();await client.login('customer-a');state.handler=()=>({status:200,data:{...record(),tenant_id:B}});
  const p=page('detail');p.onLoad({store_id:A,record_id:R});await idle(p);assert.equal(p.data.row,null);assert.match(p.data.error,/参数无效/);
  state.handler=()=>({status:200,data:record()});await p.load();assert.equal(p.data.row.id,R);p.onHide();assert.equal(p.data.row,null);assert.equal(p.data.images.length,0);
});
test('private images send authentication as a header, never a query token',async()=>{
  const {client,state}=setup();await client.login('customer-a');await client.privateImage(`/api/v1/me/media/${R}/content?store_id=${A}`);
  assert.ok(state.downloads[0].header.Authorization);assert.equal(new URL(state.downloads[0].url).searchParams.has('token'),false);
});
test('image picker cancellation sends no upload and preserves draft',async()=>{
  const {client,state}=setup();await client.login('customer-a');state.chooseCancel=true;state.calls=[];
  const media=require(path.join(root,'lib/media.js'));await assert.rejects(media.chooseAndUpload(`/api/v1/stores/${A}/private-media?privacy_accepted=true`),{code:'IMAGE_SELECTION_CANCELLED'});assert.equal(state.calls.length,0);
});
test('a different product entry does not silently mix an existing inquiry draft',async()=>{
  const {client,drafts,state}=setup();await client.login('customer-a');const d=drafts.readDraft(A,'inquiry');d.raw_text='old';d.product_id=R;drafts.saveDraft(A,d,'inquiry');state.handler=()=>({status:200,data:{name:'A'}});
  const p=page('compose');p.onLoad({store_id:A,kind:'inquiry',product_id:B});await idle(p);p.onShow();assert.equal(p.data.draft,null);assert.equal(drafts.readDraft(A,'inquiry').product_id,R);assert.match(p.data.error,/另一商品/);
});

test('leaving the login page interrupts the pending identity switch',async()=>{
  const {client,state}=setup();const p=page('index');let release;
  wx.request=options=>{state.calls.push(options);release=()=>options.success({statusCode:200,data:{access_token:'synthetic:customer-a'}});return{abort(){}};};
  const running=p.signIn();p.onHide();release();await running;assert.equal(client.auth().authenticated,false);assert.equal(state.calls.length,1);
});
test('date-only input remains a note and is not silently assigned midnight',async()=>{
  const {client,state}=setup();await client.login('customer-a');state.handler=o=>({status:o.method==='POST'?201:200,data:o.method==='POST'?record():{name:'A'}});
  const p=page('compose');p.onLoad({store_id:A});await idle(p);p.input(input('x','raw_text'));p.consent({detail:{value:['accepted']}});p.date({detail:{value:'2026-10-15'}});await p.submit();
  const body=state.calls.filter(x=>x.method==='POST'&&new URL(x.url).pathname.endsWith('/reservations')).at(-1).data;assert.equal(body.expected_at,undefined);assert.equal(body.expected_time_note,'2026-10-15');
});
test('source default has no API origin or enabled fake login',()=>{
  const text=fs.readFileSync(path.resolve(root,'../config.ts'),'utf8');assert.match(text,/apiOrigin:\s*''/);assert.match(text,/enableDevelopmentLogin:\s*false/);
});

test('manual UUID entry is development-only; valid recent/shared route is retained',()=>{
 const {state,config}=setup();const p=page('index');config.enableDevelopmentLogin=false;
 p.data.storeInput='10000000-0000-4000-8000-000000000001';p.enter();assert.equal(state.navigation.length,0);
 p.enter({currentTarget:{dataset:{id:p.data.storeInput}}});assert.equal(state.navigation.length,1);
});
