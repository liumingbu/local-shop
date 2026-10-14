/** Configure a verified API origin before developer-tool testing. No credentials belong here. */
export const config: {
    apiOrigin: string;
    enableDevelopmentLogin: boolean;
    enableWechatLogin: boolean;
} = {
    apiOrigin: '',
    enableDevelopmentLogin: false,
    enableWechatLogin: false,
};
