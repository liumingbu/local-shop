import { ApiError } from './api';
import { requireId,type PendingStorage,type Transport } from './platform';
interface Category {id:string;name:string;status:string}
interface Product {id:string;version:number;category_id:string;name:string;description:string;unit:string;spec:string;reference_price:string|null;status:string;supply_status:string;sort_order:number}
interface List<T>{items:T[];total:number}
export interface CatalogRow {id:string;version:number;category_id:string;name:string;description:string;unit:string;spec:string;reference_price:string;status:string;supply_status:string;sort_order:string;selected:boolean;rowKey:string}
interface Command {path:string;method:'POST'|'PUT';body:unknown;key:string;name:string}
interface Result {name:string;id:string;version:number}
interface Batch {commands:Command[];cursor:number;completed:Result[];blocked:string;uncertain:boolean}
export function catalogState(){return {busy:false,ready:false,error:'',notice:'',locked:false,uncertain:false,blocked:'',page:1,total:0,done:0,count:0,rows:[] as CatalogRow[],categories:[] as Category[],results:[] as Result[]};}
export type CatalogState=ReturnType<typeof catalogState>;
export function bodyOf(row:CatalogRow){
 const limits:{[key:string]:number}={name:120,description:4000,unit:20,spec:120};for(const [name,limit]of Object.entries(limits)){const value=row[name as keyof CatalogRow];if(typeof value!=='string'||value.length>limit)throw Error('INVALID_PRODUCT_TEXT');}
 if(!row.name.trim()||!row.unit.trim())throw Error('NAME_AND_UNIT_REQUIRED');requireId(row.category_id);
 if(!['DRAFT','PUBLISHED','ARCHIVED'].includes(row.status)||!['CONFIRM','REGULAR','UNAVAILABLE'].includes(row.supply_status))throw Error('INVALID_PRODUCT_STATUS');
 if(row.reference_price!==''&&!/^(?:0|[1-9]\d{0,9})(?:\.\d{1,2})?$/.test(row.reference_price))throw Error('INVALID_REFERENCE_PRICE');
 if(!/^\d{1,6}$/.test(row.sort_order)||Number(row.sort_order)>100000)throw Error('INVALID_SORT_ORDER');
 return {category_id:row.category_id,name:row.name,description:row.description,unit:row.unit,spec:row.spec,reference_price:row.reference_price===''?null:row.reference_price,status:row.status,supply_status:row.supply_status,sort_order:Number(row.sort_order),...(row.id?{expected_version:row.version}:{})};
}
export class CatalogConsole {
 private alive=true;private root:string;private slot:string;
 constructor(public state:CatalogState,private transport:Transport,private storage:PendingStorage,user:string,tenant:string,private makeKey:()=>string=()=>crypto.randomUUID()){
  this.root=`/api/v1/merchant/tenants/${requireId(tenant)}/products`;this.slot=`local-shop.web.catalog.v1.${requireId(user)}.${requireId(tenant)}`;
 }
 dispose(){this.alive=false;this.state.ready=false;this.state.rows=[];this.state.categories=[];this.state.results=[];}
 private patch(value:Partial<CatalogState>){if(this.alive)Object.assign(this.state,value);}
 private save(batch:Batch|null){try{this.storage.setItem(this.slot,JSON.stringify(batch));}catch{throw Error('LOCAL_BATCH_UNAVAILABLE');}}
 private read():Batch|null{try{const raw=this.storage.getItem(this.slot);if(!raw||raw==='null')return null;if(raw.length>300000)throw Error();const x=JSON.parse(raw) as Batch;
   if(!Array.isArray(x.commands)||!x.commands.length||x.commands.length>50||!Number.isInteger(x.cursor)||x.cursor<0||x.cursor>x.commands.length||!Array.isArray(x.completed)||x.completed.length!==x.cursor)throw Error();
   for(const c of x.commands){if(typeof c.key!=='string'||!/^[A-Za-z0-9_.-]{8,100}$/.test(c.key)||!c.body||typeof c.body!=='object'||Array.isArray(c.body))throw Error();
    if(c.method==='POST'){if(c.path!==this.root)throw Error();}else if(c.method==='PUT'){if(!c.path.startsWith(this.root+'/'))throw Error();requireId(c.path.slice(this.root.length+1));}else throw Error();
   }return x;
  }catch{throw Error('LOCAL_BATCH_UNAVAILABLE');}}
 private show(batch:Batch|null){this.patch({locked:!!batch,done:batch?.cursor||0,count:batch?.commands.length||0,blocked:batch?.blocked||'',uncertain:!!batch?.uncertain,results:batch?.completed||[]});}
 private async run(fn:()=>Promise<void>){if(!this.alive||this.state.busy)return;this.patch({busy:true,error:''});try{await fn();}catch(e){this.patch({error:e instanceof ApiError?e.code:e instanceof Error?e.message:'NETWORK_UNCERTAIN'});}finally{this.patch({busy:false});}}
 private async rows(){const response=await this.transport<List<Product>>(`${this.root}?page=${this.state.page}&limit=20`);this.patch({total:response.total,rows:response.items.map(x=>({...x,reference_price:x.reference_price??'',sort_order:String(x.sort_order),selected:false,rowKey:x.id}))});}
 load(){return this.run(async()=>{this.patch({ready:false,rows:[],categories:[]});this.show(this.read());const categories:Category[]=[];
  for(let page=1;page<=100;page++){const response=await this.transport<List<Category>>(`${this.root.replace(/\/products$/,'/categories')}?page=${page}&limit=100`);categories.push(...response.items);if(page*100>=response.total)break;if(page===100)throw Error('TOO_MANY_CATEGORIES');}
  await this.rows();this.patch({categories,ready:true});
 });}
 add(){if(this.state.busy||this.state.locked||!this.state.ready||this.state.rows.length>=50)return;this.state.rows.push({id:'',version:0,category_id:this.state.categories.find(x=>x.status==='ACTIVE')?.id||'',name:'',description:'',unit:'',spec:'',reference_price:'',status:'DRAFT',supply_status:'CONFIRM',sort_order:'0',selected:true,rowKey:this.makeKey()});}
 changePage(page:number){if(this.state.busy||this.state.locked||page<1||!Number.isSafeInteger(page))return Promise.resolve();this.state.page=page;return this.load();}
 submit(){return this.run(async()=>{if(!this.state.ready)throw Error('TENANT_NOT_READY');if(this.read())throw Error('BATCH_ALREADY_PENDING');const selected=this.state.rows.filter(x=>x.selected);if(!selected.length||selected.length>50)throw Error('SELECT_ONE_TO_FIFTY_ROWS');
  // Validate the entire selection before persisting or sending the first command.
  const commands:Command[]=selected.map(row=>({path:this.root+(row.id?'/'+requireId(row.id):''),method:row.id?'PUT':'POST',body:bodyOf(row),key:this.makeKey(),name:row.name}));
  const batch:Batch={commands,cursor:0,completed:[],blocked:'',uncertain:false};this.save(batch);this.show(batch);await this.execute(batch);
 });}
 resume(){return this.run(async()=>{if(!this.state.ready)throw Error('TENANT_NOT_READY');const batch=this.read();if(!batch)throw Error('NO_PENDING_BATCH');await this.execute(batch);});}
 private async execute(batch:Batch){
  while(batch.cursor<batch.commands.length){if(!this.alive)return;const c=batch.commands[batch.cursor];let result:Product;
   try{result=await this.transport<Product>(c.path,c.method,c.body,c.key);}catch(e){if(!this.alive)return;batch.blocked=e instanceof ApiError?e.code:'NETWORK_UNCERTAIN';batch.uncertain=!(e instanceof ApiError&&e.status>=400&&e.status<500&&![401,403,408,429].includes(e.status));this.save(batch);this.show(batch);throw e;}
   if(!this.alive)return;
   batch.completed.push({name:c.name,id:requireId(result.id),version:result.version});batch.cursor++;batch.blocked='';batch.uncertain=false;
   this.save(batch);this.show(batch); // If persistence fails, stored cursor stays old and same key safely replays.
  }
  this.patch({rows:[],notice:'本批全部请求已保存。正在重新读取当前版本；这不是跨商品原子事务。'});this.save(null);this.patch({locked:false,uncertain:false,blocked:''});await this.rows();
 }
 discardKnownFailure(confirmed:boolean){return this.run(async()=>{const batch=this.read();if(!confirmed||!batch||!batch.blocked||batch.uncertain)throw Error('VERIFY_OR_RETRY_ORIGINAL_BATCH');
  this.patch({rows:[],results:batch.completed,notice:'已保留成功项，明确放弃未执行的剩余请求；不会回滚已保存商品。'});this.save(null);this.patch({locked:false,blocked:'',uncertain:false});await this.rows();
 });}
}
