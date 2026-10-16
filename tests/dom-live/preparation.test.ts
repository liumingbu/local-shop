import {afterEach,expect,it,vi} from 'vitest';
import {mount,flushPromises,type VueWrapper} from '@vue/test-utils';
import PreparationPanel from '../../apps/admin/src/PreparationPanel.vue';
const base=process.env.LOCAL_SHOP_TEST_API||'';
if(!/^http:\/\/127\.0\.0\.1:\d+$/.test(base))throw Error('Requires isolated loopback API');
const original=globalThis.fetch;let wrapper:VueWrapper|undefined;
const tenant='10000000-0000-4000-8000-000000000001';
function button(label:string){const el=wrapper!.findAll('button').find(x=>x.text()===label);if(!el)throw Error('missing '+label);return el;}
async function settle(fn:()=>boolean){for(let n=0;n<300;n++){await flushPromises();if(fn())return;await new Promise(r=>setTimeout(r,20));}throw Error('DOM did not settle');}
async function token(){const r=await original(base+'/api/v1/dev/session',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({identity:'merchant-a'})});return(await r.json()).access_token;}
afterEach(()=>{wrapper?.unmount();wrapper=undefined;vi.unstubAllGlobals();document.body.innerHTML='';});
it('CSV preview/explicit categories, lost committed row response, reload and resume create only draft products',async()=>{
 const t=await token();let lost=true;let posts=0;
 vi.stubGlobal('fetch',async(path:string,options:any)=>{const response=await original(base+path,options);if(options?.method==='POST'&&/\/rows\/1$/.test(path)){posts++;if(lost){lost=false;throw Error('synthetic lost response after commit');}}return response;});
 const props={token:t,userId:'00000000-0000-4000-8000-000000000001',tenantId:tenant};
 wrapper=mount(PreparationPanel,{props,attachTo:document.body});await settle(()=>wrapper!.attributes('aria-busy')==='false');
 await wrapper.find('textarea').setValue('商品名称,分类,规格,单位,参考价格,供货说明,排序,商品介绍\nDOM合成茶叶,DOM导入分类,散装,斤,,常备,0,合成\nDOM合成茶叶,DOM导入分类,礼盒,盒,12.50,待确认,1,合成');
 await button('解析并预览').trigger('click');await settle(()=>wrapper!.find('[aria-label="导入任务"]').exists()&&wrapper!.attributes('aria-busy')==='false');
 expect(wrapper.text()).toContain('DOM导入分类');expect(wrapper.text()).toContain('尚未执行 2');
 const checks=wrapper.findAll('input[type="checkbox"]');await checks[0].setValue(true);await checks[2].setValue(true);
 await button('确认导入范围').trigger('click');await settle(()=>wrapper!.text().includes('CONFIRMED')&&wrapper!.attributes('aria-busy')==='false');
 await button('创建草稿/继续未完成行').trigger('click');await settle(()=>wrapper!.find('[role="alert"]').exists()&&wrapper!.attributes('aria-busy')==='false');
 wrapper.unmount();wrapper=mount(PreparationPanel,{props,attachTo:document.body});await settle(()=>wrapper!.findAll('li button').length>0&&wrapper!.attributes('aria-busy')==='false');
 await wrapper.find('li button').trigger('click');await settle(()=>wrapper!.text().includes('成功 1')&&wrapper!.attributes('aria-busy')==='false');
 await button('创建草稿/继续未完成行').trigger('click');await settle(()=>wrapper!.text().includes('成功 2')&&wrapper!.attributes('aria-busy')==='false');expect(posts).toBe(1);
 const r=await original(base+`/api/v1/merchant/tenants/${tenant}/products`,{headers:{Authorization:'Bearer '+t}});const products=(await r.json()).items.filter((p:any)=>p.name==='DOM合成茶叶');expect(products).toHaveLength(2);expect(products.every((p:any)=>p.status==='DRAFT')).toBe(true);
 await wrapper.find('textarea').setValue('商品名称,分类,规格,单位,参考价格,供货说明,排序,商品介绍\nDOM合成茶叶,DOM导入分类,散装,斤,,常备,0,合成');await button('解析并预览').trigger('click');await settle(()=>wrapper!.text().includes('疑似重复')&&wrapper!.attributes('aria-busy')==='false');expect(button('确认导入范围').attributes('disabled')).toBeDefined();
 await button('店内预览').trigger('click');expect(wrapper.find('[aria-label="店内预览"]').exists()).toBe(true);expect(wrapper.text()).toContain('真实微信分享/二维码待接入');
});
