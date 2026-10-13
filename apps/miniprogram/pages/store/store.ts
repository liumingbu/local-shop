import { absolute, errorText, request, requireId } from '../../lib/client';
import { route, run } from '../../lib/ui';
import type { Store, Product, ListResult } from '../../lib/types';
Page({
    alive: true,
    data: { busy: false, error: '', storeId: '', store: null as (Store & {
            categories: {
                id: string;
                name: string;
            }[];
        }) | null,
        products: [] as (Product & {
            cover: string;
            supplyLabel: string;
        })[], category: '', page: 1, total: 0, logo: '' },
    onLoad(query: Record<string, string>) { try {
        this.setData({ storeId: requireId(query.store_id) });
        void this.load();
    }
    catch (e) {
        this.setData({ error: errorText(e) });
    } },
    onUnload() { this.alive = false; },
    load() {
        return run(this, async (commit) => {
            commit({ store: null, products: [], logo: '' });
            const id = this.data.storeId;
            const store = await request<Store & {
                categories: {
                    id: string;
                    name: string;
                }[];
            }>(`/api/v1/stores/${id}`);
            const list = await request<ListResult<Product>>(`/api/v1/stores/${id}/products?page=${this.data.page}&limit=20${this.data.category ? '&category_id=' + this.data.category : ''}`);
            commit({ store, logo: store.logo_url ? absolute(store.logo_url) : '', products: list.items.map(item => ({ ...item,
                    cover: item.images[0] ? absolute(item.images[0].url) : '', supplyLabel: ({ REGULAR: '常备', CONFIRM: '请先询货', UNAVAILABLE: '暂缺' } as Record<string, string>)[item.supply_status] })), total: list.total });
            try {
                const old = wx.getStorageSync('local-shop.recent') || [];
                wx.setStorageSync('local-shop.recent', [{ id, name: store.name }, ...(Array.isArray(old) ? old : []).filter(x => x.id !== id)].slice(0, 5));
            }
            catch { /* Browsing does not depend on saving recent stores. */ }
        });
    },
    category(event: WechatMiniprogram.TouchEvent) { if (this.data.busy)
        return; this.setData({ category: String(event.currentTarget.dataset.id || ''), page: 1 }); void this.load(); },
    previous() { if (this.data.busy || this.data.page <= 1)
        return; this.setData({ page: this.data.page - 1 }); void this.load(); },
    next() { if (this.data.busy || this.data.page * 20 >= this.data.total)
        return; this.setData({ page: this.data.page + 1 }); void this.load(); },
    product(event: WechatMiniprogram.TouchEvent) { route('product', this.data.storeId, '&product_id=' + requireId(event.currentTarget.dataset.id)); },
    inquiry() { route('compose', this.data.storeId, '&kind=inquiry'); },
    request() { route('compose', this.data.storeId, '&kind=reservation'); },
    records() { route('records', this.data.storeId); },
    onShareAppMessage() { return { title: this.data.store?.name || 'local-shop', path: `/pages/store/store?store_id=${this.data.storeId}` }; },
});
