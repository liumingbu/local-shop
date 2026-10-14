import { ApiError } from './api';
import { requireId, type PendingStorage } from './platform';
export interface ManualDraft {customer_label:string;raw_text:string;source:string;fulfillment_method:string;expected_time_note:string;internal_note:string;mark_confirmed:boolean;copy_review_required?:boolean;contact_name:string;contact_phone:string;delivery_address:string;expected_at:string|null;items:{name:string;quantity:string;unit:string;spec:string;product_id?:string|null}[]}
export interface Command {path:string;body:unknown;key:string}
export const emptyDraft=():ManualDraft=>({customer_label:'',raw_text:'',source:'MERCHANT_PHONE',fulfillment_method:'PICKUP',expected_time_note:'',internal_note:'',mark_confirmed:false,contact_name:'',contact_phone:'',delivery_address:'',expected_at:null,items:[]});
export class WorkbenchDraft {
 readonly root:string;private slot:string;
 constructor(private storage:PendingStorage,user:string,tenant:string){this.root=`/api/v1/merchant/tenants/${requireId(tenant)}/reservations`;this.slot=`local-shop.web.workbench.v1.${requireId(user)}.${requireId(tenant)}`;}
 read():{draft:ManualDraft;pending:Command|null}{
  try{const raw=this.storage.getItem(this.slot);if(!raw)return{draft:emptyDraft(),pending:null};if(raw.length>50000)throw Error();const value=JSON.parse(raw);
   const draft={...emptyDraft(),...value.draft};const limits:Record<string,number>={customer_label:100,raw_text:4000,expected_time_note:200,internal_note:2000,contact_name:100,contact_phone:50,delivery_address:500};
   if(!draft||Object.entries(limits).some(([k,n])=>typeof draft[k]!=='string'||draft[k].length>n)||!['MERCHANT_PHONE','MERCHANT_WECHAT','MERCHANT_IN_STORE'].includes(draft.source)||!['PICKUP','DELIVERY'].includes(draft.fulfillment_method)||typeof draft.mark_confirmed!=='boolean')throw Error();
   const pending=value.pending;if(pending){if(!/^[A-Za-z0-9_.-]{8,100}$/.test(pending.key)||!pending.body||typeof pending.body!=='object'||Array.isArray(pending.body))throw Error();
    if(pending.path!==this.root){if(typeof pending.path!=='string'||!pending.path.startsWith(this.root+'/'))throw Error();const parts=pending.path.slice(this.root.length+1).split('/');requireId(parts[0]);if(parts.length===4&&parts[1]==='cancellation-requests'&&parts[3]==='decision'){requireId(parts[2]);}else if(parts.length!==2||!['transitions','confirmation-revisions'].includes(parts[1]))throw Error();}}
   if(!Array.isArray(draft.items)||draft.items.length>100)throw Error();return{draft:{...emptyDraft(),...draft},pending:pending||null};
  }catch{throw Error('LOCAL_DRAFT_UNAVAILABLE');}
 }
 save(draft:ManualDraft,pending:Command|null){try{this.storage.setItem(this.slot,JSON.stringify({draft,pending}));}catch{throw Error('LOCAL_DRAFT_UNAVAILABLE');}}
}
export function errorMessage(reason:unknown):string{
 const code=reason instanceof ApiError?reason.code:reason instanceof Error?reason.message:'';
 const messages:Record<string,string>={VERSION_CONFLICT:'记录已被更新，请刷新核对后再操作，不会覆盖他人修改。',EXPLICIT_RECONFIRMATION_REQUIRED:'需要先打开详情，核对最新确认内容并勾选已与顾客确认。',CANCELLATION_REVIEW_REQUIRED:'顾客有待处理的取消申请，请先在商户详情处理。',LOCAL_DRAFT_UNAVAILABLE:'当前设备无法可靠保存草稿，请检查存储后重试；未发起新的业务提交。',TENANT_ACCESS_DENIED:'当前店铺已暂停或授权失效，请重新登录并核对店铺。',TOKEN_EXPIRED:'登录已过期，请重新登录同一身份；原请求仍会保留。'};
 if(messages[code])return messages[code];
 if(reason instanceof ApiError&&reason.status===401)return '登录已失效，请重新登录；草稿和待确认请求仍保留。';
 if(reason instanceof ApiError&&reason.status===403)return '没有当前操作权限，请核对身份或店铺状态。';
 if(reason instanceof ApiError&&reason.status===409)return '当前状态有冲突，请刷新并核对处理结果。';
 if(reason instanceof ApiError&&reason.status===422)return '请检查必填内容、数量和时间格式。';
 if(reason instanceof ApiError&&reason.status===429)return '操作较频繁，请稍后重试原请求。';
 if(reason instanceof ApiError&&reason.status===404)return '记录或店铺不可访问，请核对当前入口。';
 return '网络结果未确认，请重试原操作；不会另外生成一条需求。';
}
