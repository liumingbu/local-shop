import { test, expect } from '@playwright/test';
test('老板A完整闭环、关闭历史、切换B隔离、重复点击', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', {name:'进入工作台'}).click();
  await expect(page.getByRole('heading', {name:'合成演示店1'})).toBeVisible();
  await page.getByText('店铺资料与公开设置', {exact:true}).click();
  await page.getByLabel('店名', {exact:true}).fill('演示店 A');
  await page.getByRole('button', {name:'保存店铺'}).click();
  await page.getByLabel('顾客称呼', {exact:true}).fill('自动测试顾客甲');
  await page.getByLabel('原始需求', {exact:true}).fill('半斤干贝，分两袋。周三下午自提。');
  await page.getByRole('button', {name:'保存需求', exact:true}).dblclick();
  const card = page.locator('article').filter({hasText:'自动测试顾客甲'});
  await expect(card).toHaveCount(1);
  for (const status of ['已确认','备货中','待取/送','已完成']) {
    await card.getByRole('button', {name:status, exact:true}).click();
    await expect(card.locator('.badge')).toHaveText(status);
  }
  await card.getByRole('button', {name:'查看详情与历史'}).click();
  const history=page.getByRole('region',{name:'处理详情'});
  await expect(history.locator('li')).toHaveCount(5);
  await page.getByRole('button', {name:'关闭详情'}).click();
  await expect(history).toHaveCount(0);
  await page.getByLabel('演示身份').selectOption('merchant-b');
  await page.getByRole('button', {name:'进入工作台'}).click();
  await expect(page.getByRole('heading', {name:'合成演示店2'})).toBeVisible();
  await expect(page.locator('article')).toHaveCount(0);
  await expect(page.getByLabel('原始需求', {exact:true})).toHaveValue('');
  await page.getByLabel('演示身份').selectOption('merchant-a');
  await page.getByRole('button', {name:'进入工作台'}).click();
  await expect(card).toHaveCount(1);
  await expect(page.getByLabel('店名',{exact:true})).toHaveValue('演示店 A');
});

test('请求失败保留草稿和幂等键，重试后仅一单', async ({page}) => {
  await page.goto('/');await page.getByRole('button',{name:'进入工作台'}).click();
  await page.getByLabel('顾客称呼',{exact:true}).fill('网络恢复顾客');
  await page.getByLabel('原始需求',{exact:true}).fill('保留这段原始需求');
  let firstKey='';let calls=0;
  await page.route('**/api/v1/merchant/tenants/*/reservations',async route => {
    if (route.request().method()!=='POST') return route.continue();
    calls++;
    if(calls===1){firstKey=route.request().headers()['idempotency-key'];return route.abort();}
    expect(route.request().headers()['idempotency-key']).toBe(firstKey);
    return route.continue();
  });
  await page.getByRole('button',{name:'保存需求',exact:true}).click();
  await expect(page.getByRole('alert')).toContainText('结果未确认');
  await expect(page.getByLabel('原始需求',{exact:true})).toHaveValue('保留这段原始需求');
  await page.getByRole('button',{name:'重试原提交',exact:true}).click();
  await expect(page.locator('article').filter({hasText:'网络恢复顾客'})).toHaveCount(1);
});

test('浏览器刷新后需重新选择身份，不泄露旧记录', async ({page}) => {
  await page.goto('/');await page.getByRole('button',{name:'进入工作台'}).click();
  await expect(page.getByRole('heading',{name:'合成演示店1'})).toBeVisible();
  await page.reload();
  await expect(page.locator('article')).toHaveCount(0);
  await expect(page.getByRole('heading',{name:'合成演示店1'})).toHaveCount(0);
});
