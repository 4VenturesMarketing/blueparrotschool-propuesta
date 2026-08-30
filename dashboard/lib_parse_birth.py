"""Parse WooCommerce billing_birth free-text into a date."""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Optional, Tuple

MONTHS = {
    "enero": 1, "ene": 1, "febrero": 2, "feb": 2, "marzo": 3, "mar": 3,
    "abril": 4, "abr": 4, "mayo": 5, "may": 5, "junio": 6, "jun": 6,
    "julio": 7, "jul": 7, "agosto": 8, "ago": 8, "septiembre": 9, "setiembre": 9,
    "sep": 9, "sept": 9, "octubre": 10, "oct": 10, "noviembre": 11, "nov": 11,
    "diciembre": 12, "dic": 12,
}

def _norm_month_token(s: str) -> str:
    return (
        s.lower()
        .replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
    )

def _valid(y: int, m: int, d: int) -> Optional[date]:
    try:
        dt = date(y, m, d)
    except ValueError:
        return None
    if dt.year < 1920 or dt > date.today():
        return None
    if date.today().year - dt.year > 100:
        return None
    return dt

def _fix_part(n: str, maxv: int) -> int:
    n = (n or "0").lstrip("0") or "0"
    if len(n) == 3:
        if int(n[:2]) <= maxv:
            n = n[:2]
        else:
            n = n[1:]
    return int(n)

def parse_birth(raw) -> Tuple[Optional[date], str]:
    if raw is None:
        return None, "empty"
    text = str(raw).strip()
    if not text:
        return None, "empty"

    t0 = text
    t = text.lower().replace(" de ", " ").replace(",", " ")
    t = t.replace(":", "/").replace(".", "/").replace("_", "/")
    t = re.sub(r"\s*[-–—]\s*", "/", t)
    t = re.sub(r"\s*/\s*", "/", t)
    t = re.sub(r"\s+", " ", t).strip()

    digits = re.sub(r"\D", "", t0)
    if re.fullmatch(r"\d{8}", digits):
        for how, trip in (
            ("ddmmyyyy", (int(digits[0:2]), int(digits[2:4]), int(digits[4:8]))),
            ("yyyymmdd", (int(digits[6:8]), int(digits[4:6]), int(digits[0:4]))),
            ("mmddyyyy", (int(digits[2:4]), int(digits[0:2]), int(digits[4:8]))),
        ):
            d, m, y = trip if how != "yyyymmdd" else (trip[0], trip[1], trip[2])
            if how == "ddmmyyyy":
                d, m, y = int(digits[0:2]), int(digits[2:4]), int(digits[4:8])
            elif how == "yyyymmdd":
                y, m, d = int(digits[0:4]), int(digits[4:6]), int(digits[6:8])
            else:
                m, d, y = int(digits[0:2]), int(digits[2:4]), int(digits[4:8])
            dt = _valid(y, m, d)
            if dt:
                return dt, how

    if re.fullmatch(r"\d{4}", t0.strip()):
        dt = _valid(int(t0.strip()), 7, 1)
        if dt:
            return dt, "year_only_mid"

    m = re.match(r"^(\d{1,2})\s+([a-záéíóúñ]+)\s+(\d{2,4})$", t)
    if m:
        d = int(m.group(1))
        mon = MONTHS.get(_norm_month_token(m.group(2)))
        y = int(m.group(3))
        if y < 100:
            y += 2000 if y <= 30 else 1900
        if mon:
            dt = _valid(y, mon, d)
            if dt:
                return dt, "d_month_yyyy"

    nums = re.findall(r"\d+", t)
    if len(nums) == 3:
        a, b, c = nums
        y = int(c)
        if y < 100:
            y += 2000 if y <= 30 else 1900
        if len(a) == 4:
            dt = _valid(int(a), _fix_part(b, 12), _fix_part(c, 31))
            if dt:
                return dt, "yyyy_mm_dd"
        da, mo = _fix_part(a, 31), _fix_part(b, 12)
        if mo == 0:
            for guess in (1, 10):
                dt = _valid(y, guess, da)
                if dt:
                    return dt, "dd_mm_yyyy_month0"
        if 1 <= mo <= 12 and 1 <= da <= 31:
            dt = _valid(y, mo, da)
            if dt:
                return dt, "dd_mm_yyyy"
        ma, da2 = _fix_part(a, 12), _fix_part(b, 31)
        if 1 <= ma <= 12 and 1 <= da2 <= 31:
            dt = _valid(y, ma, da2)
            if dt:
                return dt, "mm_dd_yyyy_fallback"

    for fmt in ("%d/%m/%Y", "%Y/%m/%d", "%d/%m/%y", "%m/%d/%Y"):
        try:
            cand = t.replace(" ", "")
            parsed = datetime.strptime(cand[:10] if "%Y" in fmt else cand[:8], fmt).date()
            dt = _valid(parsed.year, parsed.month, parsed.day)
            if dt:
                return dt, "strptime_" + fmt
        except ValueError:
            continue

    m = re.match(r"^(\d{1,2})\s+(\d{1,2})\s+(\d{2,4})$", re.sub(r"\s+", " ", t0.lower()).strip())
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 2000 if y <= 30 else 1900
        dt = _valid(y, mo, d)
        if dt:
            return dt, "dd_mm_yyyy_spaces"

    return None, f"fail:{t0[:50]}"
