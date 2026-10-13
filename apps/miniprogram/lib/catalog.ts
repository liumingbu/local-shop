import { ApiError, request } from './client';
import { merchantBase } from './merchant';
import type { Category,ListResult,Product } from './types';
export interface ProductForm {category_id:string;name:string;description:string;unit:string;spec:string;reference_price:string;status:string;supply_status:string;sort_order:string}
export function blankProduct(category=''):ProductForm{return {category_id:category,name:'',description:'',unit:'',spec:'',reference_price:'',status:'DRAFT',supply_status:'CONFIRM',sort_order:'0'};}
export function productForm(row:Product):ProductForm{return {...blankProduct(),category_id:row.category_id,name:row.name,description:row.description,unit:row.unit,spec:row.spec,
 reference_price:row.reference_price??'',status:row.status||'DRAFT',supply_status:row.supply_status,sort_order:String(row.sort_order||0)};}
export function order(value:string):number{if(!/^\d{1,6}$/.test(value)||Number(value)>100000)throw new ApiError('INVALID_SORT_ORDER');return Number(value);}
export function productBody(form:ProductForm){if(form.reference_price!==''&&!/^(?:0|[1-9]\d{0,9})(?:\.\d{1,2})?$/.test(form.reference_price))throw new ApiError('INVALID_REFERENCE_PRICE');
 return {...form,reference_price:form.reference_price===''?null:form.reference_price,sort_order:order(form.sort_order)};}
export async function allCategories(store:string):Promise<Category[]>{const rows:Category[]=[];for(let page=1;page<=100;page++){
 const result=await request<ListResult<Category>>(`${merchantBase(store)}/categories?page=${page}&limit=100`);rows.push(...result.items);if(page*100>=result.total)return rows;
 }throw new ApiError('CATEGORY_LIMIT_REQUIRES_WEB');}
export function uncertain(error:unknown):boolean{return !(error instanceof ApiError)||!error.status||error.status===409||error.status>=500;}
