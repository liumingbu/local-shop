import { config } from '../config';
export class ApiError extends Error {
    constructor(public code: string, public status = 0) { super(code); }
}
export type Method = 'GET' | 'POST' | 'PUT';
let token = '';
let userId = '';
let identity = '';
let generation = 0;
let sequence = 0;
export function auth() { return { userId, identity, generation, authenticated: !!token && !!userId }; }
export function logout() { generation++; token = ''; userId = ''; identity = ''; }
export function validId(value: unknown): value is string {
    return typeof value === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
}
export function requireId(value: unknown): string {
    if (!validId(value))
        throw new ApiError('INVALID_STORE_OR_RECORD');
    return value.toLowerCase();
}
export function developmentAllowed(): boolean {
    return config.enableDevelopmentLogin && wx.getAccountInfoSync().miniProgram.envVersion === 'develop'
        && /^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/.test(config.apiOrigin);
}
export function origin(): string {
    const value = config.apiOrigin.replace(/\/$/, '');
    if (/^https:\/\/[a-z0-9.-]+(:\d+)?$/i.test(value))
        return value;
    if (wx.getAccountInfoSync().miniProgram.envVersion === 'develop'
        && /^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/.test(value))
        return value;
    throw new ApiError('API_NOT_CONFIGURED');
}
export function absolute(path: string): string {
    if (!path.startsWith('/api/v1/') || path.includes('..') || path.includes('://') || path.includes('\\')) {
        throw new ApiError('INVALID_API_PATH');
    }
    return origin() + path;
}
export function makeKey(): string { sequence++; return `mini.${Date.now()}.${sequence}.${Math.random().toString(36).slice(2)}`; }
export function request<T>(path: string, method: Method = 'GET', body?: unknown, key?: string, contentType = 'application/json'): Promise<T> {
    const current = generation;
    return new Promise<T>((resolve, reject) => {
        let url: string;
        try {
            url = absolute(path);
        }
        catch (e) {
            reject(e);
            return;
        }
        wx.request<WechatMiniprogram.IAnyObject>({
            url, method, timeout: 10000, redirect: 'manual',
            header: { 'Content-Type': contentType, ...(token ? { Authorization: `Bearer ${token}` } : {}),
                ...(key ? { 'Idempotency-Key': key } : {}) },
            ...(body === undefined ? {} : { data: body as WechatMiniprogram.IAnyObject | ArrayBuffer }),
            success(result) {
                if (generation !== current) {
                    reject(new ApiError('SESSION_CHANGED'));
                    return;
                }
                if (result.statusCode >= 200 && result.statusCode < 300)
                    resolve(result.data as T);
                else
                    reject(new ApiError(String(result.data?.code || `HTTP_${result.statusCode}`), result.statusCode));
            },
            fail() { reject(new ApiError(generation === current ? 'NETWORK_UNCERTAIN' : 'SESSION_CHANGED')); },
        });
    });
}
export async function login(alias: string): Promise<void> {
    if (!developmentAllowed())
        throw new ApiError('WECHAT_LOGIN_NOT_CONFIGURED');
    if (!['merchant-a', 'merchant-b', 'customer-a', 'customer-b'].includes(alias))
        throw new ApiError('INVALID_IDENTITY');
    logout();
    const current = generation;
    try {
        const session = await request<{
            access_token: string;
        }>('/api/v1/dev/session', 'POST', { identity: alias });
        if (current !== generation)
            throw new ApiError('SESSION_CHANGED');
        token = session.access_token;
        const me = await request<{
            user_id: string;
        }>('/api/v1/dev/me');
        userId = requireId(me.user_id);
        identity = alias;
    }
    catch (e) {
        if (current === generation)
            logout();
        throw e;
    }
}
export function needLogin(): void { if (!auth().authenticated)
    throw new ApiError('LOGIN_REQUIRED'); }
export function errorText(error: unknown): string {
    if (!(error instanceof ApiError))
        return '操作未完成，请稍后重试';
    const texts: Record<string, string> = {
        INVALID_SORT_ORDER: '排序须为0至100000的整数', INVALID_REFERENCE_PRICE: '参考价格须非负且最多2位小数；也可留空', SAVE_PRODUCT_FIRST: '请先保存商品并核对当前版本', TOO_MANY_IMAGES: '每件商品最多8张图片', OPERATION_CANCELLED: '页面已离开，本次上传未继续发送', CATEGORY_LIMIT_REQUIRES_WEB: '分类过多，请改用后台维护',
        NO_MERCHANT_MEMBERSHIP: '当前账号没有商户成员资格', OWNER_REQUIRED: '只有店主可以维护店铺资料', TENANT_NOT_FOUND: '该店铺不在当前账号授权范围', DATE_REQUIRED: '设置时刻前请先选择日期',
        OTHER_PRODUCT_DRAFT_EXISTS: '本店已有另一商品的询货草稿，请先处理或明确放弃原草稿',
        PRIVACY_CONSENT_REQUIRED: '请先阅读并确认开发隐私说明', INVALID_QUANTITY: '数量须大于0，最多3位小数',
        EMPTY_DRAFT: '请填写需求、选择商品或上传图片', IMAGE_OVER_2M: '压缩后图片仍超过2MiB，请换用较小图片',
        IMAGE_SELECTION_CANCELLED: '已取消选择图片，草稿保持不变',
        API_NOT_CONFIGURED: '尚未配置本项目API，当前不能连接服务', LOGIN_REQUIRED: '请先在入口选择受控开发身份',
        WECHAT_LOGIN_NOT_CONFIGURED: '真实微信登录尚未配置，不能提交；可先浏览店铺',
        INVALID_STORE_OR_RECORD: '店铺或记录参数无效，请重新从本店入口进入',
        NETWORK_UNCERTAIN: '网络结果未确认。请重试原请求，不要重复新建',
        SESSION_CHANGED: '身份已切换，旧请求结果已丢弃', VERSION_CONFLICT: '记录已有更新，请刷新后再操作',
        EXPLICIT_RECONFIRMATION_REQUIRED: '确认内容有修订，请查看最新版本并明确重新确认',
        CANCELLATION_REVIEW_REQUIRED: '有待处理取消申请，需先处理后再推进',
        STORAGE_UNAVAILABLE: '本机草稿保存失败，尚未发出请求，请检查小程序存储空间',
        PENDING_DIFFERENT_OPERATION: '有结果未确认的原请求，请先重试原请求',
    };
    if (texts[error.code])
        return texts[error.code];
    if (error.status === 401)
        return '登录已失效，请重新登录；草稿和原请求保留';
    if (error.status === 404)
        return '店铺/记录不可访问，可能已停用或不属于当前身份';
    return `操作未完成：${error.code}`;
}
export function privateImage(path: string): Promise<string> {
    needLogin();
    const current = generation;
    return new Promise((resolve, reject) => {
        wx.downloadFile({ url: absolute(path), timeout: 10000, header: { Authorization: `Bearer ${token}` },
            success(result) {
                if (generation !== current) {
                    reject(new ApiError('SESSION_CHANGED'));
                    return;
                }
                if (result.statusCode === 200)
                    resolve(result.tempFilePath);
                else
                    reject(new ApiError(`IMAGE_HTTP_${result.statusCode}`, result.statusCode));
            }, fail() { reject(new ApiError('IMAGE_UNAVAILABLE')); },
        });
    });
}
