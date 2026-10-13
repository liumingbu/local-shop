import { auth, ApiError, errorText, needLogin, request, requireId } from '../../lib/client';
import { finishMutation, mutate, pending } from '../../lib/drafts';
import { order, uncertain } from '../../lib/catalog';
import { merchantBase, memberships, selectTenant } from '../../lib/merchant';
import { route, run } from '../../lib/ui';
import type { Category,ListResult,Product } from '../../lib/types';
const blank=()=>({id:'',name:'',sort_order:'0',status:'ACTIVE',version:0});
Page({alive:true,view:0,
 data:{busy:false,error:'',notice:'',storeId:'',owner:'',authorized:false,categories:[] as Category[],catPage:1,catTotal:0,products:[] as Product[],page:1,total:0,
   form:blank(),locked:false,pendingCreate:false,filter:'',lastCategory:''},
 onLoad(query:Record<string,string>){try{this.setData({storeId:requireId(query.store_id)});void this.load();}catch(e){this.setData({error:errorText(e)});}},
 onShow(){this.alive=true;if(this.data.storeId)void this.load();},onHide(){this.view++;this.alive=false;this.setData({busy:false,authorized:false,categories:[],products:[],form:blank()});},onUnload(){this.alive=false;},
 async lists(){const base=merchantBase(this.data.storeId);const [cats,products]=await Promise.all([request<ListResult<Category>>(`${base}/categories?page=${this.data.catPage}&limit=20`),
 request<ListResult<Product>>(`${base}/products?page=${this.data.page}&limit=20${this.data.filter?'&category_id='+this.data.filter:''}`)]);return {categories:cats.items,catTotal:cats.total,products:products.items,total:products.total};},
 load(){return run(this,async commit=>{needLogin();const epoch=auth().generation,view=this.view;commit({authorized:false,categories:[],products:[],form:blank()});selectTenant(await memberships(),this.data.storeId);
   const rows=await this.lists();if(!this.alive||view!==this.view||epoch!==auth().generation)return;const original=pending(this.data.storeId,'category-create');
   commit({...rows,owner:auth().userId,authorized:true,locked:!!original,pendingCreate:!!original,form:original?{...blank(),...(original.body as object)}:blank(),notice:'修改已有分类前请在列表选中；刷新将放弃未提交的分类编辑。'});
 });},
 input(event:WechatMiniprogram.Input){if(this.data.busy||this.data.locked)return;const field=String(event.currentTarget.dataset.field);if(['name','sort_order'].includes(field))this.setData({form:{...this.data.form,[field]:event.detail.value}});},
 archived(event:WechatMiniprogram.CheckboxGroupChange){if(!this.data.busy&&!this.data.locked)this.setData({form:{...this.data.form,status:event.detail.value.includes('archived')?'ARCHIVED':'ACTIVE'}});},
 edit(event:WechatMiniprogram.TouchEvent){if(this.data.busy||this.data.locked)return;const row=this.data.categories.find(x=>x.id===event.currentTarget.dataset.id);if(row)this.setData({form:{...row,sort_order:String(row.sort_order)},notice:'正在编辑已有分类；归档后该分类商品不再公开展示。'});},
 fresh(){if(!this.data.busy&&!this.data.locked)this.setData({form:blank(),notice:'新分类'});},
 save(){return run(this,async commit=>{needLogin();if(!this.data.authorized||this.data.owner!==auth().userId)throw new ApiError('SESSION_CHANGED');if(this.data.locked&&!this.data.pendingCreate)throw new ApiError('VERSION_CONFLICT');
   const view=this.view,epoch=auth().generation,store=this.data.storeId,form=this.data.form,body={name:form.name,sort_order:order(String(form.sort_order)),status:form.status};let saved:Category;
   try{saved=form.id?await request<Category>(`${merchantBase(store)}/categories/${form.id}`,'PUT',{...body,expected_version:form.version}):await mutate<Category>(store,'category-create',merchantBase(store)+'/categories','POST',body);}
   catch(e){commit({locked:form.id?uncertain(e):!!pending(store,'category-create'),pendingCreate:!form.id&&!!pending(store,'category-create')});throw e;}
   if(!this.alive||view!==this.view||epoch!==auth().generation)return;
   if(!form.id){try{finishMutation(store,'category-create');}catch(e){commit({locked:true,pendingCreate:true});throw e;}}commit({form:{...saved,sort_order:String(saved.sort_order)},lastCategory:saved.id,notice:'分类已保存',locked:false,pendingCreate:false});
   try{commit(await this.lists());}catch{commit({error:'已保存分类，列表刷新失败，请手动刷新。'});}
 });},
 filter(event:WechatMiniprogram.TouchEvent){if(this.data.busy)return;this.setData({filter:String(event.currentTarget.dataset.id||''),page:1});void this.load();},
 catPrevious(){if(!this.data.busy&&this.data.catPage>1){this.setData({catPage:this.data.catPage-1});void this.load();}},catNext(){if(!this.data.busy&&this.data.catPage*20<this.data.catTotal){this.setData({catPage:this.data.catPage+1});void this.load();}},
 previous(){if(!this.data.busy&&this.data.page>1){this.setData({page:this.data.page-1});void this.load();}},next(){if(!this.data.busy&&this.data.page*20<this.data.total){this.setData({page:this.data.page+1});void this.load();}},
 createProduct(){route('productedit',this.data.storeId,this.data.filter?'&category_id='+requireId(this.data.filter):'');},open(event:WechatMiniprogram.TouchEvent){route('productedit',this.data.storeId,'&product_id='+requireId(event.currentTarget.dataset.id));},back(){route('merchant',this.data.storeId);},
});
