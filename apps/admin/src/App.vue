<script setup lang="ts">
import {computed,onMounted,onUnmounted,ref} from 'vue';
import PlatformPanel from './PlatformPanel.vue';
import CatalogPanel from './CatalogPanel.vue';
import WorkbenchPanel from './WorkbenchPanel.vue';
import {ApiError,request,type Tenant} from './api';
import {errorMessage} from './workbench';
const development=computed(()=>import.meta.env.DEV&&import.meta.env.VITE_ENABLE_DEVELOPMENT_LOGIN==='true'&&['127.0.0.1','localhost'].includes(location.hostname));
const alias=ref('merchant-a'),token=ref(''),userId=ref(''),activeAlias=ref(''),platformRole=ref(false),tenantId=ref(''),members=ref<Tenant[]>([]);
const busy=ref(false),error=ref(''),notice=ref(''),tab=ref('workbench'),sessionVersion=ref(0),concealed=ref(document.hidden);
const platformBusy=ref(false),catalogBusy=ref(false),workbenchBusy=ref(false),platformLocked=ref(false),catalogLocked=ref(false),workbenchLocked=ref(false);
const childBusy=computed(()=>platformBusy.value||catalogBusy.value||workbenchBusy.value),locked=computed(()=>platformLocked.value||catalogLocked.value||workbenchLocked.value);
const tenant=computed(()=>members.value.find(x=>x.id===tenantId.value));let alive=true,epoch=0;
async function login(){
 if(!development.value||busy.value||childBusy.value)return;
 if(locked.value&&alias.value!==activeAlias.value){error.value='原操作待确认，请先重试，或退出后切换账号；原请求按账号保存。';return;}
 const current=epoch;busy.value=true;error.value='';
 try{
  const session=await request<{access_token:string}>('/api/v1/dev/session','','POST',{identity:alias.value});
  const me=await request<{user_id:string}>('/api/v1/dev/me',session.access_token);
  let platform=false;try{platform=(await request<{role:string}>('/api/v1/platform/me',session.access_token)).role==='PLATFORM_ADMIN';}catch(e){if(!(e instanceof ApiError&&e.status===403))throw e;}
  const list=platform?[]:(await request<{items:Tenant[]}>('/api/v1/merchant/tenants',session.access_token)).items;
  if(!alive||current!==epoch)return;
  const previous=userId.value===me.user_id?tenantId.value:'';
  token.value=session.access_token;userId.value=me.user_id;activeAlias.value=alias.value;platformRole.value=platform;members.value=list;tenantId.value=list.find(x=>x.id===previous)?.id||list[0]?.id||'';sessionVersion.value++;tab.value='workbench';
  notice.value=!platform&&!list.length?'当前账号没有已启用的店铺授权。请先由平台邀请并完成审核。':'';
 }catch(e){if(alive&&current===epoch)error.value=errorMessage(e);}finally{if(alive)busy.value=false;}
}
function logout(){epoch++;token.value='';userId.value='';members.value=[];tenantId.value='';platformRole.value=false;error.value='';notice.value='已退出。令牌已清除，未确认请求按账号和店铺保留在本机。';platformBusy.value=catalogBusy.value=workbenchBusy.value=false;platformLocked.value=catalogLocked.value=workbenchLocked.value=false;}
function choose(event:Event){if(busy.value||childBusy.value||locked.value)return;const value=(event.target as HTMLSelectElement).value;if(members.value.some(x=>x.id===value)){tenantId.value=value;sessionVersion.value++;tab.value='workbench';}}
function visibility(){concealed.value=document.hidden;}
onMounted(()=>document.addEventListener('visibilitychange',visibility));onUnmounted(()=>{alive=false;epoch++;document.removeEventListener('visibilitychange',visibility);});
</script>
<template><main>
<header><span>local-shop · 商户工作台</span><h1>记下需求，安排备货</h1><p v-if="development">受控开发模式：只用本机合成账号，不用于实际营业。</p><p v-else>正式登录尚未配置。不会自动使用演示身份；请完成接入后使用。</p></header>
<section v-if="development" class="login" aria-label="开发登录"><label>演示身份<select v-model="alias" :disabled="busy||childBusy||locked"><option value="merchant-a">商户 A</option><option value="merchant-b">商户 B</option><option value="customer-a">受邀账号 A</option><option value="customer-b">受邀账号 B</option><option value="platform-admin">平台合成管理员</option></select></label><button :disabled="busy||childBusy" @click="login">{{token?'重新登录同一身份':'进入工作台'}}</button><button v-if="token" class="secondary" @click="logout">退出登录</button></section>
<p v-if="error" role="alert" class="error">{{error}}</p><p v-if="notice" role="status" class="notice">{{notice}}</p>
<template v-if="token&&userId&&!concealed">
<PlatformPanel v-if="platformRole" :key="userId+sessionVersion" :token="token" :user-id="userId" @busy="platformBusy=$event" @locked="platformLocked=$event"/>
<template v-else-if="tenant"><div class="row"><h2 class="store-title">{{tenant.name}}</h2><label v-if="members.length>1">当前已授权店铺<select :value="tenantId" :disabled="busy||childBusy||locked" @change="choose"><option v-for="member in members" :key="member.id" :value="member.id">{{member.name}}</option></select></label></div>
<nav aria-label="工作台功能" class="actions"><button :aria-pressed="tab==='workbench'" @click="tab='workbench'">记单与待办</button><button :aria-pressed="tab==='catalog'" @click="tab='catalog'">商品维护</button></nav>
<WorkbenchPanel v-show="tab==='workbench'" :key="'workbench'+userId+tenantId+sessionVersion" :token="token" :user-id="userId" :tenant-id="tenantId" :role="tenant.role" :active="tab==='workbench'" @busy="workbenchBusy=$event" @locked="workbenchLocked=$event"/>
<CatalogPanel v-show="tab==='catalog'" :key="'catalog'+userId+tenantId+sessionVersion" :token="token" :user-id="userId" :tenant-id="tenantId" @busy="catalogBusy=$event" @locked="catalogLocked=$event"/>
</template></template>
<p v-if="concealed">页面已隐藏，私有工作台内容已清除；返回后重新读取。</p>
</main></template>
<style>
:root{font-family:system-ui,sans-serif;color:#213b36;background:#f4f3ee}*{box-sizing:border-box}body{margin:0}main{max-width:850px;margin:auto;padding:28px 18px 60px}header{padding:24px 0}h1{font-size:32px;line-height:1.4}h2,h3{margin:8px 0 16px}p{line-height:1.7}section{background:white;border:1px solid #dbe4df;border-radius:14px;padding:22px;margin:18px 0}.row,.login,.actions{display:flex;align-items:center;gap:12px;flex-wrap:wrap}label{display:grid;gap:7px;margin-bottom:12px;flex:1}input,select,textarea{font:inherit;padding:12px;border:1px solid #aebfb5;border-radius:8px;width:100%;background:white}textarea{min-height:100px}button{font:inherit;border:0;border-radius:8px;padding:12px 16px;background:#216653;color:white;cursor:pointer}button:disabled{opacity:.5;cursor:default}.secondary{background:#e5ede8;color:#264d40}fieldset{border:0;padding:0;margin:0}.error{padding:16px;color:#8e281f;background:#ffede8;border-radius:10px}.badge{margin-left:auto;padding:6px 10px;background:#edf3df;border-radius:8px}.raw{white-space:pre-wrap;overflow-wrap:anywhere}article{border-top:1px solid #e2e8e3;padding:20px 0}.actions{margin-top:14px}small{color:#5e7169}li{padding:8px 0}@media(max-width:500px){h1{font-size:26px}section{padding:16px}.actions button{flex:1}}

.notice{padding:14px;background:#fff6dc;color:#66501d;border-radius:8px}.muted,.empty{color:#5e7169}.store-title,strong,h1,h2,h3,summary{overflow-wrap:anywhere;min-width:0}.check{display:flex;align-items:center;gap:8px}.check input{width:auto}.store-settings{margin:22px 0}summary{cursor:pointer;font-weight:600;padding:14px}.row label{min-width:180px}nav button[aria-pressed="false"]{background:#e5ede8;color:#264d40}button:focus-visible,input:focus-visible,textarea:focus-visible,select:focus-visible{outline:3px solid #b48d3f;outline-offset:2px}@media(max-width:500px){main{padding:16px 12px 40px}.row>*{max-width:100%}label{min-width:0}button{min-height:44px}}
</style>
