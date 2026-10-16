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

## M4b 私图已实现（开发身份）

- POST /api/v1/stores/{store_id}/private-media?privacy_accepted=true：登录顾客、已发布店铺、原始二进制图、Idempotency-Key。
- POST /api/v1/merchant/tenants/{tenant_id}/private-media：本店有效成员代记私图。
- 顾客询货/需求及商户代记可带media_ids（最多5、不重复、保序）；仅本人上传、同店、PRIVATE用途。仅图顾客请求可无raw_text。
- GET /api/v1/me/media/{media_id}/content?store_id=...：本人上传或本人记录中明确可见的关联图。无匿名URL/URL令牌；不能下载别店/别人的私图。
- 既有商户media内容与状态接口对PRIVATE加关联限制：非本人上传且尚未提交的客户图片不可读取/归档；提交到本店后才可处理。
- 转需求复制原咨询附件与顺序；商户新增内部附件默认不对顾客可见。PRIVATE不能关联商品/Logo或修改用途。
- 0006降级遇私图拒绝。没有真实资料自动清理任务；保留/删除政策发布前另确认。

## M4c 取消意向（当前实现，测试状态见TESTING）

上方各M1–M4b段落是当时范围说明，诸如“当前无附件/顾客入口”不代表最新状态；实际路由以此后追加段落及OpenAPI为准。

- POST /api/v1/me/reservations/{id}/cancellation-requests：expected_version、reason；必需Idempotency-Key，仅已验证归属本人。非终态统一申请；返回状态不自动变CANCELLED。
- POST /api/v1/merchant/tenants/{tenant_id}/reservations/{id}/cancellation-requests/{request_id}/decision：expected_version、decision=ACCEPTED|REJECTED、response_note（明确对顾客可见）；必需Idempotency-Key与本店有效成员。
- 有REQUESTED意向时所有普通状态迁移409 CANCELLATION_REVIEW_REQUIRED。接受才取消，拒绝保留原状态；两者增加需求版本和不可丢失事件，原文/明细不修改。
- 商户GET .../reservations?cancellation_pending=true|false：同租户分页筛选。商户和本人需求DTO包含cancellation_requests，不含处理人/申请人账号标识；record_events新增action便于区分同状态变更。
- 停店本人仍可留下取消意向，但无新增需求；客户端不能宣称已通知/已处理。完成和取消为终态，不受理新申请。
- 0007迁移遇取消历史拒绝破坏性降级；无需物理删除。

## M4d 确认详情修订（实现与测试状态见TESTING）

- POST /api/v1/merchant/tenants/{tenant_id}/reservations/{id}/confirmation-revisions：expected_version、summary或items、可空带时区fulfillment_at、time_note、change_reason；必需Idempotency-Key、本店有效成员。
- 原始raw_text/items/expected_at保持不变。每次候选完整快照追加为confirmation_revisions，包含商品服务端快照、小数数量和单位；前版不会被覆盖。
- 仅待确认/已确认且无待处理取消申请可改候选；每次改动将状态回到PENDING_CONFIRMATION，必须重新确认后才能备货。进入备货后不直接改明细，先沟通取消/重新建单；不静默改已执行任务。
- 存在候选时，原transitions→CONFIRMED还必须带当前confirmation_revision_id及customer_agreed=true。该字段表示商户明确记录已与顾客达成一致，不是经过微信验证的顾客电子确认。旧候选ID/未明确同意409。
- 本人与商户DTO均有confirmation_revisions，不含actor账号；包含提议版本/快照、确认版本/时间、agreement_recorded_by=MERCHANT。顾客期望时间与候选最终时间分开；未确认候选不得显示成承诺。
- 原confirmed_text仍是从询货转换时保存的文字，历史保持原值；有修订时界面以最新候选及其confirmed_version区分“待确认/已确认”，不能把旧字段误当最新确认结果。
- 迁移0008遇确认历史拒绝破坏性降级。

## 平台邀请审核与暂停（2026-10-13 实现补充）

- GET /platform/me、/platform/tenants、/platform/invitations、/platform/audit：独立平台管理员表鉴权，分页。平台角色不授予商户记录/附件访问权。
- POST /platform/invitations：owner_user_id必须是服务端已有且启用的身份UUID；proposed_name、reason。不按姓名/电话绑定，不创建已公开店铺。
- GET /me/shop-invitations；POST /me/shop-invitations/{id}/response：只有收件账号可读取/明确ACCEPTED或DECLINED，携带expected_version。
- POST /platform/invitations/{id}/review：携带expected_version、APPROVED/REJECTED和reason。只有收件人已ACCEPTED才可APPROVED；批准原子创建租户、OWNER成员和默认未公开的店铺。
- POST /platform/tenants/{id}/status：expected_version、ACTIVE/SUSPENDED、reason。暂停后隐藏公开店铺，拒绝新增顾客业务和商户读写；顾客仍可读取本人历史。暂停期间的历史处理政策须上线前确认。
- 所有上述POST需要Idempotency-Key；按actor+key防重，同键不同命令/载荷409。操作、审计和结果在一事务内；未知结果使用原键重试，返回原始结果后可刷新当前状态。
- 审计不输出完整幂等结果或请求键，不新增跨租户顾客搜索/导出。

此处为开发身份下真实API验证，不是已经完成真实商户身份核验或资质审批。正式平台管理员安全初始化渠道尚待部署阶段确认；本次只在受控演示种子生成platform-admin。

## Web商品批量维护与更新重试（2026-10-13）

商品PUT支持可选 `Idempotency-Key`。提供时，按租户、已验证账号、商品ID、键与完整请求体（含expected_version）记载成功快照；同键同体重放原快照，不再次增加版本，不覆盖之后的变更；同键不同体409。不提供键的既有调用仍必须匹配当前版本。
Web批量面板复用单商品POST/PUT，不是新的跨商品原子接口。最多50项，全部前端校验通过后逐件保存；已成功项不回滚，首个失败停止后续项。版本冲突须核对并明确结束剩余批次，再读取当前版本编辑，不能自动加版本覆盖。
原请求键、内容、已确认进度按服务端验证user_id和tenant_id存于当前浏览器localStorage，令牌仍只在内存。未知网络结果、401/403/408/429保留请求；重新登录同一身份后重试原批次。禁止将未知结果直接清除后另起新键。这个存储不是服务器备份，清理站点数据/换浏览器仍可能丢失待确认请求。

## 图片接收限时

上传图片请求默认总接收15秒，超时HTTP408 `IMAGE_UPLOAD_TIMEOUT`，断开可响应时HTTP400 `IMAGE_UPLOAD_INTERRUPTED`；不产生成功快照，允许原键原内容重试。显式长度非法400；声明或实际超过2MiB为413；不能以小Content-Length绕过实际分片累计限制。
数据库超时仍统一503 `DATABASE_UNAVAILABLE`，错误不返回SQL/凭据。语句/锁/池等待分别有配置上限；503是失败或结果需核实，不自动更换写请求幂等键。

## 日常工作台（0010）

GET /merchant/tenants/{tenant}/reservations保留状态/分页，增加day=today|tomorrow|date|none、on_date=YYYY-MM-DD、method=PICKUP|DELIVERY、overdue=true、q最多100字。日期按Asia/Shanghai，优先已确认承诺，其次顾客明确时间；不解析自然语言。q仅本店称呼/原文/完整LS业务号，通配符按字面匹配，分页最多100。
GET /merchant/tenants/{tenant}/workbench-summary用一次SQL同快照统计状态、待回复、取消意向和逾期；as_of是统计时间，不代表微信通知。
GET /merchant/tenants/{tenant}/reservations/{id}/copy-draft只读且须本店鉴权，不创建记录；不复制ID/版本/状态/幂等键/私图/内部备注/账号归属/承诺。返回可编辑草稿与商品核对警告；保存仍走创建接口和商品现状校验。
创建增加contact_name/contact_phone/delivery_address，均限长、非身份凭据。仅本店商户和本人DTO可读，公开DTO不输出。暂不供应商品拒绝新登记，旧快照保留。

## 正式身份代码（0011；外部微信响应尚未实测）

POST /auth/wechat/session仅接受code，服务端固定HTTPS code2Session交换，按本项目AppID+openid唯一映射本地账号；不接收客户端角色/账号/租户/openid。返回短时本系统opaque bearer，数据库仅保存HMAC摘要；session_key不保存不下发。默认900秒，无自动永久刷新。
GET /auth/me返回本系统user_id、开店账号码及development_only，不返回openid/session_key。POST /auth/logout撤销当前正式会话。每次请求重新核对过期/撤销/账号状态，平台权限还须独立PlatformAdmin有效。
POST /auth/browser-approvals发起三分钟工作台确认，随机确认码与仅留当前网页内存的查询secret；POST /auth/browser-approvals/confirm需已登录正式小程序账号且confirmed=true；POST /auth/browser-approvals/poll用原secret一次领取工作台会话。不创建新角色，不把开发账号升级为正式/平台账号。仅确认本人正在打开的工作台，禁止代他人确认。
平台邀请支持owner_account_code或旧开发owner_user_id二选一；正式管理员只能邀请WECHAT账号，U-账号码用于定向邀请，不是登录凭据，不用姓名/手机号认领。
GET /capabilities明确区分登录配置存在与真实微信已验；当前二维码/消息NOT_CONFIGURED，隐私DEVELOPMENT_DRAFT。不会返回假二维码或已通知结果。

## 站内更新与人工联系（G）

GET merchant/tenants/{tenant}/updates 与 me/stores/{tenant}/updates：每页50、page<=10000，返回本站当前身份 unread/total/items；event_key只定位既有事件，不是授权凭证。POST同路径/read接收1—100个event_keys，逐个验证归属，全有权限才写；同键重试无重复，绝不迁移业务状态。顾客只见本人公开事件，商户/顾客游标独立。

GET/POST merchant/tenants/{tenant}/{reservations|inquiries}/{record}/contacts：本店商户私有，每页50。POST复用Idempotency-Key、expected_version并要求confirmed=true；method只允许PHONE/WECHAT/NOT_REACHED、note<=500，增加版本和内部事件，不改变业务状态。顾客DTO不含此事件或备注。GET /contact-draft仅已确认需求，返回待人工核对摘要；复制不写联系记录。UI支持分页、显式结果和原请求重试。

GET notification-capabilities认证后返回外部UNCONFIGURED。没有外部发送HTTP入口、后台调度或真实凭据。内部提供prepare/dispatch_once接口供将来适配，必须先提交去重任务；IN_PROGRESS/UNKNOWN/TIMEOUT不自动重发，不承诺第三方恰好一次。
