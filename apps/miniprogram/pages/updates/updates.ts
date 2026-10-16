import {auth,errorText,needLogin,request,requireId} from '../../lib/client';
import {labels,route,run,timeText} from '../../lib/ui';
type Notice={event_key:string;kind:string;record_id:string;title:string;event_status:string;created_at:string;read_at:string|null;time?:string;statusLabel?:string};
type Feed={items:Notice[];total:number;unread:number;notice:string};
Page({alive:true,view:0,timer:undefined as ReturnType<typeof setTimeout>|undefined,delay:60000,
 data:{busy:false,error:'',storeId:'',merchant:false,page:1,total:0,unread:0,items:[] as Notice[],notice:'',owner:''},
 onLoad(query:Record<string,string>){try{this.setData({storeId:requireId(query.store_id),merchant:query.audience==='merchant'});void this.load();}catch(e){this.setData({error:errorText(e)});}},
 onShow(){this.alive=true;if(this.data.owner!==auth().userId)this.setData({page:1,items:[],total:0,unread:0});if(this.data.storeId)void this.load();},
 onHide(){this.alive=false;this.view++;if(this.timer)clearTimeout(this.timer);this.setData({busy:false,items:[],total:0,unread:0,error:'',notice:''});},
 onUnload(){this.onHide();},
 onSessionInvalidated(){this.onHide();this.setData({error:'登录已变更或失效，请重新从入口登录。'});},
 base(){return this.data.merchant?`/api/v1/merchant/tenants/${this.data.storeId}/updates`:`/api/v1/me/stores/${this.data.storeId}/updates`;},
 schedule(){if(this.timer)clearTimeout(this.timer);if(this.alive)this.timer=setTimeout(()=>void this.load(),this.delay);},
 async load(){await run(this,async commit=>{needLogin();const value=await request<Feed>(this.base()+`?page=${this.data.page}`);commit({...value,items:value.items.map(x=>({...x,time:timeText(x.created_at),statusLabel:labels[x.event_status]||'请查看记录'})),owner:auth().userId});});this.delay=this.data.error?Math.min(this.delay*2,300000):60000;this.schedule();},
 async mark(event:WechatMiniprogram.TouchEvent){const key=String(event.currentTarget.dataset.key);if(!this.data.items.some(x=>x.event_key===key))return;await run(this,async()=>{await request(this.base()+'/read','POST',{event_keys:[key]});});if(this.alive&&!this.data.error)await this.load();},
 previous(){if(this.data.busy||this.data.page<=1)return;this.setData({page:this.data.page-1});void this.load();},
 next(){if(this.data.busy||this.data.page*50>=this.data.total)return;this.setData({page:this.data.page+1});void this.load();},
 open(event:WechatMiniprogram.TouchEvent){const row=this.data.items.find(x=>x.event_key===event.currentTarget.dataset.key);if(row)route(this.data.merchant?'merchantdetail':'detail',this.data.storeId,`&kind=${row.kind}&record_id=${requireId(row.record_id)}`);},
 back(){route(this.data.merchant?'merchant':'records',this.data.storeId);}
});
