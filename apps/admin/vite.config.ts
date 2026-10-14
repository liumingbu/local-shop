import { defineConfig, loadEnv } from 'vite';
import vue from '@vitejs/plugin-vue';
export default defineConfig(({mode})=>{
  const target=loadEnv(mode,'.','LOCAL_SHOP_').LOCAL_SHOP_API_TARGET||'http://127.0.0.1:8000';
  if(!/^http:\/\/127\.0\.0\.1:\d+$/.test(target))throw Error('Development proxy must target explicit loopback');
  return {plugins:[vue()],server:{host:'127.0.0.1',proxy:{'/health':target,'/api':target}}};
});
