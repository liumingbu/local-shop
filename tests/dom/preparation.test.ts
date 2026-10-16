import {afterEach,expect,it,vi} from 'vitest';
import {mount,flushPromises,type VueWrapper} from '@vue/test-utils';
import PreparationPanel from '../../apps/admin/src/PreparationPanel.vue';
let wrapper:VueWrapper|undefined;
const props={token:'synthetic',userId:'00000000-0000-4000-8000-000000000001',tenantId:'10000000-0000-4000-8000-000000000001'};
const response=(data:unknown,status=200)=>({ok:status<300,status,json:async()=>data});
function fixture(){vi.stubGlobal('fetch',vi.fn(async(path:string,options:any)=>{
 if(path.endsWith('/preparation'))return response({store:{name:'<img src=x onerror=alert(1)>',description:'合成',public_contact:'',public_address:''},steps:[],preview_products:[],product_count:0,category_count:0,notice:'可稍后'});
 if(path.endsWith('/template'))return response({csv:'template',max_bytes:32});
 if(options?.method==='POST')return response({code:'CSV_TEMPLATE_COLUMNS_REQUIRED'},422);
 return response({items:[]});}));wrapper=mount(PreparationPanel,{props});}
afterEach(()=>{wrapper?.unmount();vi.unstubAllGlobals();});
it('bounded preview gives a precise error without a write; store text is never HTML',async()=>{fixture();await flushPromises();await wrapper!.find('textarea').setValue('x'.repeat(33));await wrapper!.findAll('button').find(b=>b.text()==='解析并预览')!.trigger('click');await flushPromises();expect(wrapper!.text()).toContain('CSV超过文件大小限制');expect(vi.mocked(fetch).mock.calls.some(([,o])=>o?.method==='POST')).toBe(false);await wrapper!.findAll('button').find(b=>b.text()==='店内预览')!.trigger('click');expect(wrapper!.find('img').exists()).toBe(false);expect(wrapper!.text()).toContain('<img src=x onerror=alert(1)>');});
it('server rejects wrong template clearly and leaving the page does not create products',async()=>{fixture();await flushPromises();await wrapper!.find('textarea').setValue('wrong,columns');await wrapper!.findAll('button').find(b=>b.text()==='解析并预览')!.trigger('click');await flushPromises();expect(wrapper!.text()).toContain('8个列名和顺序');expect(wrapper!.find('[aria-label="导入任务"]').exists()).toBe(false);});
