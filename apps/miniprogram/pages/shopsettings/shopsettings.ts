import { auth, ApiError, errorText, needLogin, request, requireId } from '../../lib/client';
import { memberships, merchantBase, selectTenant } from '../../lib/merchant';
import { route, run } from '../../lib/ui';
interface Settings {name:string;description:string;public_contact:string;public_address:string;business_hours:string;delivery_note:string;allow_pickup:boolean;allow_delivery:boolean;published:boolean;version:number;logo_media_id:string|null}
const blank=():Settings=>({name:'',description:'',public_contact:'',public_address:'',business_hours:'',delivery_note:'',allow_pickup:false,allow_delivery:false,published:false,version:0,logo_media_id:null});
Page({alive:true,view:0,
  data:{busy:false,error:'',notice:'',storeId:'',owner:'',form:null as Settings|null,locked:false,authorized:false},
  onLoad(query:Record<string,string>){try{this.setData({storeId:requireId(query.store_id)});void this.load();}catch(e){this.setData({error:errorText(e)});}},
  onShow(){this.alive=true;if(this.data.storeId)void this.load();},
  onHide(){this.view++;this.alive=false;this.setData({busy:false,form:null,authorized:false});},onUnload(){this.alive=false;},
  async read(){try{return await request<Settings>(merchantBase(this.data.storeId)+'/store');}catch(e){if(e instanceof ApiError&&e.status===404)return blank();throw e;}},
  load(){return run(this,async commit=>{needLogin();commit({form:null,authorized:false});const members=await memberships(),member=selectTenant(members,this.data.storeId);if(member?.role!=='OWNER')throw new ApiError('OWNER_REQUIRED');
    const form=await this.read();commit({owner:auth().userId,form,locked:false,authorized:true,notice:'已读取当前版本；未提交的编辑离开后不会保留。'});});},
  input(event:WechatMiniprogram.Input){if(this.data.busy||this.data.locked||!this.data.form)return;const field=String(event.currentTarget.dataset.field);
    if(['name','description','public_contact','public_address','business_hours','delivery_note'].includes(field))this.setData({form:{...this.data.form,[field]:event.detail.value}});},
  flags(event:WechatMiniprogram.CheckboxGroupChange){if(this.data.busy||this.data.locked||!this.data.form)return;const values=event.detail.value;this.setData({form:{...this.data.form,allow_pickup:values.includes('pickup'),allow_delivery:values.includes('delivery'),published:values.includes('published')}});},
  save(){return run(this,async commit=>{needLogin();const form=this.data.form;if(!form||!this.data.authorized)throw new ApiError('OWNER_REQUIRED');if(this.data.locked)throw new ApiError('VERSION_CONFLICT');
    if(this.data.owner!==auth().userId)throw new ApiError('SESSION_CHANGED');
    const body={name:form.name,description:form.description,public_contact:form.public_contact,public_address:form.public_address,business_hours:form.business_hours,
      delivery_note:form.delivery_note,allow_pickup:form.allow_pickup,allow_delivery:form.allow_delivery,published:form.published,expected_version:form.version,logo_media_id:form.logo_media_id};
    try{const saved=await request<Settings>(merchantBase(this.data.storeId)+'/store','PUT',body);commit({form:saved,notice:'店铺资料已保存',locked:false});}
    catch(e){if(!(e instanceof ApiError)||!e.status||e.status===409||e.status>=500)commit({locked:true,notice:'结果或版本不确定，请先重新读取服务端资料并核对；不会自动覆盖新版本。'});throw e;}
  });},
  back(){route('merchant',this.data.storeId);},
});
