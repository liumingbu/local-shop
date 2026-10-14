import { auth, ApiError, errorText, requireId, request } from '../../lib/client';
import { clearDraft, finishMutation, mutate, pending, readDraft, saveDraft } from '../../lib/drafts';
import { memberships, merchantBase, selectTenant, type Tenant } from '../../lib/merchant';
import { labels, route, run, timeText } from '../../lib/ui';
import type { Draft,ListResult,RecordData,Store } from '../../lib/types';
Page({alive:true,view:0,validEntry:false,
  data:{busy:false,error:'',notice:'',requestedId:'',tenantId:'',owner:'',members:[] as Tenant[],memberNames:[] as string[],memberIndex:0,role:'',storeName:'',
    form:null as Draft|null,locked:false,sourceIndex:0,sources:['电话','微信','到店'],methodIndex:0,methods:['自提','配送'],kind:'reservation',status:'',day:'',onDate:'',methodFilter:'',search:'',overdue:false,page:1,total:0,
    records:[] as (RecordData & {label:string;time:string})[],counts:[] as {name:string;status:string;kind:string;total:number}[],lastId:''},
  onLoad(query:Record<string,string>){try{this.setData({requestedId:query.store_id?requireId(query.store_id):''});this.validEntry=true;void this.load();}catch(e){this.setData({error:errorText(e)});}},
  onShow(){this.alive=true;if(this.data.owner!==auth().userId)this.setData({tenantId:'',members:[],form:null,records:[],counts:[],lastId:'',page:1});if(this.validEntry)void this.load();},
  onHide(){this.view++;this.alive=false;this.setData({busy:false,form:null,records:[],counts:[]});},onUnload(){this.alive=false;},
  restore(){if(!this.data.tenantId)return;const form=readDraft(this.data.tenantId,'merchant-record');this.setData({form,locked:!!pending(this.data.tenantId,'merchant-record'),
    sourceIndex:Math.max(0,['MERCHANT_PHONE','MERCHANT_WECHAT','MERCHANT_IN_STORE'].indexOf(form.source||'MERCHANT_PHONE')),methodIndex:form.fulfillment_method==='DELIVERY'?1:0});},
  async fetchRows(){const suffix=this.data.kind==='inquiry'?'inquiries':'reservations';return request<ListResult<RecordData>>(`${merchantBase(this.data.tenantId)}/${suffix}?page=${this.data.page}&limit=20${this.data.status?'&status='+this.data.status:''}${this.data.kind==='reservation'?this.query():''}`);},
  query(){return `${this.data.day?'&day='+this.data.day:''}${this.data.onDate?'&on_date='+this.data.onDate:''}${this.data.methodFilter?'&method='+this.data.methodFilter:''}${this.data.search?'&q='+encodeURIComponent(this.data.search):''}${this.data.overdue?'&overdue=true':''}`;},
  filters(event:WechatMiniprogram.Input){const key=String(event.currentTarget.dataset.field);if(!this.data.busy&&['search','onDate'].includes(key))this.setData({[key]:event.detail.value});},
  dayFilter(event:WechatMiniprogram.TouchEvent){if(!this.data.busy){this.setData({day:String(event.currentTarget.dataset.day||''),page:1});void this.load();}},
  methodFilter(event:WechatMiniprogram.PickerChange){if(!this.data.busy){this.setData({methodFilter:['','PICKUP','DELIVERY'][Number(event.detail.value)],page:1});void this.load();}},
  overdueFilter(){if(!this.data.busy){this.setData({overdue:!this.data.overdue,page:1});void this.load();}},
  reviewed(event:WechatMiniprogram.CheckboxGroupChange){if(!this.data.busy&&!this.data.locked&&this.data.form)this.persist({...this.data.form,copy_review_required:!event.detail.value.includes('reviewed')});},
  item(event:WechatMiniprogram.Input){if(this.data.busy||this.data.locked||!this.data.form)return;const index=Number(event.currentTarget.dataset.index),field=String(event.currentTarget.dataset.field);if(!['quantity','unit','spec','name'].includes(field))return;this.persist({...this.data.form,items:this.data.form.items.map((x,i)=>i===index?{...x,[field]:event.detail.value}:x)});},
  async fetchCounts(){const summary=await request<{counts:Record<string,number>}>(merchantBase(this.data.tenantId)+'/workbench-summary');return [['待确认','PENDING_CONFIRMATION','reservation'],['待备货','CONFIRMED','reservation'],['备货中','PREPARING','reservation'],['待取/送','READY','reservation'],['配送中','OUT_FOR_DELIVERY','reservation'],['待回复','NEW_INQUIRY','inquiry']].map(([name,status,kind])=>({name,status:kind==='inquiry'?'NEW':status,kind,total:summary.counts[status]||0}));},
  load(){return run(this,async commit=>{
    const view=this.view,epoch=auth().generation;commit({owner:auth().userId,records:[],counts:[]});const members=await memberships();if(!this.alive||view!==this.view||epoch!==auth().generation)return;const selected=selectTenant(members,this.data.requestedId||this.data.tenantId);
    commit({members,memberNames:members.map(x=>x.name)});if(!selected){commit({tenantId:'',form:null,notice:'请选择已授权店铺'});return;}
    commit({tenantId:selected.id,role:selected.role,memberIndex:members.findIndex(x=>x.id===selected.id),notice:''});this.restore();
    let name=selected.name;try{name=(await request<Store>(merchantBase(selected.id)+'/store')).name;}catch(e){if(!(e instanceof ApiError&&e.status===404))throw e;}
    const rows=await this.fetchRows();const counts=await this.fetchCounts();
    commit({storeName:name,records:rows.items.map(x=>({...x,label:labels[x.status]||x.status,time:timeText(x.created_at)})),total:rows.total,counts});
  });},
  choose(event:WechatMiniprogram.PickerChange){if(this.data.busy)return;const index=Number(event.detail.value);const member=this.data.members[index];if(!member)return;
    this.setData({requestedId:'',tenantId:member.id,form:null,records:[],page:1,lastId:'',status:'',kind:'reservation'});void this.load();},
  persist(form:Draft){try{saveDraft(this.data.tenantId,form,'merchant-record');this.setData({form,error:''});}catch(e){this.setData({error:errorText(e)});}},
  input(event:WechatMiniprogram.Input){if(this.data.busy||this.data.locked||!this.data.form)return;const field=String(event.currentTarget.dataset.field);
    if(['customer_label','raw_text','internal_note','expected_time_note','contact_name','contact_phone','delivery_address'].includes(field))this.persist({...this.data.form,[field]:event.detail.value});},
  source(event:WechatMiniprogram.PickerChange){if(this.data.busy||this.data.locked||!this.data.form)return;const index=Number(event.detail.value);this.persist({...this.data.form,source:['MERCHANT_PHONE','MERCHANT_WECHAT','MERCHANT_IN_STORE'][index]});this.setData({sourceIndex:index});},
  method(event:WechatMiniprogram.PickerChange){if(this.data.busy||this.data.locked||!this.data.form)return;const index=Number(event.detail.value);this.persist({...this.data.form,fulfillment_method:index===1?'DELIVERY':'PICKUP'});this.setData({methodIndex:index});},
  expectedDate(event:WechatMiniprogram.PickerChange){if(!this.data.busy&&!this.data.locked&&this.data.form)this.persist({...this.data.form,expected_date:String(event.detail.value)});},
  expectedClock(event:WechatMiniprogram.PickerChange){if(!this.data.busy&&!this.data.locked&&this.data.form)this.persist({...this.data.form,expected_clock:String(event.detail.value)});},
  clearExpected(){if(!this.data.busy&&!this.data.locked&&this.data.form)this.persist({...this.data.form,expected_date:'',expected_clock:''});},
  confirmed(event:WechatMiniprogram.CheckboxGroupChange){if(this.data.busy||this.data.locked||!this.data.form)return;this.persist({...this.data.form,mark_confirmed:event.detail.value.includes('confirmed')});},
  create(){return run(this,async commit=>{
    const form=this.data.form;if(form?.expected_clock&&!form.expected_date)throw new ApiError('DATE_REQUIRED');if(form?.copy_review_required)throw new ApiError('COPY_REVIEW_REQUIRED');if(!form)throw new ApiError('EMPTY_DRAFT');const view=this.view,epoch=auth().generation,tenant=this.data.tenantId;
    let row:RecordData;try{row=await mutate<RecordData>(tenant,'merchant-record',merchantBase(tenant)+'/reservations','POST',{
      customer_label:form.customer_label,raw_text:form.raw_text,source:form.source||'MERCHANT_PHONE',fulfillment_method:form.fulfillment_method,
      expected_at:form.expected_date&&form.expected_clock?new Date(`${form.expected_date}T${form.expected_clock}:00+08:00`).toISOString():null,expected_time_note:[form.expected_date&&!form.expected_clock?form.expected_date:'',form.expected_time_note].filter(Boolean).join(' '),internal_note:form.internal_note||'',mark_confirmed:!!form.mark_confirmed,items:form.items,contact_name:form.contact_name||'',contact_phone:form.contact_phone||'',delivery_address:form.delivery_address||'',
    });}finally{commit({locked:!!pending(tenant,'merchant-record')});}
    if(!this.alive||view!==this.view||epoch!==auth().generation)return;clearDraft(tenant,'merchant-record');finishMutation(tenant,'merchant-record');this.restore();
    commit({lastId:row.id,notice:'已保存这条需求。原文保留，未按姓名或电话关联顾客账号。',locked:false,kind:'reservation',status:'',page:1});
    try{const rows=await this.fetchRows();const counts=await this.fetchCounts();commit({counts,records:rows.items.map(x=>({...x,label:labels[x.status]||x.status,time:timeText(x.created_at)})),total:rows.total});}
    catch{commit({error:'已保存，但列表刷新失败，请手动刷新。'});}
  });},
  filter(event:WechatMiniprogram.TouchEvent){if(this.data.busy)return;this.setData({kind:event.currentTarget.dataset.kind==='inquiry'?'inquiry':'reservation',status:String(event.currentTarget.dataset.status||''),page:1});void this.load();},
  previous(){if(this.data.busy||this.data.page<=1)return;this.setData({page:this.data.page-1});void this.load();},next(){if(this.data.busy||this.data.page*20>=this.data.total)return;this.setData({page:this.data.page+1});void this.load();},
  open(event:WechatMiniprogram.TouchEvent){route('merchantdetail',this.data.tenantId,`&kind=${this.data.kind}&record_id=${requireId(event.currentTarget.dataset.id)}`);},
  latest(){if(this.data.lastId)route('merchantdetail',this.data.tenantId,`&kind=reservation&record_id=${this.data.lastId}`);},
  catalog(){route('catalog',this.data.tenantId);},settings(){route('shopsettings',this.data.tenantId);},store(){route('store',this.data.tenantId);},home(){wx.navigateTo({url:'/pages/index/index'});},
});
