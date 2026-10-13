import { ApiError } from './api';
export interface Invitation {id:string;owner_user_id:string;proposed_name:string;status:string;version:number;tenant_id:string|null;created_at:string}
export interface PlatformTenant {id:string;display_name:string;status:string;version:number}
export interface Audit {id:string;actor_id:string;action:string;before_status:string|null;after_status:string;reason:string;created_at:string}
interface List<T>{items:T[];total:number;page:number;limit:number}
interface Pending {path:string;body:unknown;key:string}
export interface PendingStorage {getItem(key:string):string|null;setItem(key:string,value:string):void}
export type Transport=<T>(path:string,method?:string,body?:unknown,key?:string)=>Promise<T>;
const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export function requireId(value:string):string {if(!uuid.test(value))throw new Error('INVALID_ID');return value.toLowerCase();}
function allowed(path:string){return path==='/api/v1/platform/invitations'||/^\/api\/v1\/platform\/(?:invitations\/[0-9a-f-]{36}\/review|tenants\/[0-9a-f-]{36}\/status)$/.test(path);}
export function platformState(){return {busy:false,error:'',notice:'',ready:false,locked:false,pendingPath:'',tenantPage:1,invitationPage:1,auditPage:1,
 tenants:[] as PlatformTenant[],tenantTotal:0,invitations:[] as Invitation[],invitationTotal:0,audit:[] as Audit[],auditTotal:0};}
export type PlatformState=ReturnType<typeof platformState>;
export class PlatformConsole {
 private alive=true;
 private slot:string;
 constructor(public state:PlatformState,private transport:Transport,private storage:PendingStorage,userId:string,private keyFactory:()=>string=()=>crypto.randomUUID()){
  this.slot=`local-shop.web.platform.v1.${requireId(userId)}`;
 }
 dispose(){this.alive=false;this.state.tenants=[];this.state.invitations=[];this.state.audit=[];this.state.ready=false;}
 private readPending():Pending|null{
  try{const raw=this.storage.getItem(this.slot);if(!raw||raw==='null')return null;if(raw.length>10000)throw Error();const x=JSON.parse(raw);
   if(!x||typeof x.path!=='string'||!allowed(x.path)||typeof x.key!=='string'||!/^[A-Za-z0-9_.-]{8,100}$/.test(x.key)||!x.body||typeof x.body!=='object'||Array.isArray(x.body))throw Error();return x;
  }catch{throw new Error('LOCAL_PENDING_UNAVAILABLE');}
 }
 private store(value:Pending|null){try{this.storage.setItem(this.slot,JSON.stringify(value));}catch{throw new Error('LOCAL_PENDING_UNAVAILABLE');}}
 private patch(value:Partial<PlatformState>){if(this.alive)Object.assign(this.state,value);}
 private async run(fn:()=>Promise<void>){if(!this.alive||this.state.busy)return;this.patch({busy:true,error:''});try{await fn();}catch(e){this.patch({error:e instanceof ApiError?e.code:e instanceof Error?e.message:'NETWORK_UNCERTAIN'});}finally{this.patch({busy:false});}}
 private async readLists(){const [tenants,invitations,audit]=await Promise.all([
   this.transport<List<PlatformTenant>>(`/api/v1/platform/tenants?page=${this.state.tenantPage}&limit=20`),
   this.transport<List<Invitation>>(`/api/v1/platform/invitations?page=${this.state.invitationPage}&limit=20`),
   this.transport<List<Audit>>(`/api/v1/platform/audit?page=${this.state.auditPage}&limit=20`)]);
   this.patch({tenants:tenants.items,tenantTotal:tenants.total,invitations:invitations.items,invitationTotal:invitations.total,audit:audit.items,auditTotal:audit.total});
 }
 load(){return this.run(async()=>{this.patch({ready:false,tenants:[],invitations:[],audit:[]});const pending=this.readPending();this.patch({locked:!!pending,pendingPath:pending?.path||''});
  const me=await this.transport<{role:string}>('/api/v1/platform/me');if(me.role!=='PLATFORM_ADMIN')throw Error('PLATFORM_ADMIN_REQUIRED');await this.readLists();this.patch({ready:true});
 });}
 changePage(kind:'tenant'|'invitation'|'audit',next:number){if(this.state.busy||!Number.isSafeInteger(next)||next<1)return Promise.resolve();this.state[`${kind}Page`]=next;return this.load();}
 private command(path:string,body:unknown){return this.run(async()=>{if(!this.state.ready)throw Error('PLATFORM_ADMIN_REQUIRED');if(!allowed(path))throw Error('INVALID_API_PATH');
  const old=this.readPending();if(old&&old.path!==path)throw Error('PENDING_DIFFERENT_OPERATION');const command=old||{path,body:JSON.parse(JSON.stringify(body)),key:this.keyFactory()};
  this.store(command);this.patch({locked:true,pendingPath:command.path});
  try{await this.transport(command.path,'POST',command.body,command.key);}catch(e){
   if(e instanceof ApiError&&e.status>=400&&e.status<500&&![401,403,408,429].includes(e.status)){
    this.store(null);this.patch({locked:false,pendingPath:''});
   }throw e;
  }
  if(!this.alive)return;await this.readLists();if(!this.alive)return;
  this.store(null);this.patch({locked:false,pendingPath:'',notice:'命令已执行并重新读取服务端状态'});
 });}
 invite(ownerId:string,name:string,reason:string){try{return this.command('/api/v1/platform/invitations',{owner_user_id:requireId(ownerId.trim()),proposed_name:name,reason});}catch(e){this.patch({error:e instanceof Error?e.message:'INVALID_INPUT'});return Promise.resolve();}}
 review(row:Invitation,decision:'APPROVED'|'REJECTED',reason:string){if(this.state.locked)return Promise.resolve();return this.command(`/api/v1/platform/invitations/${requireId(row.id)}/review`,{expected_version:row.version,decision,reason});}
 status(row:PlatformTenant,status:'ACTIVE'|'SUSPENDED',reason:string){if(this.state.locked)return Promise.resolve();return this.command(`/api/v1/platform/tenants/${requireId(row.id)}/status`,{expected_version:row.version,status,reason});}
 retry(){let pending:Pending|null;try{pending=this.readPending();}catch(e){this.patch({error:e instanceof Error?e.message:'LOCAL_PENDING_UNAVAILABLE'});return Promise.resolve();}return pending?this.command(pending.path,pending.body):Promise.resolve();}
}
