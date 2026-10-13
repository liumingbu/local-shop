import { auth, ApiError, errorText, needLogin, request, requireId } from '../../lib/client';
import { clearDraft, finishMutation, mutate, pending, readDraft, saveDraft } from '../../lib/drafts';
import { chooseAndUpload } from '../../lib/media';
import { quantityValid, run } from '../../lib/ui';
import type { Draft, RecordData, Store } from '../../lib/types';
Page({
    alive: true, view: 0,
    data: { busy: false, error: '', storeId: '', kind: 'reservation', initialProduct: '', store: null as Store | null, owner: '', locked: false,
        draft: null as Draft | null, consent: false, methodLabels: ['自提意向', '配送意向'], methodIndex: 0, done: false },
    onLoad(query: Record<string, string>) {
        try {
            const storeId = requireId(query.store_id);
            const kind = query.kind === 'inquiry' ? 'inquiry' : 'reservation';
            this.setData({ storeId, kind, initialProduct: query.product_id ? requireId(query.product_id) : '' });
            this.restore();
            if (this.data.draft) void this.loadStore();
        }
        catch (e) {
            this.setData({ error: errorText(e) });
        }
    },
    onShow() { this.alive = true; if (this.data.storeId) {
        this.restore();
        if (this.data.draft && !this.data.store) void this.loadStore();
    } },
    onHide() { this.view++; this.alive = false; this.setData({ busy: false, draft: null }); },
    onUnload() { this.alive = false; },
    restore() {
        try {
            needLogin();
            const draft = readDraft(this.data.storeId, this.data.kind);
            if (this.data.kind === 'inquiry' && this.data.initialProduct && !pending(this.data.storeId, this.data.kind)) {
                if (draft.product_id && draft.product_id !== this.data.initialProduct)
                    throw new ApiError('OTHER_PRODUCT_DRAFT_EXISTS');
                if (!draft.product_id) {
                    draft.product_id = this.data.initialProduct;
                    saveDraft(this.data.storeId, draft, this.data.kind);
                }
            }
            this.setData({ draft, owner: auth().userId,
                consent: draft.privacy_accepted, locked: !!pending(this.data.storeId, this.data.kind), methodIndex: draft.fulfillment_method === 'DELIVERY' ? 1 : 0 });
        }
        catch (e) {
            this.setData({ draft: null, error: errorText(e) });
        }
    },
    loadStore() { return run(this, async (commit) => { const store = await request<Store>(`/api/v1/stores/${this.data.storeId}`); commit({ store }); }); },
    persist(draft: Draft) { try {
        saveDraft(this.data.storeId, draft, this.data.kind);
        this.setData({ draft, error: '' });
    }
    catch (e) {
        this.setData({ error: errorText(e) });
    } },
    input(event: WechatMiniprogram.Input) {
        if (this.data.busy || this.data.locked || !this.data.draft)
            return;
        const field = String(event.currentTarget.dataset.field);
        if (!['raw_text', 'customer_label', 'expected_time_note'].includes(field))
            return;
        this.persist({ ...this.data.draft, [field]: event.detail.value });
    },
    quantity(event: WechatMiniprogram.Input) {
        if (this.data.busy || this.data.locked || !this.data.draft)
            return;
        const index = Number(event.currentTarget.dataset.index);
        const items = this.data.draft.items.map((x, i) => i === index ? { ...x, quantity: event.detail.value } : x);
        this.persist({ ...this.data.draft, items });
    },
    remove(event: WechatMiniprogram.TouchEvent) {
        if (this.data.busy || this.data.locked || !this.data.draft)
            return;
        const index = Number(event.currentTarget.dataset.index);
        this.persist({ ...this.data.draft, items: this.data.draft.items.filter((_, i) => i !== index) });
    },
    removeImage(event: WechatMiniprogram.TouchEvent) {
        if (this.data.busy || this.data.locked || !this.data.draft)
            return;
        this.persist({ ...this.data.draft, media_ids: this.data.draft.media_ids.filter(x => x !== event.currentTarget.dataset.id) });
    },
    method(event: WechatMiniprogram.PickerChange) {
        if (this.data.busy || this.data.locked || !this.data.draft)
            return;
        const index = Number(event.detail.value);
        this.persist({ ...this.data.draft, fulfillment_method: index === 1 ? 'DELIVERY' : 'PICKUP' });
        this.setData({ methodIndex: index });
    },
    date(event: WechatMiniprogram.PickerChange) { if (this.data.busy || this.data.locked || !this.data.draft)
        return; this.persist({ ...this.data.draft, expected_date: String(event.detail.value) }); },
    clock(event: WechatMiniprogram.PickerChange) { if (this.data.busy || this.data.locked || !this.data.draft)
        return; this.persist({ ...this.data.draft, expected_clock: String(event.detail.value) }); },
    consent(event: WechatMiniprogram.CheckboxGroupChange) {
        if (this.data.busy || this.data.locked || !this.data.draft)
            return;
        const accepted = event.detail.value.includes('accepted');
        this.persist({ ...this.data.draft, privacy_accepted: accepted });
        this.setData({ consent: accepted });
    },
    upload() {
        return run(this, async (commit) => {
            const view = this.view;
            needLogin();
            const draft = this.data.draft;
            if (!draft || this.data.locked)
                throw new ApiError('PENDING_DIFFERENT_OPERATION');
            if (!draft.privacy_accepted)
                throw new ApiError('PRIVACY_CONSENT_REQUIRED');
            if (draft.media_ids.length >= 5)
                throw new ApiError('MAX_FIVE_IMAGES');
            const image = await chooseAndUpload(`/api/v1/stores/${this.data.storeId}/private-media?privacy_accepted=true`,()=>this.alive&&this.view===view);
            if (!this.alive || this.view !== view)
                return;
            const updated = { ...draft, media_ids: [...draft.media_ids, image.id] };
            saveDraft(this.data.storeId, updated, this.data.kind);
            commit({ draft: updated });
        });
    },
    submit() {
        return run(this, async (commit) => {
            const view = this.view;
            needLogin();
            if (this.data.done)
                return;
            const draft = this.data.draft;
            if (!draft)
                throw new ApiError('EMPTY_DRAFT');
            const existing = pending(this.data.storeId, this.data.kind);
            if (!existing) {
                if (!draft.privacy_accepted)
                    throw new ApiError('PRIVACY_CONSENT_REQUIRED');
                if (!draft.raw_text.trim() && !draft.items.length && !draft.media_ids.length && !draft.product_id)
                    throw new ApiError('EMPTY_DRAFT');
                if (draft.items.some(x => !quantityValid(x.quantity)))
                    throw new ApiError('INVALID_QUANTITY');
            }
            let body: Record<string, unknown> = { raw_text: draft.raw_text, privacy_accepted: true, media_ids: draft.media_ids };
            if (this.data.kind === 'inquiry') {
                if (draft.product_id)
                    body.product_id = draft.product_id;
            }
            else {
                body = { ...body, customer_label: draft.customer_label, items: draft.items, fulfillment_method: draft.fulfillment_method,
                    expected_time_note: [draft.expected_date && !draft.expected_clock ? draft.expected_date : '', draft.expected_time_note].filter(Boolean).join(' ') };
                if (draft.expected_date && draft.expected_clock) {
                    if (!/^\d{4}-\d{2}-\d{2}$/.test(draft.expected_date) || !/^\d{2}:\d{2}$/.test(draft.expected_clock))
                        throw new ApiError('INVALID_TIME');
                    body.expected_at = new Date(`${draft.expected_date}T${draft.expected_clock}:00+08:00`).toISOString();
                }
            }
            const suffix = this.data.kind === 'inquiry' ? 'inquiries' : 'reservations';
            let result: RecordData;
            try {
                result = await mutate<RecordData>(this.data.storeId, this.data.kind, `/api/v1/stores/${this.data.storeId}/${suffix}`, 'POST', body);
            }
            finally {
                commit({ locked: !!pending(this.data.storeId, this.data.kind) });
            }
            if (!this.alive || this.view !== view)
                return;
            clearDraft(this.data.storeId, this.data.kind);
            finishMutation(this.data.storeId, this.data.kind);
            commit({ done: true, locked: false });
            wx.redirectTo({ url: `/pages/detail/detail?store_id=${this.data.storeId}&kind=${this.data.kind}&record_id=${result.id}` });
        });
    },
    discard() {
        if (!this.data.storeId || !auth().authenticated) return;
        if (this.data.busy || pending(this.data.storeId, this.data.kind))
            return;
        wx.showModal({ title: '放弃本店未提交草稿？', content: '只清空当前身份、本店、本类草稿；已上传图片不物理删除。', success: result => {
                if (!result.confirm)
                    return;
                try {
                    clearDraft(this.data.storeId, this.data.kind);
                    this.restore();
                }
                catch (e) {
                    this.setData({ error: errorText(e) });
                }
            } });
    },
    privacy() { wx.navigateTo({ url: '/pages/privacy/privacy' }); },
    home() { wx.navigateTo({ url: '/pages/index/index' }); },
});
