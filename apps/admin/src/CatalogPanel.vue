<script setup lang="ts">
import { onMounted,onUnmounted,reactive,watch,ref } from 'vue';
import { ApiError,request } from './api';
import {errorMessage} from './workbench';
import { CatalogConsole,catalogState } from './catalog';
const props=defineProps<{token:string;userId:string;tenantId:string}>();const emit=defineEmits<{locked:[value:boolean];busy:[value:boolean]}>();
const state=reactive(catalogState()),token=props.token;
const categoryName=ref(''),categoryBusy=ref(false),categoryPending=ref<{name:string;key:string}|null>(null),categoryError=ref('');
const categorySlot=`local-shop.web.category.v1.${props.userId}.${props.tenantId}`;let alive=true,categoryStorageInvalid=false;
function categoryRestore(){try{const raw=localStorage.getItem(categorySlot);if(!raw||raw==='null')return;const value=JSON.parse(raw);if(typeof value.name!=='string'||!value.name.trim()||value.name.length>100||!/^[-a-zA-Z0-9_.]{8,100}$/.test(value.key))throw Error();categoryPending.value=value;categoryName.value=value.name;}catch{categoryStorageInvalid=true;categoryError.value='本机分类请求记录不可读取，请先核对存储，不要重复创建。';}}
async function createCategory(){if(categoryBusy.value||state.busy||state.locked||categoryStorageInvalid)return;categoryBusy.value=true;categoryError.value='';
 try{if(!categoryPending.value){const value={name:categoryName.value.trim(),key:crypto.randomUUID()};if(!value.name||value.name.length>100)return;localStorage.setItem(categorySlot,JSON.stringify(value));categoryPending.value=value;}
 const command=categoryPending.value;await request(`/api/v1/merchant/tenants/${props.tenantId}/categories`,token,'POST',{name:command.name,sort_order:0,status:'ACTIVE'},command.key);
 if(!alive)return;localStorage.setItem(categorySlot,'null');categoryPending.value=null;categoryName.value='';await controller.refreshCategories();
 }catch(e){if(!alive)return;if(e instanceof ApiError&&e.status>=400&&e.status<500&&![401,403,408,429].includes(e.status)){try{localStorage.setItem(categorySlot,'null');categoryPending.value=null;}catch{}}
 categoryError.value=errorMessage(e);
 }finally{if(alive)categoryBusy.value=false;}}

const controller=new CatalogConsole(state,(path,method,body,key)=>request(path,token,method,body,key),{getItem:key=>localStorage.getItem(key),setItem:(key,value)=>localStorage.setItem(key,value)},props.userId,props.tenantId);
watch(()=>state.locked||!!categoryPending.value,value=>emit('locked',value),{immediate:true});watch(()=>state.busy||categoryBusy.value,value=>emit('busy',value),{immediate:true});
onMounted(()=>{categoryRestore();void controller.load();});onUnmounted(()=>{alive=false;controller.dispose();emit('locked',false);emit('busy',false);});
function stop(){return controller.discardKnownFailure(window.confirm('请先核对成功项。确认保留已保存商品，结束本批并放弃剩余未执行项？不会回滚已保存结果。'));}
</script>
<template><section aria-label="批量商品维护"><h2>商品批量维护</h2><p>每页20件，可追加新商品草稿；每批最多50件，逐件按版本保存。不是整批原子事务，遇到冲突会停下，不覆盖他人更新。</p>
<p class="error" role="alert" v-if="state.error">{{state.error}}。请核对结果，网络未知先重试原批次。</p><p v-if="state.notice">{{state.notice}}</p>
<p v-if="state.locked">本批已确认 {{state.done}} / {{state.count}} 件。{{state.uncertain?'当前请求结果未知':'当前批次尚未结束'}} {{state.blocked}}</p>
<div class="actions"><button :disabled="state.busy" @click="controller.load()">刷新资料（未保存编辑将丢弃）</button><button v-if="state.locked" :disabled="state.busy || !state.ready" @click="controller.resume()">重试／继续原批次</button><button v-if="state.locked && state.blocked && !state.uncertain" :disabled="state.busy" @click="stop">核对后结束本批</button></div>
<template v-if="state.ready"><form aria-label="创建商品分类" @submit.prevent="createCategory"><label>新增分类名称<input v-model="categoryName" maxlength="100" :disabled="state.busy||categoryBusy||!!categoryPending||state.locked" placeholder="例如：干货、日用品"></label><button :disabled="state.busy||categoryBusy||state.locked||(!categoryPending&&!categoryName.trim())">{{categoryPending?'重试原分类创建':'创建分类'}}</button><p v-if="categoryPending" class="notice">分类创建结果待确认，请重试原请求，不要重新新建。</p><p v-if="categoryError" role="alert" class="error">{{categoryError}}</p></form><p class="notice" v-if="!state.categories.length">还没有分类，请先创建分类，再填写商品。新商品默认草稿，不会立即对顾客展示。</p><p>参考价格可空，不表示应付金额；供货说明不表示实时库存。分类归档和多图可在原生商户页维护。新商品默认草稿。</p>
<fieldset :disabled="state.busy || state.locked || categoryBusy || !!categoryPending"><div class="catalog-scroll" tabindex="0" aria-label="商品编辑表，可横向滚动"><table><caption>每个商品保留自己的规格、单位和版本；小屏可横向滚动。</caption><thead><tr><th>保存</th><th>商品/分类</th><th>单位/规格</th><th>参考价/供货</th><th>状态/排序</th><th>介绍</th></tr></thead><tbody><tr v-for="row in state.rows" :key="row.rowKey">
<td><input type="checkbox" v-model="row.selected" :aria-label="'选择商品 '+row.name"><small>{{row.id?'版本'+row.version:'新增'}}</small></td><td><input v-model="row.name" maxlength="120" aria-label="商品名"><select v-model="row.category_id" aria-label="商品分类"><option value="">请选择分类</option><option v-for="cat in state.categories" :key="cat.id" :value="cat.id">{{cat.name}}{{cat.status==='ARCHIVED'?'（归档）':''}}</option></select></td>
<td><input v-model="row.unit" maxlength="20" aria-label="单位" placeholder="斤/份/盒"><input v-model="row.spec" maxlength="120" aria-label="规格"></td><td><input v-model="row.reference_price" maxlength="13" aria-label="参考价格" placeholder="可空"><select v-model="row.supply_status" aria-label="供货说明"><option value="CONFIRM">供货待确认</option><option value="REGULAR">常规供应（非库存）</option><option value="UNAVAILABLE">暂不供应</option></select></td>
<td><select v-model="row.status" aria-label="展示状态"><option value="DRAFT">草稿</option><option value="PUBLISHED">公开</option><option value="ARCHIVED">归档</option></select><input v-model="row.sort_order" maxlength="6" aria-label="排序"></td><td><textarea v-model="row.description" maxlength="4000" aria-label="商品介绍"></textarea></td></tr></tbody></table></div>
<div class="actions"><button :disabled="state.rows.length>=50" @click="controller.add()">加一行新商品草稿</button><button @click="controller.submit()">保存所选商品</button></div></fieldset>
<div class="row"><button :disabled="state.busy || state.locked || state.page<=1" @click="controller.changePage(state.page-1)">上一页</button><span>第{{state.page}}页，共{{state.total}}件</span><button :disabled="state.busy || state.locked || state.page*20>=state.total" @click="controller.changePage(state.page+1)">下一页</button></div></template>
<details v-if="state.results.length" open><summary>本批已确认保存的结果</summary><p v-for="row in state.results" :key="row.id">{{row.name}} · {{row.id}} · 保存时版本{{row.version}}</p></details>
</section></template>
<style scoped>.catalog-scroll{overflow-x:auto}table{border-collapse:collapse;min-width:920px;width:100%}th,td{padding:10px;border:1px solid #dbe4df;vertical-align:top}td input,td select{min-width:130px;margin-bottom:8px}td input[type=checkbox]{min-width:0;width:auto}td textarea{min-width:170px}td small{display:block}</style>
