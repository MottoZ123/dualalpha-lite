from __future__ import annotations

from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo


SHANGHAI = ZoneInfo("Asia/Shanghai")
NEW_YORK = ZoneInfo("America/New_York")
SSE_CALENDAR_SOURCE = "https://www.sse.com.cn/disclosure/dealinstruc/closed/c/c_20251222_10802510.shtml"
HKEX_CALENDAR_SOURCE = "https://www.hkex.com.hk/-/media/HKEX-Market/Services/Circulars-and-Notices/Participant-and-Members-Circulars/SEHK/2025/ce_SEHK_CT_075_2025.pdf"
NYSE_CALENDAR_SOURCE = "https://www.nyse.com/trade/hours-calendars"
SSE_2026_HOLIDAYS = {
    date(2026, 1, 1), date(2026, 1, 2),
    date(2026, 2, 16), date(2026, 2, 17), date(2026, 2, 18), date(2026, 2, 19), date(2026, 2, 20), date(2026, 2, 23),
    date(2026, 4, 6),
    date(2026, 5, 1), date(2026, 5, 4), date(2026, 5, 5),
    date(2026, 6, 19),
    date(2026, 9, 25),
    date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 5), date(2026, 10, 6), date(2026, 10, 7),
}
HKEX_2026_HOLIDAYS = {
    date(2026, 1, 1), date(2026, 2, 17), date(2026, 2, 18), date(2026, 2, 19),
    date(2026, 4, 3), date(2026, 4, 6), date(2026, 4, 7), date(2026, 5, 1),
    date(2026, 5, 25), date(2026, 6, 19), date(2026, 7, 1), date(2026, 10, 1),
    date(2026, 10, 19), date(2026, 12, 25),
}
NYSE_2026_HOLIDAYS = {
    date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16), date(2026, 4, 3),
    date(2026, 5, 25), date(2026, 6, 19), date(2026, 7, 3), date(2026, 9, 7),
    date(2026, 11, 26), date(2026, 12, 25),
}
NYSE_2026_EARLY_CLOSES = {date(2026, 11, 27), date(2026, 12, 24)}


def _inside(value: time, start: time, end: time) -> bool:
    return start <= value < end


def market_clock(now: datetime | None = None) -> dict:
    """Return conservative cross-market session state and refresh guidance.

    The current SSE annual closure notice is applied exactly for 2026. Other
    years remain conservatively labelled as weekday-session-only.
    """
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    cn = instant.astimezone(SHANGHAI)
    us = instant.astimezone(NEW_YORK)
    cn_calendar_covered = cn.year == 2026
    cn_holiday = cn.date() in SSE_2026_HOLIDAYS if cn_calendar_covered else False
    cn_weekday = cn.weekday() < 5 and not cn_holiday
    hk_holiday = cn.date() in HKEX_2026_HOLIDAYS if cn.year == 2026 else False
    hk_weekday = cn.weekday() < 5 and not hk_holiday
    us_holiday = us.date() in NYSE_2026_HOLIDAYS if us.year == 2026 else False
    us_weekday = us.weekday() < 5 and not us_holiday
    cn_time, us_time = cn.time().replace(tzinfo=None), us.time().replace(tzinfo=None)
    cn_open = cn_weekday and (_inside(cn_time, time(9, 30), time(11, 30)) or _inside(cn_time, time(13), time(15)))
    cn_lunch = cn_weekday and _inside(cn_time, time(11, 30), time(13))
    hk_open = hk_weekday and (_inside(cn_time, time(9, 30), time(12)) or _inside(cn_time, time(13), time(16)))
    us_close = time(13) if us.date() in NYSE_2026_EARLY_CLOSES else time(16)
    us_open = us_weekday and _inside(us_time, time(9, 30), us_close)
    next_refresh = 5 if cn_open else 15 if hk_open or us_open else 30 if cn_lunch else 300
    return {
        "asOf": instant.isoformat(),
        "timezone": "Asia/Shanghai",
        "cn": {"state": "trading" if cn_open else "lunch" if cn_lunch else "closed", "localTime": cn.isoformat(), "holiday": cn_holiday},
        "hk": {"state": "trading" if hk_open else "closed", "localTime": cn.isoformat(), "quoteLatency": "provider-dependent", "holiday": hk_holiday},
        "us": {"state": "trading" if us_open else "closed", "localTime": us.isoformat(), "dstAware": True, "holiday": us_holiday, "earlyClose": us.date() in NYSE_2026_EARLY_CLOSES},
        "nextRefreshSeconds": next_refresh,
        "calendarConfidence": "official-annual-2026" if cn_calendar_covered else "weekday-session-only",
        "calendarNote": "A股、港股和美股采用各交易所2026年度休市安排；NYSE 11月27日、12月24日提前至13:00收盘。" if cn_calendar_covered else "当前年份未配置交易所正式休市表，只按工作日与交易时段判断。",
        "calendarSources": {"cn": SSE_CALENDAR_SOURCE, "hk": HKEX_CALENDAR_SOURCE, "us": NYSE_CALENDAR_SOURCE} if cn_calendar_covered else {},
    }
