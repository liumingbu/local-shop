import {defineConfig} from 'vitest/config';
import vue from '@vitejs/plugin-vue';
export default defineConfig({plugins:[vue()],test:{include:['tests/dom-live/**/*.test.ts'],environment:'jsdom',environmentOptions:{jsdom:{url:'http://localhost',pretendToBeVisual:true}},pool:'threads',maxWorkers:1,fileParallelism:false,testTimeout:30000}});
