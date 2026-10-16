import {afterEach,expect,it,vi} from 'vitest';
import {mount,flushPromises,type VueWrapper} from '@vue/test-utils';
import FulfillmentPanel from '../../apps/admin/src/FulfillmentPanel.vue';
const base=process.env.LOCAL_SHOP_TEST_API||'';if(!/^http:\/\/127\.0\.0\.1:\d+$/.test(base))throw Error('Requires isolated loopback API');
const original=globalThis.fetch,tenant='10000000-0000-4000-8000-000000000001';let w:VueWrapper|undefined;
async function call(path:string,token='',method='GET',body?:unknown){const r=await original(base+path,{method,headers:{'Content-Type':'application/json',...(token?{Authorization:'Bearer '+token}:{}),'Idempotency-Key':crypto.randomUUID()},...(body?{body:JSON.stringify(body)}:{})});const data=await r.json();if(!r.ok)throw Error(JSON.stringify(data));return data;}
async function settle(fn:()=>boolean){for(let i=0;i<300;i++){await flushPromises();if(fn())return;await new Promise(r=>setTimeout(r,20));}throw Error('DOM did not settle');}
function button(label:string){const b=w!.findAll('button').find(x=>x.text()===label);if(!b)throw Error('missing '+label);return b;}
afterEach(()=>{w?.unmount();vi.unstubAllGlobals();vi.restoreAllMocks();document.body.innerHTML='';});
it('real Vue + HTTP/PG: trace confirmed list, generate escaped print document, reject stale export after cancel',async()=>{
 const token=(await call('/api/v1/dev/session','','POST',{identity:'merchant-a'})).access_token;
 const root=`/api/v1/merchant/tenants/${tenant}`;
 const cat=await call(root+'/categories',token,'POST',{name:'DOM备货分类'});
 const product=await call(root+'/products',token,'POST',{category_id:cat.id,name:'<img src=x onerror=alert(1)>',spec:'合成',unit:'盒',status:'PUBLISHED',supply_status:'REGULAR'});
 const row=await call(root+'/reservations',token,'POST',{customer_label:'DOM备货',raw_text:'DOM备货范围',mark_confirmed:true,contact_phone:'PRIVATE_PHONE',internal_note:'PRIVATE_NOTE',items:[{product_id:product.id,name:product.name,spec:'合成',unit:'盒',quantity:'2'}]});
 vi.stubGlobal('fetch',(path:string,options?:RequestInit)=>original(base+path,options));
 w=mount(FulfillmentPanel,{props:{token,tenantId:tenant},attachTo:document.body});await settle(()=>w!.attributes('aria-busy')==='false');
 await w.find('input[maxlength="200"]').setValue('DOM备货范围');await button('重新读取清单').trigger('click');await settle(()=>w!.attributes('aria-busy')==='false');
 expect(w.text()).toContain(row.business_number);expect(w.find('img').exists()).toBe(false);
 await button('按商品汇总').trigger('click');expect(w.text()).toContain('2 盒');
 await button('生成打印清单').trigger('click');await settle(()=>w!.find('[aria-label="生成的清单"]').exists()&&w!.attributes('aria-busy')==='false');
 const print=w.find('[aria-label="生成的清单"]');expect(print.text()).toContain('<img src=x onerror=alert(1)>');expect(print.find('img').exists()).toBe(false);expect(print.text()).not.toContain('PRIVATE_PHONE');expect(print.text()).not.toContain('PRIVATE_NOTE');
 const spy=vi.spyOn(window,'print').mockImplementation(()=>{});await button('打印此清单').trigger('click');await settle(()=>spy.mock.calls.length===1&&w!.attributes('aria-busy')==='false');expect(spy).toHaveBeenCalledOnce();
 await call(root+`/reservations/${row.id}/transitions`,token,'POST',{target_status:'CANCELLED',expected_version:row.version});
 await button('生成打印清单').trigger('click');await settle(()=>w!.find('[role="alert"]').exists()&&w!.attributes('aria-busy')==='false');expect(w.text()).toContain('清单中的记录已更新');expect(w.find('[aria-label="生成的清单"]').exists()).toBe(false);
 await button('重新读取清单').trigger('click');await settle(()=>w!.attributes('aria-busy')==='false');expect(w.text()).toContain('本店 0 单');
});
