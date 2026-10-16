import {afterEach,expect,it,vi} from 'vitest';
import {mount,flushPromises,type VueWrapper} from '@vue/test-utils';
import Updates from '../../apps/admin/src/UpdatesPanel.vue';
let w:VueWrapper|undefined;
afterEach(()=>{w?.unmount();w=undefined;vi.unstubAllGlobals();vi.useRealTimers();});
it('updates component escapes event titles, sends only explicit read keys and clears timers on unmount',async()=>{
 vi.useFakeTimers();const writes:unknown[]=[];let read=false;vi.stubGlobal('fetch',vi.fn(async(path:string,options:any={})=>{if(options.method==='POST'){writes.push(JSON.parse(options.body));read=true;}return new Response(JSON.stringify({items:[{event_key:'r:synthetic',title:'<img src=x onerror=alert(1)>',read_at:read?'now':null,created_at:'2026-10-16',event_status:'CONFIRMED'}],total:1,unread:read?0:1,page:1,limit:50,notice:''}));}));
 w=mount(Updates,{props:{token:'synthetic',tenantId:'10000000-0000-4000-8000-000000000001'}});await flushPromises();expect(w.find('img').exists()).toBe(false);expect(w.text()).toContain('<img');expect(writes).toHaveLength(0);await w.findAll('button').find(x=>x.text()==='这条已查看')!.trigger('click');await flushPromises();expect(writes).toEqual([{event_keys:['r:synthetic']}]);expect(w.text()).toContain('本站内未读 0');const before=vi.mocked(fetch).mock.calls.length;w.unmount();w=undefined;await vi.advanceTimersByTimeAsync(600000);expect(vi.mocked(fetch).mock.calls).toHaveLength(before);
});
