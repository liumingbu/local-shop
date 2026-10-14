<script setup lang="ts">
import { computed,onMounted,onUnmounted,ref,watch } from 'vue';
import { ApiError,request,transitions,type RecordItem,type Store } from './api';
import { WorkbenchDraft,emptyDraft,errorMessage,type Command } from './workbench';
const props=defineProps<{token:string;userId:string;tenantId:string;role:string}>();
const emit=defineEmits<{locked:[boolean];busy:[boolean]}>();
const root=`/api/v1/merchant/tenants/${props.tenantId}`;
const draftStore=new WorkbenchDraft({getItem:k=>localStorage.getItem(k),setItem:(k,v)=>localStorage.setItem(k,v)},props.userId,props.tenantId);
const draft=ref(emptyDraft()),pending=ref<Command|null>(null),ready=ref(false),busy=ref(false),error=ref(''),notice=ref('');
const store=ref<Store>({name:'',description:'',version:0}),rows=ref<RecordItem[]>([]),total=ref(0),page=ref(1),filter=ref('');
const detail=ref<RecordItem|null>(null),agreed=ref(false),note=ref(''),summary=ref(''),changeReason=ref(''),timeNote=ref('');
const labels:Record<string,string>={PENDING_CONFIRMATION:'待确认',CONFIRMED:'已确认',PREPARING:'备货中',READY:'待取/送',OUT_FOR_DELIVERY:'配送中',COMPLETED:'已完成',CANCELLED:'已取消'};
let alive=true,epoch=0;
const latest=computed(()=>detail.value?.confirmation_revisions?.at(-1));
watch(busy,x=>emit('busy',x),{immediate:true});watch(pending,x=>emit('locked',!!x),{immediate:true});
watch(draft,()=>{if(ready.value){try{draftStore.save(draft.value,pending.value);}catch(e){error.value=errorMessage(e);}}},{deep:true,flush:'sync'});
function safe(){return alive&&!document.hidden;}
async function run(action:()=>Promise<void>){if(busy.value||!safe())return;busy.value=true;error.value='';try{await action();}catch(e){if(safe())error.value=errorMessage(e);}finally{if(alive)busy.value=false;}}
async function list(){const own=epoch;const data=await request<{items:RecordItem[];total:number}>(`${root}/reservations?page=${page.value}&limit=20${filter.value?'&status='+filter.value:''}`,props.token);if(safe()&&own===epoch){rows.value=data.items;total.value=data.total;}}
async function storeRead(){const own=epoch;try{const value=await request<Store>(root+'/store',props.token);if(safe()&&own===epoch)store.value=value;}catch(e){if(!(e instanceof ApiError&&e.status===404))throw e;}}
function load(){return run(async()=>{ready.value=false;const saved=draftStore.read();draft.value=saved.draft;pending.value=saved.pending;ready.value=true;await storeRead();await list();});}
function refresh(next=1){if(busy.value)return;page.value=next;detail.value=null;agreed.value=false;return run(list);}
function open(row:RecordItem){return run(async()=>{const own=epoch;detail.value=null;agreed.value=false;note.value='';summary.value='';changeReason.value='';timeNote.value='';const result=await request<RecordItem>(`${root}/reservations/${row.id}`,props.token);if(safe()&&own===epoch)detail.value=result;});}
function close(){detail.value=null;agreed.value=false;note.value='';}
async function send(command:Command){
 const own=epoch;
 try{
  await request(command.path,props.token,'POST',command.body,command.key);
  if(!alive)return;
  // Persist clearing before unlocking; a storage failure retains the old same-key request.
  const next=command.path===draftStore.root?emptyDraft():draftStore.read().draft;
  draftStore.save(next,null);ready.value=false;draft.value=next;pending.value=null;ready.value=true;
  if(safe()&&own===epoch){notice.value='已保存。可刷新列表核对最新处理结果。';close();page.value=1;try{await list();}catch{error.value='已保存，但列表刷新失败，请手动刷新；无需再次提交。';}}
 }catch(e){
  if(e instanceof ApiError&&e.status>=400&&e.status<500&&![401,403,408,429].includes(e.status)){
   draftStore.save(draft.value,null);pending.value=null;
  }
  throw e;
 }
}
function command(path:string,body:unknown){return run(async()=>{if(!ready.value||pending.value)return;const value={path,body,key:crypto.randomUUID()};draftStore.save(draft.value,value);pending.value=value;await send(value);});}
function create(){if(!draft.value.customer_label.trim()||!draft.value.raw_text.trim())return;return command(draftStore.root,{...draft.value});}
function retry(){return run(async()=>{if(pending.value)await send(pending.value);});}
function transition(row:RecordItem,target:string){
 if(pending.value)return;
 const revision=row.confirmation_revisions?.at(-1);
 if(target==='CONFIRMED'&&revision&&(!detail.value||detail.value.id!==row.id||!agreed.value)){error.value='请先查看详情，核对最新确认内容并勾选已与顾客确认。';return;}
 return command(`${draftStore.root}/${row.id}/transitions`,{target_status:target,expected_version:row.version,note:note.value,visible_to_customer:false,...(target==='CONFIRMED'&&revision?{confirmation_revision_id:revision.id,customer_agreed:true}:{})});
}
function propose(){if(!detail.value||!summary.value.trim()||!changeReason.value.trim())return;return command(`${draftStore.root}/${detail.value.id}/confirmation-revisions`,{expected_version:detail.value.version,summary:summary.value,change_reason:changeReason.value,time_note:timeNote.value,items:[]});}
function saveStore(){return run(async()=>{const own=epoch;const value=store.value;const response=await request<Store>(root+'/store',props.token,'PUT',{name:value.name,description:value.description,expected_version:value.version,public_contact:value.public_contact||'',public_address:value.public_address||'',business_hours:value.business_hours||'',delivery_note:value.delivery_note||'',allow_pickup:!!value.allow_pickup,allow_delivery:!!value.allow_delivery,published:!!value.published});if(safe()&&own===epoch){store.value=response;notice.value='店铺资料已保存，Logo关联保持不变。';}});}
function visibility(){epoch++;if(document.hidden){rows.value=[];detail.value=null;ready.value=false;draft.value=emptyDraft();store.value={name:'',description:'',version:0};}else if(!busy.value)void load();}
onMounted(()=>{document.addEventListener('visibilitychange',visibility);void load();});
onUnmounted(()=>{alive=false;epoch++;document.removeEventListener('visibilitychange',visibility);emit('locked',false);emit('busy',false);});
</script>
<template><div aria-label="商户日常工作台" :aria-busy="busy">
<p class="error" role="alert" v-if="error">{{error}}</p><p class="notice" role="status" v-if="notice">{{notice}}</p>
<p v-if="!ready&&!busy">工作台资料未就绪。<button @click="load">重新读取</button></p>
<section aria-label="快速代记"><h2>快速代记</h2><p>没有商品库也能先记下来。草稿仅保存在当前设备，按账号和店铺分别保存。</p>
<form @submit.prevent="create"><fieldset :disabled="busy||!!pending||!ready">
<label>顾客称呼<input v-model="draft.customer_label" required maxlength="100" placeholder="例如：陈阿姨，不自动关联顾客账号"></label>
<label>原始需求<textarea v-model="draft.raw_text" required maxlength="4000" placeholder="例如：半斤干贝分两袋，周三下午自提"></textarea></label>
<div class="row"><label>来源<select v-model="draft.source"><option value="MERCHANT_PHONE">电话</option><option value="MERCHANT_WECHAT">微信</option><option value="MERCHANT_IN_STORE">到店</option></select></label><label>交付意向<select v-model="draft.fulfillment_method"><option value="PICKUP">自提</option><option value="DELIVERY">商家配送</option></select></label></div>
<label>期望日期或时段<input v-model="draft.expected_time_note" maxlength="200" placeholder="保留顾客原话，不自动当成交付承诺"></label>
<label>内部备注（顾客不可见）<textarea v-model="draft.internal_note" maxlength="2000"></textarea></label>
<label class="check"><input type="checkbox" v-model="draft.mark_confirmed">已通过电话等方式明确确认这条需求</label>
<button :disabled="!draft.customer_label.trim()||!draft.raw_text.trim()">保存需求</button></fieldset></form>
<p class="notice" v-if="pending">原操作结果待确认，暂不修改原内容。刷新页面并登录同一账号和店铺后仍可恢复。</p><button v-if="pending" :disabled="busy||!ready" @click="retry">重试原提交</button>
</section>
<section aria-label="待办与历史"><div class="row"><h2>待办与历史（{{total}}）</h2><label>状态<select v-model="filter" :disabled="busy" @change="refresh()"><option value="">全部</option><option v-for="(label,status) in labels" :key="status" :value="status">{{label}}</option></select></label><button :disabled="busy||!ready" @click="refresh(page)">刷新待办</button></div>
<p class="empty" v-if="!rows.length&&!busy&&!error">当前筛选没有记录。可以先用上面的快速代记保存第一条需求。</p>
<article v-for="row in rows" :key="row.id"><div class="row"><strong>{{row.customer_label}}</strong><span class="badge">{{labels[row.status]}}</span></div><p class="raw">{{row.raw_text}}</p><small>{{row.fulfillment_method==='PICKUP'?'自提':'配送'}} · 版本 {{row.version}}</small>
<div class="actions"><button class="secondary" :disabled="busy" @click="open(row)">查看详情与历史</button><button v-for="target in transitions(row)" :key="target" :disabled="busy||!!pending" @click="transition(row,target)">{{labels[target]}}</button></div></article>
<div class="row"><button :disabled="busy||page<=1" @click="refresh(page-1)">上一页</button><span>第 {{page}} 页</span><button :disabled="busy||page*20>=total" @click="refresh(page+1)">下一页</button></div></section>
<section v-if="detail" aria-label="处理详情"><button class="secondary" @click="close">关闭详情</button><h2>{{detail.customer_label}} · {{labels[detail.status]}}</h2><h3>原始需求（保留不改）</h3><p class="raw">{{detail.raw_text}}</p><p>顾客期望：{{detail.expected_time_note||'未填写'}}</p><p v-if="detail.internal_note" class="notice">内部备注（顾客不可见）：{{detail.internal_note}}</p>
<ul v-if="detail.items?.length"><li v-for="(item,i) in detail.items" :key="i">{{item.name}} · {{item.quantity}} {{item.unit}} · {{item.spec}}</li></ul>
<template v-if="latest"><h3>最新确认候选</h3><p class="raw">{{latest.details.summary}}</p><p>{{latest.details.time_note||'未填写确认时间备注'}}</p><label v-if="detail.status==='PENDING_CONFIRMATION'" class="check"><input type="checkbox" v-model="agreed" :disabled="busy||!!pending">已与顾客核对并确认以上最新内容</label></template>
<label>本次内部处理备注<input v-model="note" maxlength="500" :disabled="busy||!!pending"></label><div class="actions"><button v-for="target in transitions(detail)" :key="target" :disabled="busy||!!pending" @click="transition(detail!,target)">{{labels[target]}}</button></div>
<details v-if="['PENDING_CONFIRMATION','CONFIRMED'].includes(detail.status)"><summary>补充确认内容（保留原文，需重新确认）</summary><form @submit.prevent="propose"><fieldset :disabled="busy||!!pending"><label>确认内容<textarea v-model="summary" maxlength="4000" required></textarea></label><label>变更原因<input v-model="changeReason" maxlength="500" required></label><label>确认时间备注<input v-model="timeNote" maxlength="200" placeholder="仅备注，不生成精确截止时间"></label><button>保存待确认候选</button></fieldset></form></details>
<h3>处理历史</h3><ol><li v-for="(event,i) in detail.events" :key="i">{{labels[event.to_status]||event.action}}<span v-if="event.note">：{{event.note}}</span></li></ol></section>
<details class="store-settings"><summary>店铺资料与公开设置</summary><section><p>只有店主可保存；此处不会移除已关联的Logo。</p><button class="secondary" :disabled="busy||!ready" @click="run(storeRead)">重新读取店铺（放弃未保存修改）</button><form @submit.prevent="saveStore"><fieldset :disabled="busy||!!pending||role!=='OWNER'||!ready"><label>店名<input v-model="store.name" maxlength="100" required></label><label>店铺介绍<textarea v-model="store.description" maxlength="2000"></textarea></label><label>公开联系电话<input v-model="store.public_contact" maxlength="200"></label><label>公开地址<input v-model="store.public_address" maxlength="300"></label><label>营业时间<input v-model="store.business_hours" maxlength="200"></label><label>交付说明<textarea v-model="store.delivery_note" maxlength="500"></textarea></label><label class="check"><input type="checkbox" v-model="store.allow_pickup">允许自提</label><label class="check"><input type="checkbox" v-model="store.allow_delivery">允许商家配送</label><label class="check"><input type="checkbox" v-model="store.published">公开店铺资料与已发布商品</label><button :disabled="!store.name.trim()">保存店铺</button></fieldset></form></section></details>
<p class="muted">没有已验证的微信消息通知，请主动查看待办。这里只记录备货与交付，不涉及支付结算。</p>
</div></template>
