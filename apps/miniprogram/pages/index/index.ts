import { auth, developmentAllowed, errorText, login, logout, requireId, validId } from '../../lib/client';
import { run } from '../../lib/ui';
Page({
    alive: true, view: 0,
    data: { busy: false, error: '', storeInput: '', identity: '未登录', devAllowed: false, aliasIndex: 0,
        aliases: ['customer-a', 'customer-b', 'merchant-a', 'merchant-b'], recent: [] as {
            id: string;
            name: string;
        }[] },
    onLoad(query: Record<string, string>) {
        this.setData({ devAllowed: developmentAllowed() });
        if (Object.prototype.hasOwnProperty.call(query, 'store_id') || query.scene !== undefined) {
            try {
                const target = query.store_id !== undefined ? query.store_id : decodeURIComponent(query.scene);
                const id = requireId(target);
                wx.redirectTo({ url: `/pages/store/store?store_id=${id}` });
            }
            catch (e) {
                this.setData({ error: errorText(e) });
            }
        }
    },
    onShow() {
        this.alive = true;
        this.setData({ identity: auth().identity || '未登录', devAllowed: developmentAllowed() });
        try {
            const stored = wx.getStorageSync('local-shop.recent') || [];
            this.setData({ recent: Array.isArray(stored) ? stored.filter(x => validId(x.id)).slice(0, 5) : [] });
        }
        catch {
            this.setData({ recent: [] });
        }
    },
    onHide() { this.view++; this.alive = false; if (this.data.busy) logout(); this.setData({busy:false}); },
    onUnload() { if (this.data.busy) logout(); this.alive = false; },
    invitations(){wx.navigateTo({url:'/pages/invitations/invitations'});},
    workbench(){wx.navigateTo({url:'/pages/merchant/merchant'});},
    input(event: WechatMiniprogram.Input) { this.setData({ storeInput: event.detail.value }); },
    chooseIdentity(event: WechatMiniprogram.PickerChange) { this.setData({ aliasIndex: Number(event.detail.value) }); },
    signIn() { return run(this, async (commit) => { await login(this.data.aliases[this.data.aliasIndex]); commit({ identity: auth().identity }); }, false); },
    signOut() { if (this.data.busy)
        return; logout(); this.setData({ identity: '未登录' }); },
    enter(event?: WechatMiniprogram.TouchEvent) {
        try {
            if (!event?.currentTarget.dataset.id && !developmentAllowed()) throw new Error('DEVELOPMENT_ENTRY_DISABLED');
            const id = requireId(event?.currentTarget.dataset.id || this.data.storeInput.trim());
            wx.navigateTo({ url: `/pages/store/store?store_id=${id}` });
        }
        catch (e) {
            this.setData({ error: errorText(e) });
        }
    },
});
