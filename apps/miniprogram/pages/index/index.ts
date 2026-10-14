import { auth, developmentAllowed, errorText, login, logout, wechatSignIn, signOutSession, request, ApiError, requireId, validId } from '../../lib/client';
import { run } from '../../lib/ui';
Page({
    alive: true, view: 0,
    data: { busy: false, error: '', storeInput: '', identity: '未登录', devAllowed: false, aliasIndex: 0,
        capabilities:'',approvalCode:'',approvalConfirmed:false,
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
    onHide() { this.view++; this.alive = false; if (this.data.busy) logout(); this.setData({busy:false,approvalCode:'',approvalConfirmed:false}); },
    onUnload() { if (this.data.busy) logout(); this.alive = false; },
    capabilities(){return run(this,async commit=>{const value=await request<{wechat_login_configured:boolean}>('/api/v1/capabilities');commit({capabilities:`登录配置：${value.wechat_login_configured?'服务端已配置（不等于真机通过）':'未配置'}；真实二维码/订阅消息未配置，隐私说明仍为开发草案。`});},false);},
    invitations(){wx.navigateTo({url:'/pages/invitations/invitations'});},
    workbench(){wx.navigateTo({url:'/pages/merchant/merchant'});},
    input(event: WechatMiniprogram.Input) { this.setData({ storeInput: event.detail.value }); },
    chooseIdentity(event: WechatMiniprogram.PickerChange) { this.setData({ aliasIndex: Number(event.detail.value) }); },
    signIn() { return run(this, async (commit) => { await login(this.data.aliases[this.data.aliasIndex]); commit({ identity: auth().identity }); }, false); },
    wechatLogin(){return run(this,async commit=>{await wechatSignIn();commit({identity:auth().identity});},false);},
    signOut(){return run(this,async commit=>{try{await signOutSession();}finally{commit({identity:'未登录'});}},false);},
    approvalInput(event:WechatMiniprogram.Input){if(!this.data.busy)this.setData({approvalCode:event.detail.value.trim().toUpperCase(),approvalConfirmed:false});},
    approvalCheck(event:WechatMiniprogram.CheckboxGroupChange){if(!this.data.busy)this.setData({approvalConfirmed:event.detail.value.includes('confirmed')});},
    approveBrowser(){return run(this,async commit=>{if(!this.data.approvalConfirmed)throw new ApiError('EXPLICIT_RECONFIRMATION_REQUIRED');await request('/api/v1/auth/browser-approvals/confirm','POST',{code:this.data.approvalCode,confirmed:true});commit({approvalCode:'',approvalConfirmed:false,identity:auth().identity});});},
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
