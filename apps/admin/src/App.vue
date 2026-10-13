<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue';
import { checkHealth } from './api';
const message = ref('尚未检查 API');
const loading = ref(false);
let controller: AbortController | undefined;
async function check() {
  if (loading.value) return;
  controller = new AbortController();
  loading.value = true;
  const timeout = setTimeout(() => controller?.abort(), 5000);
  try { message.value = await checkHealth(controller.signal); }
  catch { message.value = '检查失败，请确认 API 已启动后重试'; }
  finally { clearTimeout(timeout); loading.value = false; }
}
onBeforeUnmount(() => controller?.abort());
</script>
<template>
  <main>
    <p class="tag">local-shop · 工程初始化</p>
    <h1>店铺工作台</h1>
    <p>当前仅提供工程健康检查，记单、商品与店铺业务尚未实现。</p>
    <button :disabled="loading" @click="check">{{ loading ? '检查中…' : '检查 API' }}</button>
    <p role="status" aria-live="polite">{{ message }}</p>
    <aside>真实 PostgreSQL 集成与微信真机能力尚未验证。</aside>
  </main>
</template>
<style>
:root { font-family: system-ui, sans-serif; color: #203c37; background: #f6f4ef; }
main { max-width: 640px; margin: 8vh auto; padding: 28px; }
h1 { font-size: 36px; } p { line-height: 1.8; }
.tag { color: #54786b; } button { background: #206858; color: white; border: 0; border-radius: 10px; padding: 14px 24px; cursor: pointer; }
button:disabled { opacity: .55; cursor: wait; } aside { margin-top: 36px; color: #6b716e; }
</style>
