import { auth, ApiError, errorText, needLogin, privateImage, request, requireId } from '../../lib/client';
import { finishMutation, mutate, pending, readDraft, saveDraft } from '../../lib/drafts';
import { merchantBase, transitions } from '../../lib/merchant';
import { labels, quantityValid, route, run, timeText } from '../../lib/ui';
import type { Cancellation, Draft, Item, RecordData } from '../../lib/types';
function present(row:RecordData){
  const cancellations=row.cancellation_requests||[],revisions=row.confirmation_revisions||[];
  return {row,label:labels[row.status]||row.status,time:timeText(row.created_at),expected:timeText(row.expected_at),
    actions:transitions(row).map(status=>({status,label:labels[status]})),
    pendingCancellation:cancellations.find(x=>x.status==='REQUESTED')||null,
    cancellations:cancellations.map(x=>({...x,label:labels[x.status]||x.status})),
    revisions:revisions.map((x,i)=>({...x,label:x.confirmed_version?'商户已记录确认':i===revisions.length-1?'最新待确认候选':'旧候选',fulfillment:timeText(x.details.fulfillment_at)})),
    events:(row.events||[]).map(x=>({...x,label:labels[x.to_status]||x.to_status,time:timeText(x.created_at)})),
    canPropose:['PENDING_CONFIRMATION','CONFIRMED'].includes(row.status)&&!cancellations.some(x=>x.status==='REQUESTED'),
  };
}
Page({alive:true,view:0,
  data:{busy:false,error:'',notice:'',storeId:'',recordId:'',kind:'reservation',owner:'',row:null as RecordData|null,
    label:'',time:'',expected:'',locked:false,actions:[] as {status:string;label:string}[],pendingCancellation:null as Cancellation|null,
    cancellations:[] as unknown[],revisions:[] as unknown[],events:[] as unknown[],images:[] as {id:string;path:string}[],canPropose:false,
    contactPage:1,contactTotal:0,contactIndex:0,contactMethods:['已电话联系','已微信联系','暂未联系上'],contactNote:'',contactConfirmed:false,contactText:'',contactReviewed:false,contacts:[] as {id:string;method:string;note:string;created_at:string}[],note:'',visible:false,agreed:false,replyText:'',responseNote:'',summary:'',changeReason:'',timeNote:'',date:'',clock:'',items:[] as Item[],
    customerLabel:'',conversionText:'',convertConfirmed:false,methodIndex:0,methods:['自提','配送']},
  onLoad(query:Record<string,string>){try{this.setData({storeId:requireId(query.store_id),recordId:requireId(query.record_id),kind:query.kind==='inquiry'?'inquiry':'reservation'});void this.load();}catch(e){this.setData({error:errorText(e)});}},
  onShow(){this.alive=true;if(this.data.owner!==auth().userId)this.clearInputs();if(this.data.recordId)void this.load();},
  onHide(){this.view++;this.alive=false;this.clearInputs();this.setData({busy:false,row:null,images:[],events:[],revisions:[],cancellations:[],actions:[],pendingCancellation:null});},onUnload(){this.alive=false;},
  onSessionInvalidated(){this.onHide();this.setData({error:'登录已变更或失效，请重新从入口登录。'});},
  clearInputs(){this.setData({contactPage:1,contactTotal:0,contactIndex:0,contactNote:'',contactConfirmed:false,contactText:'',contactReviewed:false,contacts:[],note:'',visible:false,agreed:false,replyText:'',responseNote:'',summary:'',changeReason:'',timeNote:'',date:'',clock:'',items:[],customerLabel:'',conversionText:'',convertConfirmed:false});},
  base(){return `${merchantBase(this.data.storeId)}/${this.data.kind==='inquiry'?'inquiries':'reservations'}/${this.data.recordId}`;},
  slot(){return `merchant-${this.data.recordId}`;},
  async fetchRecord(){const row=await request<RecordData>(this.base());if(row.tenant_id!==this.data.storeId)throw new ApiError('INVALID_STORE_OR_RECORD');return row;},
  load(){return run(this,async commit=>{needLogin();commit({owner:auth().userId,row:null,images:[],agreed:false,actions:[],pendingCancellation:null,canPropose:false});const row=await this.fetchRecord();commit({...present(row),locked:!!pending(this.data.storeId,this.slot())});
    const images=await Promise.all(row.attachments.map(async x=>({id:x.id,path:await privateImage(x.url).catch(()=> '')})));commit({images});const history=await request<{items:{id:string;method:string;note:string;created_at:string}[];total:number}>(this.base()+'/contacts');commit({contacts:history.items,contactTotal:history.total,contactPage:1});});},
  perform(path:string,body:unknown){return run(this,async commit=>{
    needLogin();const view=this.view,epoch=auth().generation,store=this.data.storeId,slot=this.slot();
    try{await mutate(store,slot,path,'POST',body);}finally{commit({locked:!!pending(store,slot)});}
    if(!this.alive||view!==this.view||epoch!==auth().generation)return;
    const row=await this.fetchRecord();if(!this.alive||view!==this.view||epoch!==auth().generation)return;
    finishMutation(store,slot);this.clearInputs();commit({...present(row),locked:false,notice:'已保存并重新读取服务端记录'});
  });},
  retry(){try{const operation=pending(this.data.storeId,this.slot());if(operation)return this.perform(operation.path,operation.body);}catch(e){this.setData({error:errorText(e)});}},
  input(event:WechatMiniprogram.Input){if(this.data.busy||this.data.locked)return;const field=String(event.currentTarget.dataset.field);if(['note','replyText','responseNote','summary','changeReason','timeNote','customerLabel','conversionText','contactNote'].includes(field))this.setData({[field]:event.detail.value});},
  check(event:WechatMiniprogram.CheckboxGroupChange){if(this.data.busy||this.data.locked)return;const values=event.detail.value;this.setData({visible:values.includes('visible'),agreed:values.includes('agreed'),convertConfirmed:values.includes('converted')});},
  method(event:WechatMiniprogram.PickerChange){if(!this.data.busy&&!this.data.locked)this.setData({methodIndex:Number(event.detail.value)});},
  date(event:WechatMiniprogram.PickerChange){if(!this.data.busy&&!this.data.locked)this.setData({date:String(event.detail.value)});},
  clock(event:WechatMiniprogram.PickerChange){if(!this.data.busy&&!this.data.locked)this.setData({clock:String(event.detail.value)});},
  clearTime(){if(!this.data.busy&&!this.data.locked)this.setData({date:'',clock:''});},
  transition(event:WechatMiniprogram.TouchEvent){
    const row=this.data.row;if(!row||this.data.busy||this.data.locked)return;const target=String(event.currentTarget.dataset.status);if(!transitions(row).includes(target))return;
    const revisions=row.confirmation_revisions||[],latest=revisions[revisions.length-1];
    if(target==='CONFIRMED'&&latest&&!this.data.agreed){this.setData({error:'请核对最新候选，并勾选已与顾客重新确认'});return;}
    return this.perform(this.base()+'/transitions',{expected_version:row.version,target_status:target,note:this.data.note,visible_to_customer:this.data.visible,
      ...(target==='CONFIRMED'&&latest?{confirmation_revision_id:latest.id,customer_agreed:true}:{})});
  },
  contactsPage(event:WechatMiniprogram.TouchEvent){return run(this,async commit=>{const next=this.data.contactPage+Number(event.currentTarget.dataset.step);if(next<1||next>Math.max(1,Math.ceil(this.data.contactTotal/50)))return;const history=await request<{items:{id:string;method:string;note:string;created_at:string}[];total:number}>(this.base()+`/contacts?page=${next}`);commit({contacts:history.items,contactTotal:history.total,contactPage:next});});},
  contactMethod(event:WechatMiniprogram.PickerChange){if(!this.data.busy&&!this.data.locked)this.setData({contactIndex:Number(event.detail.value)});},
  contactCheck(event:WechatMiniprogram.CheckboxGroupChange){if(!this.data.busy&&!this.data.locked)this.setData({contactConfirmed:event.detail.value.includes('contact'),contactReviewed:event.detail.value.includes('review')});},
  logContact(){const row=this.data.row;if(!row||this.data.locked||!this.data.contactConfirmed)return;return this.perform(this.base()+'/contacts',{expected_version:row.version,confirmed:true,method:['PHONE','WECHAT','NOT_REACHED'][this.data.contactIndex],note:this.data.contactNote});},
  contactDraft(){return run(this,async commit=>{if(this.data.kind!=='reservation')return;const result=await request<{text:string}>(this.base()+'/contact-draft');commit({contactText:result.text,contactReviewed:false});});},
  copyContact(){if(!this.data.contactReviewed||this.data.busy||!this.alive)return;const epoch=auth().generation,view=this.view;wx.setClipboardData({data:this.data.contactText,success:()=>{if(this.alive&&view===this.view&&epoch===auth().generation)this.setData({notice:'已复制，请核对收件人后自行发送；未登记联系成功。'});},fail:()=>{if(this.alive&&view===this.view&&epoch===auth().generation)this.setData({error:'复制未成功，请手动选择摘要复制。'});}});},
  reply(){const row=this.data.row;if(row&&!this.data.locked)return this.perform(this.base()+'/replies',{expected_version:row.version,text:this.data.replyText,visible_to_customer:this.data.visible});},
  close(){const row=this.data.row;if(row&&!this.data.locked)return this.perform(this.base()+'/close',{expected_version:row.version});},
  convert(){const row=this.data.row;if(row&&!this.data.locked)return this.perform(this.base()+'/convert',{expected_version:row.version,customer_label:this.data.customerLabel,raw_text:this.data.conversionText,
    source:'MERCHANT_WECHAT',fulfillment_method:this.data.methodIndex===1?'DELIVERY':'PICKUP',mark_confirmed:this.data.convertConfirmed});},
  decision(event:WechatMiniprogram.TouchEvent){const row=this.data.row,cancel=row?.cancellation_requests?.find(x=>x.status==='REQUESTED');if(!row||!cancel||this.data.locked)return;
    const decision=String(event.currentTarget.dataset.decision);if(!['ACCEPTED','REJECTED'].includes(decision))return;
    return this.perform(this.base()+`/cancellation-requests/${cancel.id}/decision`,{expected_version:row.version,decision,response_note:this.data.responseNote});},
  addItem(){if(this.data.busy||this.data.locked||this.data.items.length>=100)return;this.setData({items:[...this.data.items,{name:'',quantity:'1',unit:'',spec:''}]});},
  item(event:WechatMiniprogram.Input){if(this.data.busy||this.data.locked)return;const index=Number(event.currentTarget.dataset.index),field=String(event.currentTarget.dataset.field);
    if(!this.data.items[index]||!['name','quantity','unit','spec'].includes(field))return;const items=this.data.items.map((x,i)=>i===index?{...x,[field]:event.detail.value}:x);this.setData({items});},
  removeItem(event:WechatMiniprogram.TouchEvent){if(!this.data.busy&&!this.data.locked)this.setData({items:this.data.items.filter((_,i)=>i!==Number(event.currentTarget.dataset.index))});},
  copyItems(){if(this.data.busy||this.data.locked)return;this.setData({items:(this.data.row?.items||[]).map(({name,quantity,unit,spec})=>({name,quantity,unit,spec}))});},
  propose(){const row=this.data.row;if(!row||!this.data.canPropose||this.data.locked)return;
    try{if(this.data.items.some(x=>!quantityValid(x.quantity)))throw new ApiError('INVALID_QUANTITY');if(this.data.clock&&!this.data.date)throw new ApiError('DATE_REQUIRED');
      const at=this.data.date&&this.data.clock?new Date(`${this.data.date}T${this.data.clock}:00+08:00`).toISOString():null;
      return this.perform(this.base()+'/confirmation-revisions',{expected_version:row.version,summary:this.data.summary,items:this.data.items,change_reason:this.data.changeReason,
        fulfillment_at:at,time_note:[this.data.date&&!this.data.clock?this.data.date:'',this.data.timeNote].filter(Boolean).join(' ')});
    }catch(e){this.setData({error:errorText(e)});}},
  copy(){return run(this,async commit=>{if(this.data.kind!=='reservation'||this.data.locked)return;const old=readDraft(this.data.storeId,'merchant-record');if(old.raw_text||old.items.length||pending(this.data.storeId,'merchant-record'))throw new ApiError('EXISTING_DRAFT');const result=await request<{draft:Draft;warnings:string[]}>(this.base()+'/copy-draft');if(!this.alive)return;saveDraft(this.data.storeId,{...result.draft,privacy_accepted:false,copy_review_required:true},'merchant-record');commit({notice:result.warnings.join('；')});route('merchant',this.data.storeId);});},
  converted(){const id=this.data.row?.converted_reservation_id;if(id)route('merchantdetail',this.data.storeId,'&kind=reservation&record_id='+requireId(id));},
  back(){route('merchant',this.data.storeId);},home(){wx.navigateTo({url:'/pages/index/index'});},
});
