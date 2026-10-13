import { auth, ApiError, errorText, needLogin, privateImage, request, requireId } from '../../lib/client';
import { allCategories, blankProduct, productBody, productForm, uncertain } from '../../lib/catalog';
import { finishMutation, mutate, pending } from '../../lib/drafts';
import { merchantBase, memberships, selectTenant } from '../../lib/merchant';
import { chooseAndUpload } from '../../lib/media';
import { route, run } from '../../lib/ui';
import type { Category,Product } from '../../lib/types';
Page({alive:true,view:0,
 data:{busy:false,error:'',notice:'',storeId:'',productId:'',initialCategory:'',owner:'',authorized:false,form:blankProduct(),version:0,categories:[] as Category[],categoryNames:[] as string[],categoryIndex:-1,
 statuses:['草稿','公开','归档'],statusIndex:0,supplies:['供货待确认','常规供应（不表示有现货）','暂不供应'],supplyIndex:0,locked:false,pendingCreate:false,
 images:[] as {id:string;url:string;path:string}[],imagesDirty:false},
 onLoad(query:Record<string,string>){try{this.setData({storeId:requireId(query.store_id),productId:query.product_id?requireId(query.product_id):'',initialCategory:query.category_id?requireId(query.category_id):''});void this.load();}catch(e){this.setData({error:errorText(e)});}},
 onShow(){this.alive=true;if(this.data.storeId)void this.load();},onHide(){this.view++;this.alive=false;this.setData({busy:false,authorized:false,form:blankProduct(),images:[],categories:[]});},onUnload(){this.alive=false;},
 base(){return merchantBase(this.data.storeId)+'/products';},
 async previews(images:{id:string;url:string}[]){return Promise.all(images.map(async x=>({...x,path:await privateImage(x.url).catch(()=> '')})));},
 load(){return run(this,async commit=>{needLogin();commit({authorized:false,images:[],imagesDirty:false});selectTenant(await memberships(),this.data.storeId);const categories=await allCategories(this.data.storeId);
   const original=!this.data.productId?pending(this.data.storeId,'product-create'):undefined;
   const product=this.data.productId?await request<Product>(this.base()+'/'+this.data.productId):null;
   const form=product?productForm(product):original?productForm({...original.body as Product,reference_price:(original.body as Product).reference_price,images:[],version:0}):blankProduct(this.data.initialCategory);
   commit({owner:auth().userId,authorized:true,categories,categoryNames:categories.map(x=>x.name+(x.status==='ARCHIVED'?'（归档）':'')),categoryIndex:categories.findIndex(x=>x.id===form.category_id),
     form,version:product?.version||0,locked:!!original,pendingCreate:!!original,statusIndex:['DRAFT','PUBLISHED','ARCHIVED'].indexOf(form.status),supplyIndex:['CONFIRM','REGULAR','UNAVAILABLE'].indexOf(form.supply_status),notice:'刷新会放弃未保存编辑；参考价格不构成应付金额。'});
   if(product)commit({images:await this.previews(product.images)});
 });},
 input(event:WechatMiniprogram.Input){if(this.data.busy||this.data.locked)return;const field=String(event.currentTarget.dataset.field);if(['name','description','unit','spec','reference_price','sort_order'].includes(field))this.setData({form:{...this.data.form,[field]:event.detail.value}});},
 category(event:WechatMiniprogram.PickerChange){if(this.data.busy||this.data.locked)return;const index=Number(event.detail.value),row=this.data.categories[index];if(row)this.setData({categoryIndex:index,form:{...this.data.form,category_id:row.id}});},
 status(event:WechatMiniprogram.PickerChange){if(this.data.busy||this.data.locked)return;const index=Number(event.detail.value);if(index>=0&&index<3)this.setData({statusIndex:index,form:{...this.data.form,status:['DRAFT','PUBLISHED','ARCHIVED'][index]}});},
 supply(event:WechatMiniprogram.PickerChange){if(this.data.busy||this.data.locked)return;const index=Number(event.detail.value);if(index>=0&&index<3)this.setData({supplyIndex:index,form:{...this.data.form,supply_status:['CONFIRM','REGULAR','UNAVAILABLE'][index]}});},
 save(){return run(this,async commit=>{needLogin();if(!this.data.authorized||this.data.owner!==auth().userId)throw new ApiError('SESSION_CHANGED');if(this.data.locked&&!this.data.pendingCreate)throw new ApiError('VERSION_CONFLICT');
   const view=this.view,epoch=auth().generation,store=this.data.storeId,id=this.data.productId,body=productBody(this.data.form);let row:Product;
   try{row=id?await request<Product>(this.base()+'/'+id,'PUT',{...body,expected_version:this.data.version}):await mutate<Product>(store,'product-create',this.base(),'POST',body);}
   catch(e){commit({locked:id?uncertain(e):!!pending(store,'product-create'),pendingCreate:!id&&!!pending(store,'product-create')});throw e;}
   if(!this.alive||view!==this.view||epoch!==auth().generation)return;
   if(!id){try{finishMutation(store,'product-create');}catch(e){commit({locked:true,pendingCreate:true});throw e;}}commit({productId:row.id,version:row.version,form:productForm(row),locked:false,pendingCreate:false,notice:'商品资料已保存；图片顺序需要单独保存。'});
 });},
 upload(){return run(this,async commit=>{if(!this.data.productId||this.data.locked||!this.data.authorized)throw new ApiError('SAVE_PRODUCT_FIRST');if(this.data.images.length>=8)throw new ApiError('TOO_MANY_IMAGES');
   const view=this.view;const uploaded=await chooseAndUpload(merchantBase(this.data.storeId)+'/media?purpose=PRODUCT',()=>this.alive&&this.view===view);const url=merchantBase(this.data.storeId)+`/media/${uploaded.id}/content`;
   const path=await privateImage(url).catch(()=> '');commit({images:[...this.data.images,{id:uploaded.id,url,path}],imagesDirty:true,notice:'图片已暂存，保存图片顺序后才关联本商品。'});
 });},
 remove(event:WechatMiniprogram.TouchEvent){if(this.data.busy||this.data.locked)return;this.setData({images:this.data.images.filter((_,i)=>i!==Number(event.currentTarget.dataset.index)),imagesDirty:true});},
 move(event:WechatMiniprogram.TouchEvent){if(this.data.busy||this.data.locked)return;const index=Number(event.currentTarget.dataset.index),delta=Number(event.currentTarget.dataset.delta),target=index+delta,images=[...this.data.images];if(![-1,1].includes(delta)||!images[index]||!images[target])return;[images[index],images[target]]=[images[target],images[index]];this.setData({images,imagesDirty:true});},
 saveImages(){return run(this,async commit=>{needLogin();if(!this.data.productId||this.data.locked||!this.data.authorized)throw new ApiError('SAVE_PRODUCT_FIRST');
   try{const saved=await request<{version:number;images:Product['images']}>(this.base()+'/'+this.data.productId+'/images','PUT',{expected_version:this.data.version,media_ids:this.data.images.map(x=>x.id)});commit({version:saved.version,imagesDirty:false,notice:'图片顺序已保存；移除的是商品关联，未执行永久文件删除。'});}
   catch(e){if(uncertain(e))commit({locked:true,notice:'图片保存结果或版本不确定，请刷新并核对服务器顺序。'});throw e;}
 });},
 back(){route('catalog',this.data.storeId);},
});
