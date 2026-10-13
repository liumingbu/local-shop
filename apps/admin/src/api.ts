export class ApiError extends Error {
  constructor(public status: number, public code: string) { super(code); }
}
export interface Tenant { id: string; name: string; role: string }
export interface Store { name: string; description: string; version: number }
export interface RecordItem {
  id: string; tenant_id: string; customer_label: string; raw_text: string;
  source: string; fulfillment_method: 'PICKUP' | 'DELIVERY'; status: string;
  version: number; created_at: string;
}
export async function request<T>(path: string, token: string, method = 'GET', body?: unknown, key?: string): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10000);
  try {
    const response = await fetch(path, {
      method, signal: controller.signal,
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
  const choices: { [key: string]: string[] } = {
    PENDING_CONFIRMATION: ['CONFIRMED', 'CANCELLED'], CONFIRMED: ['PREPARING', 'CANCELLED'],
    PREPARING: ['READY', 'CANCELLED'],
    READY: record.fulfillment_method === 'PICKUP' ? ['COMPLETED', 'CANCELLED'] : ['OUT_FOR_DELIVERY', 'CANCELLED'],
    OUT_FOR_DELIVERY: ['COMPLETED', 'CANCELLED'], COMPLETED: [], CANCELLED: [],
  };
  return choices[record.status] ?? [];
}
