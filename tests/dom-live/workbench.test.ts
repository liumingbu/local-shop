import {afterEach,expect,it,vi} from 'vitest';
import {mount,flushPromises,type VueWrapper} from '@vue/test-utils';
import App from '../../apps/admin/src/App.vue';
const base=process.env.LOCAL_SHOP_TEST_API||'';
if(!/^http:\/\/127\.0\.0\.1:\d+$/.test(base))throw Error('Requires explicit isolated loopback API');
const nativeFetch=globalThis.fetch;
let wrappers:VueWrapper[]=[];
function button(w:VueWrapper,text:string){const b=w.findAll('button').find(x=>x.text()===text);if(!b)throw Error('Missing button '+text);return b;}
async function field(w:VueWrapper,label:string,value:string|boolean){const l=w.findAll('label').find(x=>x.text().startsWith(label));if(!l)throw Error('Missing label '+label);await l.find('input,select,textarea').setValue(value);}
async function settle(predicate:()=>boolean){for(let i=0;i<300;i++){await flushPromises();if(predicate())return;await new Promise(r=>setTimeout(r,20));}throw Error('DOM condition timed out');}
async function call(path:string,token='',method='GET',body?:unknown){const r=await nativeFetch(base+path,{method,headers:{'Content-Type':'application/json',...(token?{Authorization:'Bearer '+token}:{}),'Idempotency-Key':crypto.randomUUID()},...(body?{body:JSON.stringify(body)}:{})});const data=await r.json();if(!r.ok)throw Error(JSON.stringify(data));return data;}
async function token(alias:string){return (await call('/api/v1/dev/session','','POST',{identity:alias})).access_token;}
async function start(alias='merchant-a'){vi.stubEnv('VITE_ENABLE_DEVELOPMENT_LOGIN','true');vi.stubGlobal('fetch',(path:string,options?:RequestInit)=>nativeFetch(base+path,options));const w=mount(App,{attachTo:document.body});wrappers.push(w);await field(w,'演示身份',alias);await button(w,'进入工作台').trigger('click');await settle(()=>alias==='platform-admin'?w.text().includes('定向邀请已有账号'):w.find('[aria-label="商户日常工作台"]').exists()&&!w.find('[aria-label="商户日常工作台"]').attributes('aria-busy')?.includes('true'));return w;}
afterEach(()=>{for(const w of wrappers)w.unmount();wrappers=[];vi.unstubAllGlobals();vi.unstubAllEnvs();document.body.innerHTML='';localStorage.clear();});
it('Vue DOM + real HTTP/PG: persisted unknown create, confirmation, delivery history, tenant switch',async()=>{
 let w=await start();await field(w,'顾客称呼','DOM真实链路合成顾客');await field(w,'原始需求','0.5斤合成干贝，分两袋');
 const wire:any[]=[];let lose=true;
 vi.stubGlobal('fetch',async(path:string,options:any)=>{const response=await nativeFetch(base+path,options);if(options?.method==='POST'&&path.endsWith('/reservations')){wire.push({key:options.headers['Idempotency-Key'],body:options.body});if(lose){lose=false;throw Error('synthetic response loss after DB commit');}}return response;});
 await w.find('[aria-label="快速代记"] form').trigger('submit');await settle(()=>w.text().includes('原操作结果待确认'));
 w.unmount();wrappers=[];w=await start();
 // Reinstall the same observation transport after the simulated page reload.
 vi.stubGlobal('fetch',async(path:string,options:any)=>{if(options?.method==='POST'&&path.endsWith('/reservations'))wire.push({key:options.headers['Idempotency-Key'],body:options.body});return nativeFetch(base+path,options);});
 await button(w,'重试原提交').trigger('click');await settle(()=>!w.text().includes('原操作结果待确认')&&w.find('[aria-label="商户日常工作台"]').attributes('aria-busy')==='false');
 expect(wire).toHaveLength(2);expect(wire[1]).toEqual(wire[0]);
 const cards=()=>w.findAll('[aria-label="待办与历史"] article').filter(x=>x.text().includes('DOM真实链路合成顾客'));
 expect(cards()).toHaveLength(1);
 for(const status of ['已确认','备货中','待取/送','已完成']){await settle(()=>w.find('[aria-label="商户日常工作台"]').attributes('aria-busy')==='false');await cards()[0].findAll('button').find(x=>x.text()===status)!.trigger('click');await settle(()=>cards()[0]?.find('.badge').text()===status);}
 await settle(()=>w.find('[aria-label="商户日常工作台"]').attributes('aria-busy')==='false');await cards()[0].findAll('button').find(x=>x.text()==='查看详情与历史')!.trigger('click');await settle(()=>w.find('[aria-label="处理详情"]').exists());expect(w.find('[aria-label="处理详情"] ol').findAll('li')).toHaveLength(5);
 await button(w,'关闭详情').trigger('click');expect(w.find('[aria-label="处理详情"]').exists()).toBe(false);
 await button(w,'退出登录').trigger('click');await field(w,'演示身份','merchant-b');await button(w,'进入工作台').trigger('click');await settle(()=>w.find('[aria-label="商户日常工作台"]').exists()&&!w.find('[aria-label="商户日常工作台"]').attributes('aria-busy')?.includes('true'));expect(w.text()).not.toContain('DOM真实链路合成顾客');
});
it('Vue platform panel + real PG: invite, recipient acceptance, approve, suspend and recover',async()=>{
 const w=await start('platform-admin');await settle(()=>w.text().includes('创建邀请'));
 await field(w,'收件人账号UUID','00000000-0000-4000-8000-000000000004');await field(w,'拟用店名','DOM审核合成店');await field(w,'邀请原因','合成流程验证');
 await w.find('[aria-label="平台管理"] form').trigger('submit');await settle(()=>w.findAll('article').some(x=>x.text().includes('DOM审核合成店')));
 const customer=await token('customer-b');const list=await call('/api/v1/me/shop-invitations',customer);expect(list, 'Invitation response must be a paginated server result').toHaveProperty('items');const invitation=list.items.find((x:any)=>x.proposed_name==='DOM审核合成店');expect(invitation).toBeTruthy();
 await call(`/api/v1/me/shop-invitations/${invitation.id}/response`,customer,'POST',{expected_version:invitation.version,decision:'ACCEPTED'});
 await button(w,'重新读取服务端').trigger('click');await settle(()=>w.findAll('article').some(x=>x.text().includes('DOM审核合成店')&&x.text().includes('已接受，待审核'))&&button(w,'重新读取服务端').attributes('disabled')===undefined);
 await field(w,'本次审核理由','已核对合成邀请');const card=w.findAll('article').find(x=>x.text().includes('DOM审核合成店'))!;await card.findAll('button').find(x=>x.text().includes('明确批准'))!.trigger('click');await settle(()=>w.findAll('article').some(x=>x.text().includes('DOM审核合成店')&&x.text().includes('已批准'))&&button(w,'重新读取服务端').attributes('disabled')===undefined);
 await field(w,'本次启停理由','验证暂停与恢复');const tenantCard=()=>w.findAll('article').find(x=>x.text().includes('DOM审核合成店')&&x.text().includes('明确暂停商户'))!;
 await tenantCard().find('button').trigger('click');await settle(()=>w.findAll('article').some(x=>x.text().includes('DOM审核合成店')&&x.text().includes('恢复启用'))&&button(w,'重新读取服务端').attributes('disabled')===undefined);
 const paused=w.findAll('article').find(x=>x.text().includes('DOM审核合成店')&&x.text().includes('恢复启用'))!;await paused.find('button').trigger('click');await settle(()=>!!tenantCard());
});
it('Vue catalog + real PG: create category, edit one product and verify persisted fields',async()=>{
 const w=await start();await button(w,'商品维护').trigger('click');const panel=w.find('[aria-label="批量商品维护"]');
 await field(w,'新增分类名称','DOM合成分类');await panel.find('form[aria-label="创建商品分类"]').trigger('submit');await settle(()=>panel.find('input[placeholder="例如：干货、日用品"]').exists()&&!panel.find('input[placeholder="例如：干货、日用品"]').element.value);
 await button(w,'加一行新商品草稿').trigger('click');const row=panel.findAll('tbody tr').at(-1)!;await row.find('[aria-label="商品名"]').setValue('DOM合成商品长名称');const cat=row.find('[aria-label="商品分类"]').findAll('option').find(x=>x.text()==='DOM合成分类')!;await row.find('[aria-label="商品分类"]').setValue(cat.attributes('value'));await row.find('[aria-label="单位"]').setValue('斤');await row.find('[aria-label="规格"]').setValue('散装');await row.find('[aria-label="参考价格"]').setValue('12.50');await button(w,'保存所选商品').trigger('click');await settle(()=>panel.text().includes('本批已确认保存的结果'));
 const owner=await token('merchant-a');const result=await call('/api/v1/merchant/tenants/10000000-0000-4000-8000-000000000001/products?limit=100',owner);const product=result.items.find((x:any)=>x.name==='DOM合成商品长名称');expect(product).toMatchObject({unit:'斤',spec:'散装',reference_price:'12.50',status:'DRAFT'});
});
it('Vue daily queue + real PG: contacts, scoped search, explicit deadline and copy creates new request',async()=>{
 const w=await start();await field(w,'顾客称呼','DOM日常合成顾客');await field(w,'原始需求','0.5斤合成日常需求');await field(w,'联系人','合成人');await field(w,'联系电话','SYNTHETIC');await field(w,'交付意向','DELIVERY');await field(w,'配送地址','合成地址');
 await w.find('[aria-label="快速代记"] form').trigger('submit');await settle(()=>w.find('[aria-label="商户日常工作台"]').attributes('aria-busy')==='false');
 await field(w,'本店历史搜索','DOM日常合成顾客');await button(w,'应用筛选').trigger('click');await settle(()=>w.find('[aria-label="商户日常工作台"]').attributes('aria-busy')==='false');
 const cards=()=>w.findAll('[aria-label="待办与历史"] article');expect(cards()).toHaveLength(1);await cards()[0].findAll('button').find(x=>x.text()==='查看详情与历史')!.trigger('click');await settle(()=>w.find('[aria-label="处理详情"]').exists());expect(w.find('[aria-label="处理详情"]').text()).toContain('SYNTHETIC');
 await field(w,'确认内容','明确备货合成内容');await field(w,'变更原因','合成约定');await field(w,'商户承诺交付时间','2026-01-01T12:00');await w.find('[aria-label="处理详情"] form').trigger('submit');await settle(()=>w.find('[aria-label="商户日常工作台"]').attributes('aria-busy')==='false');
 await cards()[0].findAll('button').find(x=>x.text()==='查看详情与历史')!.trigger('click');await settle(()=>w.find('[aria-label="处理详情"]').exists());await field(w,'已与顾客核对',true);await w.find('[aria-label="处理详情"]').findAll('button').find(x=>x.text()==='已确认')!.trigger('click');await settle(()=>w.find('[aria-label="商户日常工作台"]').attributes('aria-busy')==='false');expect(cards()[0].text()).toContain('已逾承诺时间');
 await cards()[0].findAll('button').find(x=>x.text()==='复制为新需求')!.trigger('click');await settle(()=>w.text().includes('这是新需求草稿'));expect(button(w,'保存需求').attributes('disabled')).toBeDefined();await field(w,'已重新核对数量',true);await w.find('[aria-label="快速代记"] form').trigger('submit');await settle(()=>w.find('[aria-label="商户日常工作台"]').attributes('aria-busy')==='false');expect(cards()).toHaveLength(2);
 const owner=await token('merchant-a');const data=await call('/api/v1/merchant/tenants/10000000-0000-4000-8000-000000000001/reservations?q='+encodeURIComponent('DOM日常合成顾客'),owner);expect(new Set(data.items.map((x:any)=>x.business_number)).size).toBe(2);expect(data.items.filter((x:any)=>x.status==='PENDING_CONFIRMATION')).toHaveLength(1);
});
it('Vue cancellation decision + real PG keeps intent separate from cancellation',async()=>{
 const owner=await token('merchant-a'),customer=await token('customer-a');const tid='10000000-0000-4000-8000-000000000001';
 const row=await call(`/api/v1/stores/${tid}/reservations`,customer,'POST',{raw_text:'DOM取消合成需求',customer_label:'DOM取消合成顾客',privacy_accepted:true,fulfillment_method:'PICKUP'});
 await call(`/api/v1/me/reservations/${row.id}/cancellation-requests`,customer,'POST',{expected_version:row.version,reason:'合成取消意向'});
 const w=await start();await field(w,'本店历史搜索','DOM取消合成顾客');await button(w,'应用筛选').trigger('click');await settle(()=>w.find('[aria-label="商户日常工作台"]').attributes('aria-busy')==='false');const card=w.find('[aria-label="待办与历史"] article');expect(card.findAll('button').some(x=>x.text()==='已确认')).toBe(false);
 await card.findAll('button').find(x=>x.text()==='查看详情与历史')!.trigger('click');await settle(()=>w.find('[aria-label="取消申请处理"]').exists());expect(button(w,'明确同意取消').attributes('disabled')).toBeDefined();await field(w,'给顾客的处理说明','已确认同意取消');await button(w,'明确同意取消').trigger('click');await settle(()=>w.find('[aria-label="商户日常工作台"]').attributes('aria-busy')==='false');
 const saved=await call(`/api/v1/merchant/tenants/${tid}/reservations/${row.id}`,owner);expect(saved.status).toBe('CANCELLED');expect(saved.cancellation_requests[0].status).toBe('ACCEPTED');
});
