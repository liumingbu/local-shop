import { ApiError, auth, makeKey, needLogin, request, requireId, type Method } from './client';
import type { Draft, Item } from './types';
interface Pending {
    path: string;
    method: Method;
    body: unknown;
    key: string;
}
const blank = (): Draft => ({ raw_text: '', customer_label: '', items: [], media_ids: [], fulfillment_method: 'PICKUP', expected_time_note: '', privacy_accepted: false });
function storageKey(store: string, kind: string): string {
    // Anonymous carts are distinct from every authenticated account; never auto-claim a prior user's draft.
    return `local-shop.v1.${auth().userId || 'guest'}.${requireId(store)}.${kind}`;
}
function get<T>(key: string): T | undefined {
    try {
        return wx.getStorageSync(key) || undefined;
    }
    catch {
        throw new ApiError('STORAGE_UNAVAILABLE');
    }
}
function put(key: string, value: unknown): void {
    try {
        wx.setStorageSync(key, value);
    }
    catch {
        throw new ApiError('STORAGE_UNAVAILABLE');
    }
}
export function readDraft(store: string, kind = 'reservation'): Draft {
    const value = get<Draft>(storageKey(store, kind));
    return value ? { ...blank(), ...value } : blank();
}
export function saveDraft(store: string, value: Draft, kind = 'reservation'): void {
    if (pending(store, kind))
        throw new ApiError('PENDING_DIFFERENT_OPERATION');
    put(storageKey(store, kind), JSON.parse(JSON.stringify(value)));
}
export function clearDraft(store: string, kind = 'reservation'): void { put(storageKey(store, kind), blank()); }
export function addItem(store: string, item: Item): void {
    const value = readDraft(store);
    if (value.items.length >= 100)
        throw new ApiError('TOO_MANY_ITEMS');
    // Different units/specifications are never merged, even for the same catalog product.
    value.items.push(item);
    saveDraft(store, value);
}
export function pending(store: string, kind: string): Pending | undefined { return get<Pending>(storageKey(store, `${kind}.pending`)); }
const running = new Set<string>();
export async function mutate<T>(store: string, kind: string, path: string, method: Method, body: unknown): Promise<T> {
    needLogin();
    const slot = storageKey(store, `${kind}.pending`);
    if (running.has(slot))
        throw new ApiError('REQUEST_IN_PROGRESS');
    const existing = get<Pending>(slot);
    if (existing && (existing.path !== path || existing.method !== method))
        throw new ApiError('PENDING_DIFFERENT_OPERATION');
    const operation = existing || { path, method, body: JSON.parse(JSON.stringify(body)), key: makeKey() };
    // Persist BEFORE sending. A storage failure must not become an unrepeatable write.
    put(slot, operation);
    running.add(slot);
    const epoch = auth().generation;
    try {
        const result = await request<T>(operation.path, operation.method, operation.body, operation.key);
        if (auth().generation !== epoch)
            throw new ApiError('SESSION_CHANGED');
        return result; // Caller clears its draft before explicitly acknowledging the pending slot.
    }
    catch (e) {
        if (e instanceof ApiError && e.status >= 400 && e.status < 500 && ![401, 408, 429].includes(e.status))
            put(slot, null);
        throw e;
    }
    finally {
        running.delete(slot);
    }
}
export function finishMutation(store: string, kind: string): void { put(storageKey(store, `${kind}.pending`), null); }
