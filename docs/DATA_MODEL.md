# 数据模型与状态约束草案

状态：设计契约；真实 DDL、迁移和索引需在实现与PostgreSQL测试后确定。

## 1. 数据实体

| 表/实体 | 主要字段 | 约束 |
|---|---|---|
| users | id、identity_type、外部身份映射、状态 | 外部身份由服务端核验；敏感字段不公开 |
| tenants | id、显示名、status、created_at | 邀请/审核/启用/暂停；不是微信AppID |
| tenant_members | tenant_id、user_id、role、status | 复合唯一；同一用户可拥有多个成员身份 |
| stores | tenant_id、店名、介绍、logo、公开联系、交付配置 | 首版每租户一店；私有经营者资料另存 |
| categories | id、tenant_id、名称、排序、status | 同租户引用 |
| products | id、tenant_id、category_id、名称、单位、参考价、供货状态 | 价格可空；Decimal；不默认精确库存 |
| product_variants | id、tenant_id、product_id、规格、单位、参考价 | 首版可单默认规格；不要复杂规格笛卡尔积 |
| media_objects | id、tenant_id、owner_user_id、visibility、storage_key、类型、大小 | 公私分离；业务归属与权限验证 |
| product_media | tenant_id、product_id、media_id、sort | 同租户且媒体适合作公开商品图 |
| inquiries | id、tenant_id、customer_user_id、source、raw_text、status | 非空文本或关联内容；客户归属服务端确定 |
| inquiry_replies | id、tenant_id、inquiry_id、actor、text、visible_to_customer | 内部备注与公开答复区分 |
| reservations | id、tenant_id、source、customer_user_id(可空)、原始需求、确认摘要、交付、status、version | 自助提交需要身份；代记可无客户账号 |
| reservation_items | id、tenant_id、reservation_id、商品可空、名称快照、数量、单位、规格快照 | 自由文本记录允许无商品ID |
| record_events | tenant_id、record_type/id、actor、前后状态、摘要、时间 | 追加记录；不写密钥或完整隐私原文 |
| idempotency_keys | tenant_id、actor_id、endpoint、key、payload_hash、result_ref | 复合唯一、原子保存 |
| store_applications | 申请人、拟店名、审核状态、必要证明引用 | 不自动公开身份证/营业执照图 |

## 2. 同租户约束

子表的 `tenant_id` 不由客户端直接决定。关联产品、分类、媒体和记录必须属于当前租户。数据库可采用 `(tenant_id,id)` 唯一键与复合外键，防止“记录属于A却关联B商品”。只给业务表加一个 tenant_id 字段不算隔离完成。

索引重点为 `(tenant_id,status,created_at)`、`(tenant_id,customer_user_id,created_at)`、`(tenant_id,expected_at)`；分页和排序使用稳定次级键。

## 3. 咨询状态

`NEW → REPLIED → CLOSED`。可追加答复；关闭行为审计。商家答复不直接创建备货。

咨询转需求必须是明确操作，创建独立 reservation 并保留 `source_inquiry_id`；同一转换请求幂等，不删除原咨询。咨询关单与否由显式业务动作决定，不静默标记成交。

## 4. 需求状态

主路径：

```text
PENDING_CONFIRMATION → CONFIRMED → PREPARING → READY
READY → COMPLETED                         # 自提完成
READY → OUT_FOR_DELIVERY → COMPLETED       # 商家配送完成
非终态 → CANCELLED                        # 按角色/阶段规则确认
```

老板代记时可在同一事务明确“已确认”，记录从创建到CONFIRMED的事件；不得省略来源和操作人。

状态迁移按服务端允许表实现。顾客不能直接修改备货/完成状态。完成/取消默认终态，后续再需求创建新单。临时缺货通过沟通/修改/取消处理，不偷偷跳状态。

改变已确认数量、规格或交付时间时，应记录变更与重新确认标记，不能覆盖原始需求。并发携带 `expected_version`；旧版本返回冲突，不后写覆盖先写。

## 5. 幂等与事务

创建请求使用 `Idempotency-Key`，唯一范围含租户、请求主体和端点。同一键同一载荷返回原结果；同一键不同载荷返回冲突。记录主表、明细、事件和幂等结果在同一事务提交。异常回滚不能留下半张需求单。

## 6. 数量、价格与时间

数量：Decimal，例如 `"0.5"`，必须为正并规定精度上限；单位随明细保存。不同单位和规格不能直接相加。

参考价可空，固定点数值，明确标注“参考/待确认”；系统不生成支付金额、欠款、支付状态或退款。

`created_at/updated_at`使用带时区的时间；界面按Asia/Shanghai显示。期望日期/时间段与商家最终确认时间分开；无具体时间可仅存日期与时段说明，不伪造一个确定时间。

## 7. 身份与历史

`source` 为 `CUSTOMER_MINIAPP`、`MERCHANT_WECHAT`、`MERCHANT_PHONE`、`MERCHANT_IN_STORE`等，不意味着接入微信私聊API。

代记 `customer_user_id=NULL` 时，只有商户有权看。电话匹配不建立归属。本人查询必须同时匹配登录身份与记录所属租户；序号、姓名或电话不可作为访问凭证。

商品改价、改名、下架之后，历史仍显示提交快照和确认结果；不要依赖现商品数据回填历史。

## 8. 数据生命周期

商品下架与记录归档优先，不因删除商品级联删除需求。真实数据删除、保留期和备份清理须在上线前确定政策；测试合成数据可以在明确隔离测试库中重建。默认不给平台管理员无审计导出全库能力。

## M4c 实际补充

cancellation_requests：tenant_id+reservation_id复合FK、requester、reason、REQUESTED/ACCEPTED/REJECTED、对客response_note、决策actor/time、申请与决策的需求版本。每个需求至多一个REQUESTED（PG部分唯一索引）。决策非空与版本递增有CHECK。
所有申请、决策与常规状态变更先锁同一reservation行；record_events新增action，申请/拒绝可同状态但仍递增版本。幂等结果与事件事务一致。尚无结构化确认明细修订接口，原始items仍不可变。

## M4d 确认修订

confirmation_revisions以tenant_id+reservation_id复合FK绑定原需求，proposed_version唯一，details JSONB保存完整候选快照。confirmed_version/by/at须同时为空或全部存在且确认版本大于提议版本。普通API只允许追加候选及对当前未确认候选记录确认，不能覆盖旧details。
原需求文本/明细/期望时间不更新；最终时间存在候选details.fulfillment_at。修改确认内容回到待确认，既有状态机阻止直接备货，服务端要求精确候选ID与商户明确确认。

## 平台基础管理实际补充

0009_platform：tenants增加version；platform_admins独立角色（无商户成员隐式继承）；shop_invitations绑定明确owner_user_id，INVITED→ACCEPTED/DECLINED，ACCEPTED经管理员APPROVED或REJECTED，批准时才关联唯一tenant_id。
platform_operations存actor+key唯一、action、payload_hash、原始response以及目标租户/邀请、前后状态、reason和时间；普通API只追加，未提供修改/删除审计接口。不是防DB管理员篡改的承诺。
租户状态变更锁定Tenant行；商户鉴权与公开店铺新业务持有Tenant共享行锁到事务结束，避免授权检查和暂停提交间穿透。历史顾客权限路径保持独立。
存在邀请/操作历史时0009降级主动拒绝，不能靠降级删除历史；需要审查备份恢复方案。真实资料保留政策另确认。
