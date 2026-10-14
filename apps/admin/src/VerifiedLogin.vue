<script setup lang="ts">
import {onUnmounted,ref} from 'vue';
import {ApiError,request} from './api';
const emit=defineEmits<{session:[string]}>();
const busy=ref(false),code=ref(''),secret=ref(''),error=ref('');let alive=true;
async function begin(){if(busy.value)return;busy.value=true;error.value='';try{const value=await request<{code:string;secret:string}>('/api/v1/auth/browser-approvals','','POST');if(alive){code.value=value.code;secret.value=value.secret;}}catch(e){if(alive)error.value=e instanceof ApiError&&e.code==='WECHAT_LOGIN_NOT_CONFIGURED'?'本项目正式登录尚未配置，请等待微信接入；不会切换成演示账号。':'暂时无法发起登录，请稍后再试。';}finally{if(alive)busy.value=false;}}
async function poll(){if(busy.value||!secret.value)return;busy.value=true;error.value='';try{const result=await request<{status:string;access_token?:string}>('/api/v1/auth/browser-approvals/poll','','POST',{secret:secret.value});if(!alive)return;if(result.status==='APPROVED'&&result.access_token){secret.value='';code.value='';emit('session',result.access_token);}else error.value='尚未收到本人确认，请在本项目小程序登录后明确确认。';}catch(e){if(alive){error.value=e instanceof ApiError&&e.status===401?'本次登录已过期或已使用，请重新发起。':'暂时无法核对，请稍后再试。';if(e instanceof ApiError&&e.status===401){secret.value='';code.value='';}}}finally{if(alive)busy.value=false;}}
onUnmounted(()=>{alive=false;secret.value='';code.value='';});
</script>
<template><section aria-label="正式工作台登录"><h2>使用本项目微信账号登录</h2><p>小程序中明确确认后，网页使用该账号已有的商户或平台权限。确认码三分钟失效，不会生成二维码或自动授予管理员。</p><button :disabled="busy" @click="begin">发起工作台登录</button><template v-if="code"><p>本次确认码：<strong>{{code}}</strong></p><p>在本项目小程序入口的「确认自己的Web工作台登录」输入此码。不要把他人发来的码交给自己的账号确认。</p><button :disabled="busy" @click="poll">我已在小程序确认，核对状态</button></template><p role="alert" v-if="error">{{error}}</p></section></template>
