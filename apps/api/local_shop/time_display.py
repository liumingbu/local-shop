"""Human-facing business time, explicitly separate from canonical API timestamps."""

from datetime import datetime
from zoneinfo import ZoneInfo


def business_time(value):
    if value is None:
        return "未确定"
    moment = datetime.fromisoformat(value) if isinstance(value, str) else value
    if moment.tzinfo is None:
        raise ValueError("Business display requires an aware timestamp")
    return moment.astimezone(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M") + "（北京时间）"
