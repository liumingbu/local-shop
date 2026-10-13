import { absolute, errorText, needLogin, request, requireId } from '../../lib/client';
import { addItem } from '../../lib/drafts';
import { quantityValid, route, run } from '../../lib/ui';
import type { Product } from '../../lib/types';
Page({
    alive: true, data: { busy: false, error: '', storeId: '', productId: '', product: null as Product | null, images: [] as string[], quantity: '1', notice: '' },
    onLoad(query: Record<string, string>) { try {
        this.setData({ storeId: requireId(query.store_id), productId: requireId(query.product_id) });
        void this.load();
    }
    catch (e) {
        this.setData({ error: errorText(e) });
    } },
    onUnload() { this.alive = false; },
    load() { return run(this, async (commit) => { commit({ product: null, images: [] }); const product = await request<Product>(`/api/v1/stores/${this.data.storeId}/products/${this.data.productId}`); commit({ product, images: product.images.map(x => absolute(x.url)) }); }); },
    quantity(event: WechatMiniprogram.Input) { this.setData({ quantity: event.detail.value, notice: '' }); },
    add() {
        try {
            needLogin();
            const p = this.data.product;
            if (!p || !quantityValid(this.data.quantity))
                throw new Error('invalid quantity');
            addItem(this.data.storeId, { product_id: p.id, name: p.name, quantity: this.data.quantity, unit: p.unit, spec: p.spec });
            this.setData({ notice: '已加入本店需求草稿，尚未提交', error: '' });
        }
        catch (e) {
            this.setData({ error: e instanceof Error && e.message === 'invalid quantity' ? '数量须大于0，最多3位小数' : errorText(e) });
        }
    },
    inquiry() { route('compose', this.data.storeId, '&kind=inquiry&product_id=' + this.data.productId); },
    cart() { route('compose', this.data.storeId, '&kind=reservation'); },
});
