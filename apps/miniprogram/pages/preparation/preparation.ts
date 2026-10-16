import {errorText,needLogin,request,requireId} from '../../lib/client';
import {merchantBase,memberships,selectTenant} from '../../lib/merchant';
import {route,run} from '../../lib/ui';
interface Preparation {preview_products:{name:string;spec:string;unit:string;status:string}[];store:{name:string;description:string;public_contact:string;public_address:string;delivery_note:string}|null;steps:{id:string;label:string;complete:boolean}[];product_count:number;category_count:number;notice:string}
Page({alive:true,view:0,
 data:{busy:false,error:'',storeId:'',info:null as Preparation|null,preview:false},
 onLoad(query:Record<string,string>){try{this.setData({storeId:requireId(query.store_id)});void this.load();}catch(e){this.setData({error:errorText(e)});}},
 onShow(){this.alive=true;if(this.data.storeId)void this.load();},
 onHide(){this.alive=false;this.view++;this.setData({info:null,preview:false,busy:false});},
 onUnload(){this.alive=false;this.view++;},
 load(){return run(this,async commit=>{needLogin();commit({info:null});selectTenant(await memberships(),this.data.storeId);const info=await request<Preparation>(merchantBase(this.data.storeId)+'/preparation');commit({info});});},
 settings(){route('shopsettings',this.data.storeId);},catalog(){route('catalog',this.data.storeId);},
 later(){route('merchant',this.data.storeId);},preview(){this.setData({preview:!this.data.preview});},
});
