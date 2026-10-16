"""Bounded UTF-8 CSV parsing and display-only safe CSV generation. No formula evaluation."""

import csv
import io
from decimal import Decimal, InvalidOperation
from uuid import UUID

from fastapi import HTTPException
from pydantic import ValidationError

from .catalog import ProductInput

HEADERS = ["商品名称", "分类", "规格", "单位", "参考价格", "供货说明", "排序", "商品介绍"]
SUPPLY = {"常备": "REGULAR", "待确认": "CONFIRM", "暂缺": "UNAVAILABLE"}


def display_csv(rows):
    # Text-first display export: prepend apostrophe and quote/escape EVERY field.
    # Consumers must import columns as text; re-saving in Excel can remove protections.
    output = io.StringIO(newline="")
    writer = csv.writer(output, quoting=csv.QUOTE_ALL)
    for row in rows:
        writer.writerow(["'" + str(value if value is not None else "") for value in row])
    return output.getvalue()


def parse_csv(text, maximum_bytes):
    if not text or len(text.encode("utf-8")) > maximum_bytes:
        raise HTTPException(413, "CSV_SIZE_LIMIT")
    if any(ord(c) < 32 and c not in "\t\r\n" for c in text):
        raise HTTPException(422, "CSV_CONTROL_CHARACTER")
    try:
        reader = csv.reader(io.StringIO(text.lstrip("\ufeff"), newline=""), strict=True)
        header = next(reader)
        if header != HEADERS:
            raise HTTPException(422, "CSV_TEMPLATE_COLUMNS_REQUIRED")
        result = []
        for values in reader:
            if not values:
                continue
            if len(result) >= 200:
                raise HTTPException(413, "CSV_ROW_LIMIT")
            if len(values) != 8 or any(len(v) > 4000 for v in values):
                raise HTTPException(422, "CSV_COLUMN_OR_CELL_LIMIT")
            name, category, spec, unit, price, supply, order, description = [
                v.strip() for v in values
            ]
            row = {
                "number": len(result) + 1,
                "source": values,
                "state": "PENDING",
                "error": "",
                "warnings": [],
                "product_id": None,
            }
            try:
                if not category or len(category) > 100:
                    raise ValueError("CATEGORY_REQUIRED_MAX_100")
                if supply not in SUPPLY:
                    raise ValueError("SUPPLY_MUST_BE_常备_待确认_暂缺")
                if not unit or any(c in unit for c in "\r\n\t"):
                    raise ValueError("UNIT_REQUIRED_SINGLE_LINE")
                if order and (not order.isascii() or not order.isdigit()):
                    raise ValueError("SORT_MUST_BE_NONNEGATIVE_INTEGER")
                if price and not Decimal(price).is_finite():
                    raise ValueError("REFERENCE_PRICE_INVALID")
                product = ProductInput(
                    category_id=UUID(int=0),
                    name=name,
                    spec=spec,
                    unit=unit,
                    reference_price=Decimal(price) if price else None,
                    supply_status=SUPPLY[supply],
                    sort_order=int(order or "0"),
                    description=description,
                )
                row["data"] = product.model_dump(mode="json", exclude={"category_id"}) | {
                    "category_name": category
                }
            except (ValidationError, ValueError, InvalidOperation):
                row["state"] = "INVALID"
                row["error"] = "请核对名称/分类/单位长度、供货说明枚举、非负两位小数参考价和排序"
            result.append(row)
        if not result:
            raise HTTPException(422, "CSV_EMPTY")
        return result
    except (csv.Error, StopIteration):
        raise HTTPException(422, "CSV_PARSE_FAILED") from None
