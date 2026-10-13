# API 草案与验收契约

状态：下方“已实现 M1/M2”有真实测试；其余清单仍为接口规划。实施时生成 OpenAPI 并以接口测试保持一致；这里的路径可小幅调整并同步记录，不要空报接口已通。

## 1. 公共约定

前缀 `/api/v1`。JSON请求/响应，身份会话和租户上下文由服务端核验。公开slug/tenant_id只是定位；私有ID接口仍需权限。

错误至少包含 `code`、用户可理解的 `message`、`request_id`。建议使用401未认证、403无权限、404资源不存在（避免暴露其他租户资源）、409并发/幂等冲突、422参数错误、429限流；一致策略通过测试固定。

列表采用明确的分页和稳定排序。创建、转换和状态更新考虑幂等。输出只保留角色可见字段，不把数据库对象直接序列化。

## 2. 端点清单

| 模块 | 方法与路径草案 | 权限与重点 |
|---|---|---|
| 健康 | GET /health/live、/health/ready | 存活与依赖就绪分开，不返回凭据 |
| 真实登录 | POST /auth/wechat | code由服务端交换；凭据缺失明确报错，不降级假登录 |
| 自己 | GET /me | 当前身份，不暴露平台他人资料 |
| 公开店铺 | GET /stores/{store_id} | 仅已发布且启用；公开字段 |
| 商品 | GET /stores/{store_id}/products、/{product_id} | 同店、已上架，分页 |
| 询货 | POST /stores/{store_id}/inquiries | 登录身份、限流、私有图片权限 |
| 顾客需求 | POST /stores/{store_id}/reservations | 幂等、同店商品、自助归属 |
| 本人历史 | GET /me/records?store_id=... | 必须本人且所属店铺，不能仅按电话 |
| 记录详情 | GET /me/records/{type}/{id} | 本人权限与字段裁剪 |
| 请求取消 | POST /me/reservations/{id}/cancellation-requests | 留痕，不越权直接完成备货 |
| 商户租户 | GET /merchant/tenants | 只列当前用户有效成员身份 |
| 店铺维护 | PATCH /merchant/tenants/{tenant_id}/store | 成员角色、版本检查 |
| 分类商品 | /merchant/tenants/{tenant_id}/categories、products | GET/POST/PATCH与下架，所有关联同租户 |
| 代记 | POST /merchant/tenants/{tenant_id}/reservations | 来源、原始需求；客户账号不能任意绑定 |
| 待办 | GET /merchant/tenants/{tenant_id}/tasks | 仅本租户、状态/时间筛选 |
| 答复 | POST /merchant/tenants/{tenant_id}/inquiries/{id}/replies | 公私备注区别 |
| 转需求 | POST /merchant/tenants/{tenant_id}/inquiries/{id}/convert | 显式、幂等、权限 |
| 状态 | POST /merchant/tenants/{tenant_id}/reservations/{id}/transitions | expected_version、允许迁移、审计 |
| 上传 | POST /merchant/tenants/{tenant_id}/media；顾客私有图独立入口 | 文件类型/大小/权限，公开图和私图分开 |
| 私有图 | GET /media/{id}/content | 所属记录读取权限或受控短期链接 |
| 平台商户 | /platform/tenants、/applications | 平台管理员鉴权、审核/暂停留痕 |

开发身份入口仅在受控开发配置存在，不纳入公开生产API。生产启动保护须独立测试。

## 3. 代记请求示例（设计样例，全部为合成信息）

```json
{
  "source": "MERCHANT_PHONE",
  "customer_label": "演示顾客甲",
  "raw_text": "干贝半斤，分两袋，明天下午自提",
  "items": [
    {"product_id": null, "name": "干贝", "quantity": "0.5", "unit": "斤", "spec": "分两袋"}
  ],
  "fulfillment_method": "PICKUP",
  "expected_time_note": "明天下午（提交时由界面补成明确日期）",
  "mark_confirmed": false
}
```

相对日期必须在实际提交前转换或明确确认，历史不能永远写“明天”却没有参照。无商品明细时可仅用 raw_text 保存快速草稿。

## 4. 状态更新示例

```json
{
  "target_status": "PREPARING",
  "expected_version": 3,
  "note": "开始准备",
  "visible_to_customer": true
}
```

后端先鉴权、查租户、校验版本与允许迁移，再事务更新和写事件；不能让客户直接PATCH任意 status。

## 5. 接口必须覆盖的反例

其他租户ID、其他顾客ID、私有图片地址猜测、已冻结店铺提交、重复提交、同键不同载荷、跨店商品关联、负数/过多数量、非法状态、旧版本更新、公开API泄露手机号、未登录/假登录生产开启。

开发完成后补充真实请求与响应、错误码、OpenAPI位置、契约测试命令，不仅保留成功curl示例。

## 已实现 M1/M2（2026-10-13）

- GET /health/live、/health/ready；GET /openapi.json 提供实际契约。
- POST /api/v1/dev/session，GET /api/v1/dev/me：仅回环、非生产、显式开启。
- GET /api/v1/merchant/tenants：当前有效成员租户。
- GET/PUT /api/v1/merchant/tenants/{tenant_id}/store：PUT需OWNER与expected_version；首次为0。
- POST/GET /api/v1/merchant/tenants/{tenant_id}/reservations：创建需要Idempotency-Key（8–100位ASCII字母数字或-_.）；列表page/limit/status，稳定排序。
- GET /api/v1/merchant/tenants/{tenant_id}/reservations/{id}：原文与有序事件。
- POST .../{id}/transitions：target_status、expected_version、note、visible_to_customer；必需Idempotency-Key。
- 同键同载荷返回首次快照，同键不同载荷409。事务提交在响应发送之前；提交失败503不冒充已保存。
- 创建不允许指定customer_user_id、tenant_id或非空product_id；当前无商品关联。不会凭称呼绑定顾客。
- 确认→备货→READY；自提READY可完成，配送READY先OUT_FOR_DELIVERY；完成/取消为终态。
- 当前无附件/导出/顾客本人入口，不能由上述商户测试推导那些接口已安全实现。
- 原文、明细不可直接修改；确认结果当前为同一不可变明细与确认事件。后续调整确认明细需新增保留原文的显式版本接口。
- `expected_time_note`是未解析原文备注；绝不将“明天”推断成已核实交付日期。正式结构化时间字段留后续顾客需求模块。

## M3a 已实现接口（图片仍未实现）

- 商户类别：GET/POST /api/v1/merchant/tenants/{tenant_id}/categories；PUT .../categories/{id}（expected_version）。status=ARCHIVED软归档，恢复ACTIVE可重新展示；不删除历史。
- 商户商品：GET/POST .../products；GET/PUT .../products/{id}。POST需要Idempotency-Key，PUT需要expected_version。单个默认规格：名称、单位、spec、可空reference_price（Decimal12,2）、supply_status=REGULAR/CONFIRM/UNAVAILABLE；status=DRAFT/PUBLISHED/ARCHIVED。没有库存/应付金额字段。
- 公开：GET /api/v1/stores/{store_id}、/products、/products/{id}。只有启用租户、明确published店铺、PUBLISHED商品和ACTIVE分类可读，已归档/其他店商品404。列表有page/limit与稳定排序。
- 店铺PUT增加published/public_contact/public_address/business_hours/delivery_note/allow_pickup/allow_delivery；未显式开放交付方式时默认均false。更新未指定字段保留现值，避免旧客户端无意撤销发布。
- 代记items.product_id现可为本店公开商品ID；服务器读取名称/单位/规格/参考价格快照，客户端不能伪造。商品之后改名/归档不改历史快照；自由明细仍可不指定商品。
- 图片、多规格组合、平台范围搜索、真实扫码尚未实现。

## M3b 图片已实现（界面与微信上传适配未实现）

- POST /api/v1/merchant/tenants/{tenant_id}/media?purpose=PRODUCT|LOGO：原始二进制体，限定Content-Type与2MiB，必需认证和Idempotency-Key。
- GET .../media/{id}/content：仅本租户有效成员；不返回存储路径；无token查询参数。
- PATCH .../media/{id}：status=ACTIVE|ARCHIVED，expected_version；可恢复，不物理删除。
- PUT .../products/{id}/images：media_ids有序不重复、最多8、expected_version；仅本店PRODUCT图片。
- 店铺PUT logo_media_id仅本店LOGO；公开店铺返回logo_url。
- GET /api/v1/stores/{store_id}/products/{product_id}/images/{media_id} 与 /stores/{store_id}/logo：检查租户有效、店铺发布、商品/分类有效、当前关联和图片状态。未关联上传物不可公开读取。
- PNG/JPEG/WebP真实解码、动画与像素限制、清理EXIF并统一JPEG。随机UUID文件名，路径不来自用户文件名。
- 提交失败清理本次新建文件；进程被强杀时可能产生未关联孤立文件，但无公开可访问关联，不自动清理未知旧文件。上线前纳入备份/恢复与维护说明。
- 这里只接受商户公开用途候选图片。顾客咨询私图还未实现，不复用上述公开用途作为私图入口。

## M4a 顾客/询货已实现（固定开发身份，非真实微信）

- 开发身份增customer-a/customer-b，无商户成员资格。
- POST /api/v1/stores/{store_id}/reservations：文本或items至少一个；privacy_accepted=true；Idempotency-Key；后台绑定当前认证用户。不得传source/customer_user_id/status/internal_note。交付方式必须由店铺开放。
- POST /api/v1/stores/{store_id}/inquiries：原文、可选本店公开product_id、privacy_accepted；幂等。商品快照不随之后改名变化。
- GET /api/v1/me/records?kind=reservation|inquiry&store_id=...&page=...&limit=...；GET /me/records/reservation/{id}或/inquiry/{id}。只匹配本人归属；停店不删除本人已有历史，不开放新请求。
- 商户GET .../inquiries、/{id}；POST .../{id}/replies（text、visible_to_customer、expected_version）、/close（expected_version）、/convert（代记字段+expected_version）。写操作均需Idempotency-Key，租户成员与版本在服务端校验。
- 内部询货备注及其事件不返回顾客；回复有货不创建需求。显式转换锁定原咨询，一个咨询至多一个转换需求；保留咨询原文于raw_text，商户确认文字于confirmed_text；不自动关闭原咨询。
- expected_at为可空带时区时间；expected_time_note保留备注不猜测精确时间。
- 当前隐私版本development-draft-v1只用于开发模拟，不代替正式隐私文本/授权/真实身份核验。
- 私图/取消申请/原生页面尚未实现，未包含在本轮通过范围。
