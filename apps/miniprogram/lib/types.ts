export interface ListResult<T> {
    items: T[];
    total: number;
    page: number;
    limit: number;
}
export interface Store {
    id?: string;
    tenant_id: string;
    name: string;
    description: string;
    logo_url: string | null;
    public_contact: string;
    public_address: string;
    business_hours: string;
    delivery_note: string;
    allow_pickup: boolean;
    allow_delivery: boolean;
    version?: number;
}
export interface Category {
    id: string;
    name: string;
    sort_order: number;
    version: number;
    status: string;
}
export interface Product {
    id: string;
    name: string;
    description: string;
    unit: string;
    spec: string;
    reference_price: string | null;
    supply_status: string;
    category_id: string;
    images: {
        id: string;
        url: string;
    }[];
    version: number;
    status?: string;
}
export interface Item {
    name: string;
    quantity: string;
    unit: string;
    spec: string;
    product_id?: string | null;
    reference_price?: string | null;
}
export interface Attachment {
    id: string;
    url: string;
    sort_order?: number;
}
export interface Revision {
    id: string;
    proposed_version: number;
    confirmed_version: number | null;
    confirmed_at: string | null;
    details: {
        summary: string;
        items: Item[];
        fulfillment_at: string | null;
        time_note: string;
        change_reason: string;
    };
}
export interface Cancellation {
    id: string;
    reason: string;
    status: string;
    response_note: string;
}
export interface RecordData {
    id: string;
    tenant_id: string;
    raw_text: string;
    status: string;
    version: number;
    internal_note?: string;
    source?: string;
    customer_label?: string;
    items?: Item[];
    created_at: string;
    expected_at?: string | null;
    expected_time_note?: string;
    confirmed_text?: string;
    fulfillment_method?: 'PICKUP' | 'DELIVERY';
    product_snapshot?: Partial<Product> | null;
    attachments: Attachment[];
    cancellation_requests?: Cancellation[];
    confirmation_revisions?: Revision[];
    converted_reservation_id?: string | null;
    events?: {
        action?: string;
        from_status: string | null;
        to_status: string;
        note?: string;
        created_at: string;
    }[];
    replies?: {
        id: string;
        text: string;
        visible_to_customer: boolean;
        created_at: string;
    }[];
}
export interface Draft {
    raw_text: string;
    customer_label: string;
    items: Item[];
    media_ids: string[];
    fulfillment_method: 'PICKUP' | 'DELIVERY';
    expected_time_note: string;
    privacy_accepted: boolean;
    source?: string;
    internal_note?: string;
    mark_confirmed?: boolean;
    product_id?: string;
    expected_date?: string;
    expected_clock?: string;
}
