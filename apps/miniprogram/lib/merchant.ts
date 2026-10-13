import { ApiError, needLogin, request, requireId } from './client';
import type { RecordData } from './types';
export interface Tenant {id:string;name:string;role:string}
export async function memberships():Promise<Tenant[]> {needLogin();return (await request<{items:Tenant[]}>('/api/v1/merchant/tenants')).items;}
export function selectTenant(rows:Tenant[],id:string):Tenant|null {
  if(id){const selected=rows.find(x=>x.id===requireId(id));if(!selected)throw new ApiError('TENANT_NOT_FOUND');return selected;}
  if(!rows.length)throw new ApiError('NO_MERCHANT_MEMBERSHIP');
  return rows.length===1?rows[0]:null;
}
export function merchantBase(id:string):string{return `/api/v1/merchant/tenants/${requireId(id)}`;}
export function transitions(row:RecordData):string[]{
  if(row.cancellation_requests?.some(x=>x.status==='REQUESTED'))return [];
  const choices:Record<string,string[]>={PENDING_CONFIRMATION:['CONFIRMED','CANCELLED'],CONFIRMED:['PREPARING','CANCELLED'],PREPARING:['READY','CANCELLED'],
    READY:row.fulfillment_method==='PICKUP'?['COMPLETED','CANCELLED']:['OUT_FOR_DELIVERY','CANCELLED'],OUT_FOR_DELIVERY:['COMPLETED','CANCELLED'],COMPLETED:[],CANCELLED:[]};
  return choices[row.status]||[];
}
