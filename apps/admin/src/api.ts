export class ApiError extends Error {
  constructor(public status: number, public code: string) { super(code); }
}
export interface Tenant { id: string; name: string; role: string }
export interface Store { name: string; description: string; version: number; public_contact?:string;public_address?:string;business_hours?:string;delivery_note?:string;allow_pickup?:boolean;allow_delivery?:boolean;published?:boolean }
export interface RecordItem {
  business_number?:string;contact_name?:string;contact_phone?:string;delivery_address?:string;confirmed_due_at?:string|null;is_overdue?:boolean;
  id: string; tenant_id: string; customer_label: string; raw_text: string;
  source: string; fulfillment_method: 'PICKUP' | 'DELIVERY'; status: string;
  version: number; created_at: string; expected_time_note?:string;internal_note?:string;items?:{name:string;quantity:string;unit:string;spec:string}[];
  confirmation_revisions?:{id:string;confirmed_version:number|null;details:{summary:string;time_note:string;fulfillment_at:string|null}}[];
  cancellation_requests?:{id:string;status:string;reason:string;response_note:string}[];
  events?:{to_status:string;action:string;note:string}[];
}
export async function request<T>(path: string, token: string, method = 'GET', body?: unknown, key?: string): Promise<T> {
  if(!path.startsWith('/api/v1/')||path.includes('..')||path.includes('://')||path.includes('\\'))throw new ApiError(0,'INVALID_API_PATH');
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10000);
  try {
    const response = await fetch(path, {
      method, signal: controller.signal, redirect: 'error',
      headers: { 'Content-Type': 'application/json', ...(token ? {Authorization: `Bearer ${token}`} : {}),
                 ...(key ? {'Idempotency-Key': key} : {}) },
      ...(body === undefined ? {} : {body: JSON.stringify(body)}),
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new ApiError(response.status, error.code ?? `HTTP_${response.status}`);
    }
    return await response.json() as T;
  } finally { clearTimeout(timeout); }
}
export function transitions(record: RecordItem): string[] {
  if(record.cancellation_requests?.some(x=>x.status==='REQUESTED'))return [];
  const choices: { [key: string]: string[] } = {
    PENDING_CONFIRMATION: ['CONFIRMED', 'CANCELLED'], CONFIRMED: ['PREPARING', 'CANCELLED'],
    PREPARING: ['READY', 'CANCELLED'],
    READY: record.fulfillment_method === 'PICKUP' ? ['COMPLETED', 'CANCELLED'] : ['OUT_FOR_DELIVERY', 'CANCELLED'],
    OUT_FOR_DELIVERY: ['COMPLETED', 'CANCELLED'], COMPLETED: [], CANCELLED: [],
  };
  return choices[record.status] ?? [];
}
