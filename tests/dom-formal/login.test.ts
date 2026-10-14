import {expect,it,vi} from 'vitest';
import {mount,flushPromises} from '@vue/test-utils';
import App from '../../apps/admin/src/App.vue';
const base=process.env.LOCAL_SHOP_TEST_API||'';
if(!/^http:\/\/127\.0\.0\.1:\d+$/.test(base))throw Error('Requires isolated formal identity API');
const fetchReal=globalThis.fetch;
async function settle(fn:()=>boolean){for(let i=0;i<300;i++){await flushPromises();if(fn())return;await new Promise(r=>setTimeout(r,20));}throw Error('UI condition timed out');}
async function call(path:string,method='GET',body?:unknown,token=''){const r=await fetchReal(base+path,{method,headers:{'Content-Type':'application/json',...(token?{Authorization:'Bearer '+token}:{})},...(body?{body:JSON.stringify(body)}:{})});if(!r.ok)throw Error('HTTP '+r.status);return r.json();}
it('formal Vue login uses real session/database, explicit miniature-client approval and server logout',async()=>{
 vi.stubEnv('VITE_ENABLE_DEVELOPMENT_LOGIN','false');const sent:string[]=[];
 vi.stubGlobal('fetch',(path:string,options?:RequestInit)=>{sent.push(path);return fetchReal(base+path,options);});
 const w=mount(App,{attachTo:document.body});const button=(label:string)=>{const b=w.findAll('button').find(x=>x.text()===label);if(!b)throw Error('Missing '+label);return b;};
 try{expect(w.find('[aria-label="开发登录"]').exists()).toBe(false);await button('发起工作台登录').trigger('click');await settle(()=>/本次确认码：/.test(w.text()));const code=w.find('[aria-label="正式工作台登录"] strong').text();
 const session=await call('/api/v1/auth/wechat/session','POST',{code:'alice_dom'});await call('/api/v1/auth/browser-approvals/confirm','POST',{code,confirmed:true},session.access_token);await button('我已在小程序确认，核对状态').trigger('click');await settle(()=>w.find('[aria-label="平台管理"]').exists()&&w.text().includes('收件人开店账号码'));expect(w.text()).not.toContain('收件人账号UUID');expect(sent.some(x=>x.startsWith('/api/v1/dev/'))).toBe(false);
 await button('退出登录').trigger('click');await settle(()=>w.find('[aria-label="正式工作台登录"]').exists());expect(sent).toContain('/api/v1/auth/logout');expect(w.find('[aria-label="平台管理"]').exists()).toBe(false);expect(JSON.stringify(localStorage)).not.toContain('ls1_');
 }finally{w.unmount();vi.unstubAllGlobals();vi.unstubAllEnvs();document.body.innerHTML='';}
});
