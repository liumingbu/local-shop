import { auth, ApiError, needLogin, request, requireId } from '../../lib/client';
import { finishMutation, mutate, pending } from '../../lib/drafts';
import { route, run, timeText } from '../../lib/ui';
import type { ListResult } from '../../lib/types';
interface Invitation {id:string;proposed_name:string;status:string;version:number;tenant_id:string|null;created_at:string}
// Account-scoped storage namespace only; never sent as a business tenant ID.
const ACCOUNT_SCOPE='00000000-0000-0000-0000-000000000000',SLOT='shop-invitation-response';
const labels:Record<string,string>={INVITED:'待本人回应',ACCEPTED:'已接受，待平台审核',DECLINED:'本人已谢绝',APPROVED:'已批准开店',REJECTED:'未通过平台审核'};
Page({alive:true,view:0,
 data:{busy:false,error:'',notice:'',owner:'',accountCode:'',page:1,total:0,locked:false,items:[] as (Invitation&{label:string;time:string})[]},
 onLoad(){void this.load();},onShow(){this.alive=true;if(this.data.owner!==auth().userId)this.setData({items:[],owner:'',accountCode:'',page:1});void this.load();},
 onHide(){this.view++;this.alive=false;this.setData({busy:false,items:[],owner:'',accountCode:''});},onUnload(){this.alive=false;},
 async rows(){const rows=await request<ListResult<Invitation>>(`/api/v1/me/shop-invitations?page=${this.data.page}&limit=20`);return {total:rows.total,items:rows.items.map(x=>({...x,label:labels[x.status]||x.status,time:timeText(x.created_at)}))};},
 load(){return run(this,async commit=>{needLogin();commit({items:[],owner:auth().userId,accountCode:auth().accountCode||auth().userId,locked:!!pending(ACCOUNT_SCOPE,SLOT)});commit(await this.rows());});},
 respond(event:WechatMiniprogram.TouchEvent){if(this.data.busy||this.data.locked)return;const row=this.data.items.find(x=>x.id===event.currentTarget.dataset.id),decision=String(event.currentTarget.dataset.decision);
  if(!row||row.status!=='INVITED'||!['ACCEPTED','DECLINED'].includes(decision))return;
  return this.perform(`/api/v1/me/shop-invitations/${requireId(row.id)}/response`,{expected_version:row.version,decision});
 },
 perform(path:string,body:unknown){return run(this,async commit=>{needLogin();const view=this.view,epoch=auth().generation;
  try{await mutate(ACCOUNT_SCOPE,SLOT,path,'POST',body);}finally{commit({locked:!!pending(ACCOUNT_SCOPE,SLOT)});}
  if(!this.alive||view!==this.view||epoch!==auth().generation)return;const rows=await this.rows();if(!this.alive||view!==this.view||epoch!==auth().generation)return;
  finishMutation(ACCOUNT_SCOPE,SLOT);commit({...rows,locked:false,notice:'已保存本人回应；接受邀请不代表已经审核通过或公开营业。'});
 });},
 retry(){return run(this,async commit=>{const operation=pending(ACCOUNT_SCOPE,SLOT);if(!operation)throw new ApiError('INVITATION_NOT_FOUND');
  const view=this.view,epoch=auth().generation;try{await mutate(ACCOUNT_SCOPE,SLOT,operation.path,operation.method,operation.body);}finally{commit({locked:!!pending(ACCOUNT_SCOPE,SLOT)});}
  if(!this.alive||view!==this.view||epoch!==auth().generation)return;const rows=await this.rows();if(!this.alive||view!==this.view||epoch!==auth().generation)return;finishMutation(ACCOUNT_SCOPE,SLOT);commit({...rows,locked:false});
 });},
 previous(){if(!this.data.busy&&this.data.page>1){this.setData({page:this.data.page-1});void this.load();}},next(){if(!this.data.busy&&this.data.page*20<this.data.total){this.setData({page:this.data.page+1});void this.load();}},
 enter(event:WechatMiniprogram.TouchEvent){const row=this.data.items.find(x=>x.id===event.currentTarget.dataset.id);if(row?.status==='APPROVED'&&row.tenant_id)route('merchant',row.tenant_id);},
 home(){wx.navigateTo({url:'/pages/index/index'});},
});
