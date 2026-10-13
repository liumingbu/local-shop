import { ApiError, auth, makeKey, needLogin, request } from './client';
export async function chooseAndUpload(path: string, isCurrent:()=>boolean=()=>true): Promise<{
    id: string;
}> {
    needLogin();
    const epoch=auth().generation;
    const current=()=>{if(epoch!==auth().generation)throw new ApiError('SESSION_CHANGED');if(!isCurrent())throw new ApiError('OPERATION_CANCELLED');};
    const selected = await new Promise<string>((resolve, reject) => wx.chooseMedia({
        count: 1, mediaType: ['image'], sourceType: ['album', 'camera'], sizeType: ['compressed'],
        success: result => resolve(result.tempFiles[0].tempFilePath),
        fail: () => reject(new ApiError('IMAGE_SELECTION_CANCELLED')),
    }));
    current();
    const file = await new Promise<string>((resolve, reject) => wx.compressImage({
        src: selected, quality: 75, compressedWidth: 1600,
        success: result => resolve(result.tempFilePath), fail: () => reject(new ApiError('IMAGE_COMPRESSION_FAILED')),
    }));
    current();
    const bytes = await new Promise<ArrayBuffer>((resolve, reject) => wx.getFileSystemManager().readFile({
        filePath: file, success: result => typeof result.data === 'string' ? reject(new ApiError('INVALID_IMAGE')) : resolve(result.data),
        fail: () => reject(new ApiError('IMAGE_READ_FAILED')),
    }));
    current();
    if (bytes.byteLength > 2 * 1024 * 1024)
        throw new ApiError('IMAGE_OVER_2M');
    const signature = new Uint8Array(bytes);
    const mime = signature[0] === 0xff && signature[1] === 0xd8 ? 'image/jpeg'
        : signature[0] === 0x89 && signature[1] === 0x50 ? 'image/png'
            : signature[0] === 0x52 && signature[1] === 0x49 ? 'image/webp' : '';
    if (!mime)
        throw new ApiError('INVALID_IMAGE');
    return request<{
        id: string;
    }>(path, 'POST', bytes, makeKey(), mime);
}
