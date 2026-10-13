<script setup lang="ts">
import { ref } from 'vue';
import PlatformPanel from './PlatformPanel.vue';
import CatalogPanel from './CatalogPanel.vue';
import { ApiError, request, transitions, type Tenant, type RecordItem, type Store } from './api';
const alias = ref('merchant-a');
const token = ref('');
const userId=ref(''),platformRole=ref(false),platformLocked=ref(false),platformBusy=ref(false);
const tenant = ref<Tenant>();
const members=ref<Tenant[]>([]),catalogLocked=ref(false),catalogBusy=ref(false),activeAlias=ref('');
const store = ref<Store>({name:'',description:'',version:0});
const records = ref<RecordItem[]>([]);
const busy = ref(false);
const sessionVersion=ref(0);
const error = ref('');
const filter = ref('');
const total = ref(0);
const page = ref(1);
const customer = ref('');
const raw = ref('');
const source = ref('MERCHANT_PHONE');
const method = ref('PICKUP');
const detail = ref<{raw_text: string; events: {from_status: string | null; to_status: string; note: string}[]} | null>(null);
const pending = ref<{key: string; body: unknown} | null>(null);
let generation = 0;
const labels: {[key:string]:string} = {PENDING_CONFIRMATION:'待确认',CONFIRMED:'已确认',PREPARING:'备货中',READY:'待取/送',OUT_FOR_DELIVERY:'配送中',COMPLETED:'已完成',CANCELLED:'已取消'};
function base() { return `/api/v1/merchant/tenants/${tenant.value!.id}`; }
function showError(reason: unknown) {
  error.value = reason instanceof ApiError ? `操作未完成：${reason.code}` : '网络结果未确认，请重试原操作';
}
async function load() {
  const current = generation;
  const data = await request<{items: RecordItem[];total:number}>(`${base()}/reservations?page=${page.value}&limit=20${filter.value ? '&status='+filter.value : ''}`,token.value);
  if (current === generation) { records.value = data.items; total.value = data.total; }
}
async function login() {
  if (busy.value || platformBusy.value || catalogBusy.value || ((platformLocked.value || catalogLocked.value || pending.value) && alias.value!==activeAlias.value)) return;
  const savedTenant=tenant.value?.id, savedUser=userId.value;
  busy.value=true;error.value='';
  try {
    // Stage authentication and membership reads before replacing the active context.
    // A failed same-user refresh must not lose an unresolved request or its tenant.
    const session=await request<{access_token:string}>('/api/v1/dev/session','','POST',{identity:alias.value});
    const nextUser=(await request<{user_id:string}>('/api/v1/dev/me',session.access_token)).user_id;
    if((pending.value||platformLocked.value||catalogLocked.value)&&nextUser!==savedUser)throw new Error('Pending identity changed');
    let isPlatform=false;
    try {isPlatform=(await request<{role:string}>('/api/v1/platform/me',session.access_token)).role==='PLATFORM_ADMIN';}
    catch(e){if(!(e instanceof ApiError&&e.status===403))throw e;}
    const nextMembers=isPlatform?[]:(await request<{items:Tenant[]}>('/api/v1/merchant/tenants',session.access_token)).items;
    const nextTenant=nextMembers.find(x=>x.id===savedTenant)||nextMembers[0];
    if(!isPlatform&&!nextTenant)throw new Error('No tenant');
    if(pending.value&&nextTenant?.id!==savedTenant)throw new Error('Pending tenant unavailable');
    generation++;sessionVersion.value++;token.value=session.access_token;userId.value=nextUser;activeAlias.value=alias.value;
    platformRole.value=isPlatform;members.value=nextMembers;tenant.value=nextTenant;
    records.value=[];detail.value=null;store.value={name:'',description:'',version:0};page.value=1;filter.value='';
    if(!pending.value){customer.value='';raw.value='';}
    if(isPlatform)return;
    try {store.value=await request<Store>(`${base()}/store`,token.value);}
    catch(e){if(!(e instanceof ApiError&&e.status===404))throw e;}
    await load();
  }catch(e){showError(e);}finally{busy.value=false;}
}
async function chooseTenant(event:Event){
  if(busy.value||catalogBusy.value||catalogLocked.value||pending.value)return;
  const chosen=members.value.find(x=>x.id===(event.target as HTMLSelectElement).value);if(!chosen)return;
  tenant.value=chosen;records.value=[];detail.value=null;store.value={name:'',description:'',version:0};page.value=1;filter.value='';busy.value=true;error.value='';
  try{try{store.value=await request<Store>(`${base()}/store`,token.value);}catch(e){if(!(e instanceof ApiError&&e.status===404))throw e;}await load();}catch(e){showError(e);}finally{busy.value=false;}
}
async function saveStore() {
  if(busy.value) return;busy.value=true;error.value='';
  try {store.value=await request<Store>(`${base()}/store`,token.value,'PUT',{name:store.value.name,description:store.value.description,expected_version:store.value.version});}
  catch(e){showError(e);}finally{busy.value=false;}
}
async function submit() {
  if (busy.value) return;
  if (!pending.value) pending.value={key:crypto.randomUUID(),body:{customer_label:customer.value,raw_text:raw.value,source:source.value,fulfillment_method:method.value}};
  busy.value=true;error.value='';
  try {
    await request(`${base()}/reservations`,token.value,'POST',pending.value.body,pending.value.key);
    pending.value=null;customer.value='';raw.value='';filter.value='';page.value=1;await load();
  } catch(e) { if(e instanceof ApiError && e.status>=400 && e.status<500 && ![401,403,408,429].includes(e.status)) pending.value=null;showError(e); }
  finally{busy.value=false;}
}
async function transition(record:RecordItem,target:string) {
  if(busy.value)return;busy.value=true;error.value='';
  try {await request(`${base()}/reservations/${record.id}/transitions`,token.value,'POST',{target_status:target,expected_version:record.version},`${record.id}.${record.version}.${target}`);await load();}
  catch(e){showError(e);await load().catch(()=>{});}finally{busy.value=false;}
}
async function open(record:RecordItem) {
  if(busy.value)return;busy.value=true;error.value='';
  try{detail.value=await request(`${base()}/reservations/${record.id}`,token.value);}catch(e){showError(e);}finally{busy.value=false;}
}
async function refresh(nextPage=1) {
  if(busy.value)return;busy.value=true;error.value='';page.value=nextPage;detail.value=null;
  try{await load();}catch(e){showError(e);}finally{busy.value=false;}
}
</script>
<template>
  <main>
    <header><span>local-shop · 开发验证工作台</span><h1>记下需求，安排备货</h1><p>仅供本机合成账号测试，尚未接入微信真实登录。</p></header>
    <section class="login"><label>演示身份<select v-model="alias" :disabled="busy || !!pending || platformLocked || platformBusy || catalogLocked || catalogBusy"><option value="merchant-a">商户 A</option><option value="merchant-b">商户 B</option><option value="customer-a">受邀账号 A</option><option value="customer-b">受邀账号 B</option><option value="platform-admin">平台合成管理员</option></select></label><button :disabled="busy || platformBusy || catalogBusy" @click="login">{{(platformLocked||catalogLocked||pending)?'重新登录同一身份，保留原请求':'进入工作台'}}</button></section>
    <p v-if="error" role="alert" class="error">{{error}}</p>
    <PlatformPanel v-if="platformRole && userId && token" :key="userId+sessionVersion" :token="token" :user-id="userId" @locked="platformLocked=$event" @busy="platformBusy=$event" />
    <template v-if="tenant">
      <h2>{{tenant.name}}</h2><label v-if="members.length>1">当前已授权店铺<select :value="tenant.id" :disabled="busy || catalogBusy || catalogLocked || !!pending" @change="chooseTenant"><option v-for="member in members" :key="member.id" :value="member.id">{{member.name}}</option></select></label>
      <CatalogPanel v-if="userId && token" :key="userId+'.'+tenant.id+'.'+sessionVersion" :token="token" :user-id="userId" :tenant-id="tenant.id" @locked="catalogLocked=$event" @busy="catalogBusy=$event" />
      <section><h3>店铺资料</h3><label>店名<input v-model="store.name" :disabled="busy" maxlength="100"></label><button :disabled="busy || !store.name.trim()" @click="saveStore">保存店铺</button></section>
      <section><h3>快速代记</h3><p>没有商品库也能直接保存。</p>
        <form @submit.prevent="submit"><fieldset :disabled="busy || !!pending || platformLocked || platformBusy || catalogLocked || catalogBusy">
          <label>顾客称呼<input v-model="customer" required maxlength="100"></label>
          <label>原始需求<textarea v-model="raw" required maxlength="4000" placeholder="例如：半斤干贝分两袋，周三下午自提"></textarea></label>
          <div class="row"><label>来源<select v-model="source"><option value="MERCHANT_PHONE">电话</option><option value="MERCHANT_WECHAT">微信</option><option value="MERCHANT_IN_STORE">到店</option></select></label><label>交付意向<select v-model="method"><option value="PICKUP">自提</option><option value="DELIVERY">商家配送</option></select></label></div>
        </fieldset><p v-if="pending">正在确认原提交结果，重试会使用同一编号，避免重复记单。</p><button :disabled="busy || (!pending && (!customer.trim() || !raw.trim()))">{{pending ? '重试原提交' : '保存需求'}}</button></form>
      </section>
      <section><div class="row"><h3>待办与历史（{{total}}）</h3><label>状态<select v-model="filter" :disabled="busy" @change="refresh()"><option value="">全部</option><option v-for="(label,status) in labels" :key="status" :value="status">{{label}}</option></select></label><button :disabled="busy" @click="refresh(page)">刷新</button></div>
        <p v-if="!records.length">当前没有记录</p>
        <article v-for="record in records" :key="record.id"><div class="row"><strong>{{record.customer_label}}</strong><span class="badge">{{labels[record.status]}}</span></div><p class="raw">{{record.raw_text}}</p><small>{{record.fulfillment_method==='PICKUP'?'自提':'配送'}} · 版本 {{record.version}}</small><div class="actions"><button class="secondary" :disabled="busy" @click="open(record)">查看历史</button><button v-for="target in transitions(record)" :key="target" :disabled="busy" @click="transition(record,target)">{{labels[target]}}</button></div></article>
        <div class="row"><button :disabled="busy || page<=1" @click="refresh(page-1)">上一页</button><span>第 {{page}} 页</span><button :disabled="busy || page*20>=total" @click="refresh(page+1)">下一页</button></div>
      </section>
      <section v-if="detail" aria-label="处理历史"><button class="secondary" @click="detail=null">关闭历史</button><h3>原始需求与处理历史</h3><p class="raw">{{detail.raw_text}}</p><ol><li v-for="(event,index) in detail.events" :key="index">{{labels[event.to_status]}}<span v-if="event.note">：{{event.note}}</span></li></ol></section>
    </template>
  </main>
</template>
<style>
:root{font-family:system-ui,sans-serif;color:#213b36;background:#f4f3ee}*{box-sizing:border-box}body{margin:0}main{max-width:850px;margin:auto;padding:28px 18px 60px}header{padding:24px 0}h1{font-size:32px;line-height:1.4}h2,h3{margin:8px 0 16px}p{line-height:1.7}section{background:white;border:1px solid #dbe4df;border-radius:14px;padding:22px;margin:18px 0}.row,.login,.actions{display:flex;align-items:center;gap:12px;flex-wrap:wrap}label{display:grid;gap:7px;margin-bottom:12px;flex:1}input,select,textarea{font:inherit;padding:12px;border:1px solid #aebfb5;border-radius:8px;width:100%;background:white}textarea{min-height:100px}button{font:inherit;border:0;border-radius:8px;padding:12px 16px;background:#216653;color:white;cursor:pointer}button:disabled{opacity:.5;cursor:default}.secondary{background:#e5ede8;color:#264d40}fieldset{border:0;padding:0;margin:0}.error{padding:16px;color:#8e281f;background:#ffede8;border-radius:10px}.badge{margin-left:auto;padding:6px 10px;background:#edf3df;border-radius:8px}.raw{white-space:pre-wrap;overflow-wrap:anywhere}article{border-top:1px solid #e2e8e3;padding:20px 0}.actions{margin-top:14px}small{color:#5e7169}li{padding:8px 0}@media(max-width:500px){h1{font-size:26px}section{padding:16px}.actions button{flex:1}}
</style>
