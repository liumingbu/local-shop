import { auth, ApiError, errorText, needLogin, privateImage, request, requireId } from '../../lib/client';
import { finishMutation, mutate, pending } from '../../lib/drafts';
import { labels, route, run, timeText } from '../../lib/ui';
import type { RecordData } from '../../lib/types';
function present(row: RecordData) {
    const requests = row.cancellation_requests || [];
    return { row, label: labels[row.status] || row.status, time: timeText(row.created_at), expected: timeText(row.expected_at),
        canCancel: !['CANCELLED', 'COMPLETED'].includes(row.status) && !requests.some(x => x.status === 'REQUESTED'),
        cancellations: requests.map(x => ({ ...x, label: labels[x.status] || x.status })),
        revisions: (row.confirmation_revisions || []).map((x, index, array) => ({ ...x,
            label: x.confirmed_version ? '已由商户记录确认' : index === array.length - 1 ? '当前待确认候选' : '已被新候选替代',
            fulfillment: timeText(x.details.fulfillment_at), confirmed: timeText(x.confirmed_at) })),
        events: (row.events || []).map(x => ({ ...x, label: labels[x.to_status] || x.to_status, time: timeText(x.created_at), actionLabel: ({
                CANCELLATION_REQUESTED: '提交取消意向', CANCELLATION_ACCEPTED: '商家同意取消', CANCELLATION_REJECTED: '商家未同意取消',
                CONFIRMATION_PROPOSED: '更新确认候选', STATUS_CHANGED: '状态变更', CREATED: '创建', REPLIED: '商家答复', CLOSED: '关闭询货', CONVERTED: '明确转为需求',
            } as Record<string, string>)[x.action || ''] || '状态记录' })),
    };
}
Page({ alive: true, view: 0,
    data: { busy: false, error: '', storeId: '', recordId: '', kind: 'reservation', owner: '', row: null as RecordData | null,
        label: '', time: '', expected: '', reason: '', canCancel: false, locked: false, cancellations: [] as unknown[], revisions: [] as unknown[], events: [] as unknown[], images: [] as {
            id: string;
            path: string;
        }[] },
    onLoad(query: Record<string, string>) { try {
        this.setData({ storeId: requireId(query.store_id), recordId: requireId(query.record_id), kind: query.kind === 'inquiry' ? 'inquiry' : 'reservation' });
        void this.load();
    }
    catch (e) {
        this.setData({ error: errorText(e) });
    } },
    onShow() { this.alive = true; if (this.data.recordId) {
        if (this.data.owner !== auth().userId)
            this.setData({ row: null, images: [], reason: '' });
        void this.load();
    } },
    onHide() { this.view++; this.alive = false; this.setData({ busy: false, row: null, images: [], revisions: [], events: [], cancellations: [] }); },
    onUnload() { this.alive = false; },
    async fetchRecord() {
        const row = await request<RecordData>(`/api/v1/me/records/${this.data.kind}/${this.data.recordId}`);
        if (row.tenant_id !== this.data.storeId)
            throw new ApiError('INVALID_STORE_OR_RECORD');
        return row;
    },
    load() {
        return run(this, async (commit) => {
            needLogin();
            commit({ owner: auth().userId, row: null, images: [] });
            const row = await this.fetchRecord();
            commit({ ...present(row), locked: !!pending(this.data.storeId, `cancel-${row.id}`) });
            const images = await Promise.all(row.attachments.map(async (image) => ({ id: image.id, path: await privateImage(image.url).catch(() => '') })));
            commit({ images });
        });
    },
    reason(event: WechatMiniprogram.Input) { if (!this.data.busy && !this.data.locked)
        this.setData({ reason: event.detail.value }); },
    cancel() {
        return run(this, async (commit) => {
            needLogin();
            const row = this.data.row;
            if (!row)
                throw new ApiError('RECORD_NOT_FOUND');
            const view = this.view;
            const slot = `cancel-${row.id}`;
            if (!pending(this.data.storeId, slot) && !this.data.reason.trim())
                throw new ApiError('CANCELLATION_REASON_REQUIRED');
            try {
                await mutate(this.data.storeId, slot, `/api/v1/me/reservations/${row.id}/cancellation-requests`, 'POST', { expected_version: row.version, reason: this.data.reason });
            }
            finally {
                commit({ locked: !!pending(this.data.storeId, slot) });
            }
            if (!this.alive || view !== this.view)
                return;
            const fresh = await this.fetchRecord();
            finishMutation(this.data.storeId, slot);
            commit({ ...present(fresh), reason: '', locked: false });
        });
    },
    converted() { const id = this.data.row?.converted_reservation_id; if (id)
        route('detail', this.data.storeId, '&kind=reservation&record_id=' + requireId(id)); },
    records() { route('records', this.data.storeId); },
    home() { wx.navigateTo({ url: '/pages/index/index' }); },
});
