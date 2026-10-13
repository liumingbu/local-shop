<script setup lang="ts">
import { onMounted,onUnmounted,reactive,ref,watch } from 'vue';
import { request } from './api';
import { PlatformConsole,platformState,type Invitation,type PlatformTenant } from './platform';
const props=defineProps<{token:string;userId:string}>();
const emit=defineEmits<{locked:[value:boolean];busy:[value:boolean]}>();
const state=reactive(platformState()),owner=ref(''),name=ref(''),reason=ref(''),reviewReason=ref(''),statusReason=ref('');
const storage={getItem:(key:string)=>localStorage.getItem(key),setItem:(key:string,value:string)=>localStorage.setItem(key,value)};
const sessionToken=props.token;
const controller=new PlatformConsole(state,(path,method,body,key)=>request(path,sessionToken,method,body,key),storage,props.userId);
const labels:Record<string,string>={INVITED:'待收件人回应',ACCEPTED:'已接受，待审核',DECLINED:'已谢绝',APPROVED:'已批准',REJECTED:'已拒绝',ACTIVE:'启用',SUSPENDED:'暂停'};
watch(()=>state.locked,value=>emit('locked',value),{immediate:true});
watch(()=>state.busy,value=>emit('busy',value),{immediate:true});
onMounted(()=>controller.load());onUnmounted(()=>{controller.dispose();emit('locked',false);emit('busy',false);});
function review(row:Invitation,decision:'APPROVED'|'REJECTED'){return controller.review(row,decision,reviewReason.value);}
function status(row:PlatformTenant,value:'ACTIVE'|'SUSPENDED'){return controller.status(row,value,statusReason.value);}
</script>
<template>
<section aria-label="平台管理"><h2>受邀商户管理</h2><p>仅使用合成试用资料。平台角色不提供各店客户记录或私图访问。</p>
<p v-if="state.error" role="alert" class="error">操作未完成：{{state.error}}。版本冲突请刷新；存储故障请先核对原操作，不要重复新建。</p><p v-if="state.notice">{{state.notice}}</p>
<p v-if="state.locked">原请求结果待确认：{{state.pendingPath}}。编辑和切换身份已锁定。</p><button v-if="state.locked" :disabled="state.busy || !state.ready" @click="controller.retry()">重试原命令</button>
<button :disabled="state.busy" @click="controller.load()">重新读取服务端</button>
<template v-if="state.ready"><section><h3>定向邀请已有账号</h3><form @submit.prevent="controller.invite(owner,name,reason)"><fieldset :disabled="state.busy || state.locked">
<label>收件人账号UUID<input v-model="owner" maxlength="36" required placeholder="由收件人在小程序本人邀请页查看，不填姓名或电话"></label><label>拟用店名<input v-model="name" maxlength="100" required></label><label>邀请原因<textarea v-model="reason" maxlength="500" required placeholder="仅简要审核记录，不填写凭据或证件原文"></textarea></label><button>创建邀请</button></fieldset></form></section>
<section><h3>邀请与审核（{{state.invitationTotal}}）</h3><label>本次审核理由<input v-model="reviewReason" maxlength="500" :disabled="state.busy || state.locked"></label>
<article v-for="row in state.invitations" :key="row.id"><strong>{{row.proposed_name}}</strong><p>{{labels[row.status]}} · 版本{{row.version}}</p><p>收件账号：{{row.owner_user_id}}</p>
<div class="actions"><button :disabled="state.busy || state.locked || row.status!=='ACCEPTED' || !reviewReason.trim()" @click="review(row,'APPROVED')">明确批准（仍不公开店铺）</button><button :disabled="state.busy || state.locked || !['INVITED','ACCEPTED'].includes(row.status) || !reviewReason.trim()" @click="review(row,'REJECTED')">拒绝</button></div></article>
<div class="row"><button :disabled="state.busy || state.invitationPage<=1" @click="controller.changePage('invitation',state.invitationPage-1)">上一页</button><span>第{{state.invitationPage}}页</span><button :disabled="state.busy || state.invitationPage*20>=state.invitationTotal" @click="controller.changePage('invitation',state.invitationPage+1)">下一页</button></div></section>
<section><h3>商户启停（{{state.tenantTotal}}）</h3><p>暂停隐藏公开店铺并拒绝商户读写，顾客仍可查看本人历史。不会删除已有记录。</p><label>本次启停理由<input v-model="statusReason" maxlength="500" :disabled="state.busy || state.locked"></label>
<article v-for="row in state.tenants" :key="row.id"><strong>{{row.display_name}}</strong><p>{{labels[row.status]}} · 版本{{row.version}}</p><button :disabled="state.busy || state.locked || !statusReason.trim()" @click="status(row,row.status==='ACTIVE'?'SUSPENDED':'ACTIVE')">{{row.status==='ACTIVE'?'明确暂停商户':'恢复启用'}}</button></article>
<div class="row"><button :disabled="state.busy || state.tenantPage<=1" @click="controller.changePage('tenant',state.tenantPage-1)">上一页</button><span>第{{state.tenantPage}}页</span><button :disabled="state.busy || state.tenantPage*20>=state.tenantTotal" @click="controller.changePage('tenant',state.tenantPage+1)">下一页</button></div></section>
<section><h3>操作审计（{{state.auditTotal}}）</h3><article v-for="row in state.audit" :key="row.id"><strong>{{row.action}}</strong><p>{{row.before_status || '创建'}} → {{row.after_status}} · {{row.created_at}}</p><p>{{row.reason}}</p><small>操作者账号：{{row.actor_id}}</small></article>
<div class="row"><button :disabled="state.busy || state.auditPage<=1" @click="controller.changePage('audit',state.auditPage-1)">上一页</button><span>第{{state.auditPage}}页</span><button :disabled="state.busy || state.auditPage*20>=state.auditTotal" @click="controller.changePage('audit',state.auditPage+1)">下一页</button></div></section>
</template></section>
</template>
