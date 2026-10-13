import { auth, errorText, requireId } from './client';
export interface Screen {
    alive?: boolean;
    view?: number;
    data: {
        busy: boolean;
    };
    setData(data: Record<string, unknown>): void;
}
function alive(screen: Screen): boolean { return screen.alive !== false; }
export async function run(screen: Screen, action: (commit: (data: Record<string, unknown>) => void) => Promise<void>, sessionGuard = true): Promise<void> {
    if (screen.data.busy || !alive(screen))
        return;
    const current = auth().generation;
    const view = screen.view || 0;
    const commit = (data: Record<string, unknown>) => {
        if (alive(screen) && (screen.view || 0) === view && (!sessionGuard || current === auth().generation))
            screen.setData(data);
    };
    commit({ busy: true, error: '' });
    try {
        await action(commit);
    }
    catch (e) {
        commit({ error: errorText(e) });
    }
    finally {
        if (alive(screen) && (screen.view || 0) === view && (!sessionGuard || current === auth().generation))
            screen.setData({ busy: false });
    }
}
export function route(page: string, store: string, extra = ''): void {
    wx.navigateTo({ url: `/pages/${page}/${page}?store_id=${requireId(store)}${extra}` });
}
export const labels: Record<string, string> = {
    NEW: '待答复', REPLIED: '已答复', CLOSED: '已关闭', PENDING_CONFIRMATION: '待确认', CONFIRMED: '已确认',
    PREPARING: '备货中', READY: '待自提/配送', OUT_FOR_DELIVERY: '配送中', COMPLETED: '已完成', CANCELLED: '已取消',
    REQUESTED: '申请待处理', ACCEPTED: '商家同意取消', REJECTED: '商家未同意取消',
};
export function timeText(value?: string | null): string {
    if (!value)
        return '未确定';
    const time = new Date(value);
    if (Number.isNaN(time.getTime()))
        return '时间格式不可用';
    // Explicit UTC+08 display, independent of the device's own timezone.
    return new Date(time.getTime() + 8 * 3600000).toISOString().slice(0, 16).replace('T', ' ') + '（北京时间）';
}
export function quantityValid(value: string): boolean {
    return /^(?:0|[1-9]\d{0,8})(?:\.\d{1,3})?$/.test(value) && Number(value) > 0;
}
