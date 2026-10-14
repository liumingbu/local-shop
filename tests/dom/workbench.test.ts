import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import {mount,flushPromises,type VueWrapper} from '@vue/test-utils';
import Workbench from '../../apps/admin/src/WorkbenchPanel.vue';
import App from '../../apps/admin/src/App.vue';
const user='00000000-0000-4000-8000-000000000001',tenant='00000000-0000-4000-8000-000000000101',id='00000000-0000-4000-8000-000000000201';
let wrappers:VueWrapper[]=[];let posts:any[]=[];let records:any[]=[];let lost=false;let conflict=false;
const store={name:'很长很长的合成店铺名称用于换行检查',description:'合成说明',version:1,public_contact:'合成联系电话',public_address:'合成地址',business_hours:'08:00–18:00',delivery_note:'确认后自提',allow_pickup:true,allow_delivery:false,published:true,logo_media_id:'00000000-0000-4000-8000-000000000301'};
function reply(value:unknown,status=200){return new Response(JSON.stringify(value),{status,headers:{'Content-Type':'application/json'}});}
function findButton(w:VueWrapper,text:string){const match=w.findAll('button').find(b=>b.text()===text);if(!match)throw Error('Button not found: '+text);return match;}
async function input(w:VueWrapper,label:string,value:string|boolean){const target=w.findAll('label').find(x=>x.text().startsWith(label));if(!target)throw Error('Label not found '+label);await target.find('input,textarea,select').setValue(value);}
async function mounted(component:any=Workbench,props:Record<string,unknown>={token:'synthetic-token',userId:user,tenantId:tenant,role:'OWNER'}){const w=mount(component,{props,attachTo:document.body});wrappers.push(w);await flushPromises();return w;}
beforeEach(()=>{localStorage.clear();records=[];posts=[];lost=false;conflict=false;vi.stubEnv('VITE_ENABLE_DEVELOPMENT_LOGIN','true');
 vi.stubGlobal('fetch',vi.fn(async(path:string,options:any={})=>{
 const method=options.method||'GET',body=options.body?JSON.parse(options.body):null;
 if(path==='/api/v1/dev/session')return reply({access_token:'synthetic-token'});
 if(path==='/api/v1/dev/me')return reply({user_id:user});
 if(path==='/api/v1/platform/me')return reply({code:'PLATFORM_ADMIN_REQUIRED'},403);
 if(path==='/api/v1/merchant/tenants')return reply({items:[{id:tenant,name:store.name,role:'OWNER'}]});
 if(path.endsWith('/store')){if(method==='PUT'){posts.push({path,body});if(conflict)return reply({code:'VERSION_CONFLICT'},409);return reply({...store,...body,version:2});}return reply(store);}
 if(path.endsWith('/workbench-summary'))return reply({counts:{},as_of:new Date().toISOString()});
 if(path.includes('/categories'))return reply({items:[],total:0});
 if(path.includes('/products'))return reply({items:[],total:0});
 if(method==='POST'){
  const key=options.headers['Idempotency-Key'];posts.push({path,body,key});
  if(conflict)return reply({code:'VERSION_CONFLICT'},409);
  if(path.endsWith('/reservations')){if(!records.length)records.push({id,tenant_id:tenant,...body,status:body.mark_confirmed?'CONFIRMED':'PENDING_CONFIRMATION',version:1,created_at:new Date().toISOString(),events:[{to_status:'PENDING_CONFIRMATION',note:''}],confirmation_revisions:[]});
   if(lost){lost=false;throw Error('synthetic lost response');}return reply(records[0],201);}
  if(path.endsWith('/transitions')){Object.assign(records[0],{status:body.target_status,version:records[0].version+1});records[0].events.push({to_status:body.target_status,note:body.note});return reply(records[0]);}
  if(path.endsWith('/confirmation-revisions')){records[0].status='PENDING_CONFIRMATION';records[0].version++;records[0].confirmation_revisions=[{id:'00000000-0000-4000-8000-000000000401',details:body,confirmed_version:null}];return reply(records[0],201);}
 }
 if(path.includes('/reservations?'))return reply({items:records,total:records.length});
 if(path.endsWith('/reservations/'+id))return reply(records[0]);
 throw Error('Unhandled '+method+' '+path);
 }));});
afterEach(()=>{for(const w of wrappers)w.unmount();wrappers=[];vi.unstubAllGlobals();vi.unstubAllEnvs();document.body.innerHTML='';});
describe('actual Vue DOM events in jsdom; NOT browser rendering',()=>{
 it('formal/default mode never displays demo selector or sends a demo login',async()=>{vi.stubEnv('VITE_ENABLE_DEVELOPMENT_LOGIN','false');const w=await mounted(App,{});expect(w.text()).toContain('正式账号入口');expect(w.find('select').exists()).toBe(false);expect(fetch).not.toHaveBeenCalled();});
 it('login prioritizes workbench; navigates catalog and logs out clearing private DOM',async()=>{const w=await mounted(App,{});await findButton(w,'进入工作台').trigger('click');await flushPromises();expect(w.find('[aria-label="商户日常工作台"]').isVisible()).toBe(true);expect(w.find('[aria-label="批量商品维护"]').isVisible()).toBe(false);await findButton(w,'商品维护').trigger('click');expect(w.find('[aria-label="批量商品维护"]').isVisible()).toBe(true);await findButton(w,'退出登录').trigger('click');expect(w.find('[aria-label="商户日常工作台"]').exists()).toBe(false);expect(w.text()).not.toContain(store.name);});
 it('free-text create and double submit produce one command; then complete and close history',async()=>{const w=await mounted();await input(w,'顾客称呼','合成顾客甲');await input(w,'原始需求','0.5斤干贝分两袋');const form=w.find('form');await Promise.all([form.trigger('submit'),form.trigger('submit')]);await flushPromises();expect(posts).toHaveLength(1);expect(w.findAll('article')).toHaveLength(1);for(const state of ['已确认','备货中','待取/送','已完成']){await findButton(w,state).trigger('click');await flushPromises();expect(w.find('.badge').text()).toBe(state);}await findButton(w,'查看详情与历史').trigger('click');await flushPromises();expect(w.find('[aria-label="处理详情"]').text()).toContain('0.5斤');await findButton(w,'关闭详情').trigger('click');expect(w.find('[aria-label="处理详情"]').exists()).toBe(false);});
 it('lost committed response survives page remount and replays identical key and payload',async()=>{let w=await mounted();await input(w,'顾客称呼','合成网络顾客');await input(w,'原始需求','保留这段');lost=true;await w.find('form').trigger('submit');await flushPromises();expect(w.find('[role="alert"]').text()).toContain('结果未确认');w.unmount();wrappers=[];w=await mounted();expect(w.find('textarea').element.value).toBe('保留这段');await findButton(w,'重试原提交').trigger('click');await flushPromises();expect(posts).toHaveLength(2);expect(posts[1]).toEqual(posts[0]);expect(records).toHaveLength(1);expect(w.text()).not.toContain('原操作结果待确认');});
 it('saved drafts are scoped to authenticated user and tenant, never carried into another shop',async()=>{let w=await mounted();await input(w,'原始需求','甲店私有草稿');w.unmount();wrappers=[];w=await mounted(Workbench,{token:'synthetic-token',userId:user,tenantId:'00000000-0000-4000-8000-000000000102',role:'OWNER'});expect(w.find('textarea').element.value).toBe('');w.unmount();wrappers=[];w=await mounted();expect(w.find('textarea').element.value).toBe('甲店私有草稿');});
 it('storage failure blocks new submission before network write',async()=>{const w=await mounted();await input(w,'顾客称呼','合成');await input(w,'原始需求','草稿');vi.spyOn(Storage.prototype,'setItem').mockImplementation(()=>{throw Error('quota');});await w.find('form').trigger('submit');await flushPromises();expect(posts).toHaveLength(0);expect(w.find('[role="alert"]').text()).toContain('无法可靠保存草稿');});
 it('confirmation candidate requires visible detail and fresh explicit agreement',async()=>{const w=await mounted();await input(w,'顾客称呼','合成确认');await input(w,'原始需求','原始需求');await w.find('form').trigger('submit');await flushPromises();await findButton(w,'查看详情与历史').trigger('click');await flushPromises();await input(w,'确认内容','确认半斤干贝');await input(w,'变更原因','电话核对');await w.find('[aria-label="处理详情"] form').trigger('submit');await flushPromises();await findButton(w,'已确认').trigger('click');expect(w.find('[role="alert"]').text()).toContain('先查看详情');await findButton(w,'查看详情与历史').trigger('click');await flushPromises();await input(w,'已与顾客核对',true);const region=w.find('[aria-label="处理详情"]');await region.findAll('button').find(x=>x.text()==='已确认')!.trigger('click');await flushPromises();expect(posts.at(-1).body.customer_agreed).toBe(true);expect(posts.at(-1).body.confirmation_revision_id).toBe('00000000-0000-4000-8000-000000000401');});
 it('store editor preserves profile and does not send a Logo removal',async()=>{const w=await mounted();await input(w,'店名','新合成店名');await w.find('.store-settings form').trigger('submit');await flushPromises();expect(posts[0].body).toMatchObject({name:'新合成店名',allow_pickup:true,published:true,public_contact:store.public_contact});expect(posts[0].body).not.toHaveProperty('logo_media_id');});
 it('version conflict is explained without automatic overwrite or new write',async()=>{const w=await mounted();await input(w,'店名','待核对店名');conflict=true;await w.find('.store-settings form').trigger('submit');await flushPromises();expect(posts).toHaveLength(1);expect(w.find('[role="alert"]').text()).toContain('不会覆盖他人修改');expect(w.find('.store-settings input').element.value).toBe('待核对店名');});
 it('document hide clears private panels; return restores scoped draft without storing token',async()=>{
  const w=await mounted(App,{});await findButton(w,'进入工作台').trigger('click');await flushPromises();await input(w,'原始需求','页面隐藏前的合成草稿');
  const hidden=vi.spyOn(document,'hidden','get').mockReturnValue(true);document.dispatchEvent(new Event('visibilitychange'));await flushPromises();expect(w.find('[aria-label="商户日常工作台"]').exists()).toBe(false);expect(w.text()).not.toContain('页面隐藏前的合成草稿');
  hidden.mockReturnValue(false);document.dispatchEvent(new Event('visibilitychange'));await flushPromises();expect(w.find('[aria-label="快速代记"] textarea').element.value).toBe('页面隐藏前的合成草稿');expect(JSON.stringify(localStorage)).not.toContain('synthetic-token');
 });
 it('logout during an unresolved response never repaints old private data; request remains recoverable',async()=>{
  const w=await mounted(App,{});await findButton(w,'进入工作台').trigger('click');await flushPromises();await input(w,'顾客称呼','延迟合成顾客');await input(w,'原始需求','延迟原操作');
  const previous=globalThis.fetch;let resolve!:(r:Response)=>void;
  vi.stubGlobal('fetch',vi.fn((path:string,options:any)=>options?.method==='POST'&&path.endsWith('/reservations')?new Promise<Response>(r=>{resolve=r;}):previous(path,options)));
  await w.find('[aria-label="快速代记"] form').trigger('submit');await findButton(w,'退出登录').trigger('click');resolve(reply({id},201));await flushPromises();expect(w.find('[aria-label="商户日常工作台"]').exists()).toBe(false);
  expect(Object.values(localStorage).some(x=>String(x).includes('延迟原操作'))).toBe(true);
 });

});
