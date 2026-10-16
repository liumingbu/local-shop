import {afterEach,expect,it,vi} from 'vitest';
import {mount,flushPromises,type VueWrapper} from '@vue/test-utils';
import Updates from '../../apps/admin/src/UpdatesPanel.vue';
import Workbench from '../../apps/admin/src/WorkbenchPanel.vue';
const base=process.env.LOCAL_SHOP_TEST_API||'';if(!/^http:\/\/127\.0\.0\.1:\d+$/.test(base))throw Error('Requires isolated loopback API');
const original=globalThis.fetch,tenant='10000000-0000-4000-8000-000000000001';let wrappers:VueWrapper[]=[];
async function call(path:string,token='',method='GET',body?:unknown){const r=await original(base+path,{method,headers:{'Content-Type':'application/json',...(token?{Authorization:'Bearer '+token}:{}),'Idempotency-Key':crypto.randomUUID()},...(body?{body:JSON.stringify(body)}:{})});const data=await r.json();if(!r.ok)throw Error(JSON.stringify(data));return data;}
async function settle(fn:()=>boolean){for(let i=0;i<350;i++){await flushPromises();if(fn())return;await new Promise(r=>setTimeout(r,20));}throw Error('DOM did not settle');}
function button(w:VueWrapper,label:string){const b=w.findAll('button').find(x=>x.text()===label);if(!b)throw Error('missing '+label);return b;}
afterEach(()=>{for(const w of wrappers)w.unmount();wrappers=[];vi.unstubAllGlobals();vi.restoreAllMocks();document.body.innerHTML='';localStorage.clear();});
it('real Vue + HTTP/PG: explicit unread marker, contact result, reviewed copy without automatic contact',async()=>{
 const token=(await call('/api/v1/dev/session','','POST',{identity:'merchant-a'})).access_token;
 const customer=(await call('/api/v1/dev/session','','POST',{identity:'customer-a'})).access_token;
 const root=`/api/v1/merchant/tenants/${tenant}`,store=await call(root+'/store',token);
 await call(root+'/store',token,'PUT',{name:store.name,expected_version:store.version,published:true,allow_pickup:true});
 const row=await call(`/api/v1/stores/${tenant}/reservations`,customer,'POST',{customer_label:'G合成客户',raw_text:'G联系场景',privacy_accepted:true});
 vi.stubGlobal('fetch',(path:string,options?:RequestInit)=>original(base+path,options));
 const feed=mount(Updates,{props:{token,tenantId:tenant},attachTo:document.body});wrappers.push(feed);await settle(()=>feed.attributes('aria-busy')==='false'&&feed.findAll('article').length>0);
 await button(feed,'仅将当前页未读标为已读').trigger('click');await settle(()=>feed.attributes('aria-busy')==='false');expect(feed.text()).toContain('本站内未读 0');
 const unchanged=await call(root+`/reservations/${row.id}`,token);expect(unchanged.status).toBe('PENDING_CONFIRMATION');
 await call(root+`/reservations/${row.id}/transitions`,token,'POST',{target_status:'CONFIRMED',expected_version:row.version});
 const user=(await call('/api/v1/dev/me',token)).user_id;
 const w=mount(Workbench,{props:{token,userId:user,tenantId:tenant,role:'OWNER'},attachTo:document.body});wrappers.push(w);await settle(()=>w.attributes('aria-busy')==='false'&&w.text().includes('G联系场景'));
 const article=w.findAll('article').find(x=>x.text().includes('G联系场景'))!;await article.findAll('button').find(x=>x.text()==='查看详情与历史')!.trigger('click');await settle(()=>w.attributes('aria-busy')==='false'&&w.find('[aria-label="人工联系记录"]').exists());
 const panel=w.find('[aria-label="人工联系记录"]');expect(panel.find('form button').attributes('disabled')).toBeDefined();
 await button(w,'生成已确认需求联系摘要').trigger('click');await settle(()=>w.attributes('aria-busy')==='false'&&button(w,'仅复制摘要').exists());
 expect((await call(root+`/reservations/${row.id}/contacts`,token)).items).toHaveLength(0);
 const copy=vi.fn(async()=>{});Object.defineProperty(navigator,'clipboard',{value:{writeText:copy},configurable:true});
 await panel.findAll('label').find(x=>x.text().includes('已核对摘要'))!.find('input').setValue(true);await button(w,'仅复制摘要').trigger('click');await settle(()=>w.attributes('aria-busy')==='false');expect(copy).toHaveBeenCalledOnce();
 expect((await call(root+`/reservations/${row.id}/contacts`,token)).items).toHaveLength(0);
 await panel.find('textarea[maxlength="500"]').setValue('仅内部合成联系备注');await panel.findAll('label').find(x=>x.text().includes('确认这是实际联系'))!.find('input').setValue(true);await panel.find('form').trigger('submit');await settle(()=>w.attributes('aria-busy')==='false'&&!w.find('[aria-label="处理详情"]').exists());
 const contacts=await call(root+`/reservations/${row.id}/contacts`,token);expect(contacts.items).toHaveLength(1);expect(contacts.items[0].method).toBe('PHONE');expect((await call(root+`/reservations/${row.id}`,token)).status).toBe('CONFIRMED');
 const customerFeed=await call(`/api/v1/me/stores/${tenant}/updates`,customer);expect(JSON.stringify(customerFeed)).not.toContain('仅内部合成联系备注');
});
