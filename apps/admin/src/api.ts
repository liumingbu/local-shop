export async function checkHealth(signal: AbortSignal): Promise<string> {
  const response = await fetch('/health/live', {signal});
  if (!response.ok) throw new Error('API 暂不可用');
  const body: unknown = await response.json();
  if (!body || typeof body !== 'object' || !('status' in body) || body.status !== 'ok') {
    throw new Error('API 响应不符合约定');
  }
  return 'API 存活检查通过（不代表数据库已就绪）';
}
