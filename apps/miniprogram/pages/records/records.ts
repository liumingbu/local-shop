import { auth, errorText, needLogin, request, requireId } from '../../lib/client';
import { labels, route, run, timeText } from '../../lib/ui';
import type { ListResult, RecordData } from '../../lib/types';
Page({ alive: true, view: 0,
    data: { busy: false, error: '', storeId: '', kind: 'reservation', page: 1, total: 0, owner: '', items: [] as (RecordData & {
            label: string;
            time: string;
        })[] },
    onLoad(query: Record<string, string>) { try {
        this.setData({ storeId: requireId(query.store_id) });
        void this.load();
    }
    catch (e) {
        this.setData({ error: errorText(e) });
    } },
    onShow() { this.alive = true; if (this.data.storeId) {
        if (this.data.owner !== auth().userId)
            this.setData({ items: [], total: 0, page: 1 });
        void this.load();
    } },
    onHide() { this.view++; this.alive = false; this.setData({ busy: false, items: [] }); },
    onUnload() { this.alive = false; },
    load() {
        return run(this, async (commit) => {
            needLogin();
            commit({ owner: auth().userId, items: [] });
            const list = await request<ListResult<RecordData>>(`/api/v1/me/records?store_id=${this.data.storeId}&kind=${this.data.kind}&page=${this.data.page}&limit=20`);
            commit({ items: list.items.map(x => ({ ...x, label: labels[x.status] || x.status, time: timeText(x.created_at) })), total: list.total });
        });
    },
    tab(event: WechatMiniprogram.TouchEvent) { if (this.data.busy)
        return; this.setData({ kind: event.currentTarget.dataset.kind === 'inquiry' ? 'inquiry' : 'reservation', page: 1, items: [] }); void this.load(); },
    previous() { if (this.data.busy || this.data.page <= 1)
        return; this.setData({ page: this.data.page - 1 }); void this.load(); },
    next() { if (this.data.busy || this.data.page * 20 >= this.data.total)
        return; this.setData({ page: this.data.page + 1 }); void this.load(); },
    open(event: WechatMiniprogram.TouchEvent) { route('detail', this.data.storeId, `&kind=${this.data.kind}&record_id=${requireId(event.currentTarget.dataset.id)}`); },
    home() { wx.navigateTo({ url: '/pages/index/index' }); },
});
