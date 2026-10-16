<script setup lang="ts">
import {onMounted,onUnmounted,ref} from 'vue';
import {request} from './api';
import {errorMessage} from './workbench';
const props=defineProps<{token:string;tenantId:string}>();
const emit=defineEmits<{unread:[number]}>();
type Notice={event_key:string;kind:'reservation'|'inquiry';record_id:string;title:string;event_status:string;created_at:string;read_at:string|null};
type Feed={items:Notice[];total:number;unread:number;page:number;limit:number;notice:string};
const root=`/api/v1/merchant/tenants/${props.tenantId}`,feed=ref<Feed|null>(null),page=ref(1),busy=ref(false),error=ref(''),detail=ref<{raw_text:string;status:string}|null>(null);
let alive=true,generation=0,timer:ReturnType<typeof setTimeout>|undefined,delay=60000;
async function read(current:number){const value=await request<Feed>(root+`/updates?page=${page.value}`,props.token);if(alive&&current===generation){feed.value=value;emit('unread',value.unread);delay=60000;}}
function schedule(){if(timer)clearTimeout(timer);if(alive&&!document.hidden)timer=setTimeout(()=>void load(),delay);}
async function action(fn:(version:number)=>Promise<void>){if(busy.value||!alive||document.hidden)return;busy.value=true;error.value='';const current=++generation;try{await fn(current);}catch(e){if(alive&&current===generation){error.value=errorMessage(e);delay=Math.min(delay*2,300000);}}finally{if(alive){busy.value=false;schedule();}}}
function load(){return action(read);}
function mark(keys:string[]){if(!keys.length)return;return action(async version=>{await request(root+'/updates/read',props.token,'POST',{event_keys:keys});await read(version);});}
function open(row:Notice){return action(async version=>{const path=row.kind==='inquiry'?'inquiries':'reservations';const value=await request<{raw_text:string;status:string}>(root+`/${path}/${row.record_id}`,props.token);if(alive&&version===generation)detail.value=value;});}
onMounted(()=>void load());onUnmounted(()=>{alive=false;generation++;if(timer)clearTimeout(timer);feed.value=null;detail.value=null;});
</script>
<template><section aria-label="站内更新" :aria-busy="busy"><h2>站内更新</h2><p>仅页面可见时有界刷新，失败退避；关闭页面后不承诺轮询或响铃。微信/短信/邮件外部提醒未配置。</p><p v-if="error" role="alert" class="error">{{error}}</p><template v-if="feed"><p>本站内未读 {{feed.unread}} · 更新记录 {{feed.total}}</p><p>{{feed.notice}} 待处理数量仍在「记单与待办」查看。</p><button :disabled="busy||!feed.items.some(x=>!x.read_at)" @click="mark(feed.items.filter(x=>!x.read_at).map(x=>x.event_key))">仅将当前页未读标为已读</button><article v-for="item in feed.items" :key="item.event_key"><h3>{{item.read_at?'已读':'未读'}} · {{item.title}}</h3><p>{{item.created_at}} · 当次状态 {{item.event_status}}</p><button :disabled="busy" @click="open(item)">重新鉴权打开记录</button><button :disabled="busy||!!item.read_at" @click="mark([item.event_key])">这条已查看</button></article><button :disabled="busy||page===1" @click="page--;load()">上一页更新</button><button :disabled="busy||page*50>=feed.total" @click="page++;load()">下一页更新</button></template><button :disabled="busy" @click="load">刷新站内更新</button><article v-if="detail" aria-label="更新关联记录"><p>当前状态 {{detail.status}}</p><p class="raw">{{detail.raw_text}}</p><p>处理需求请使用原工作台；看过本条不会确认、取消或完成业务，也不会标记顾客已读。</p><button @click="detail=null">关闭记录</button></article></section></template>
