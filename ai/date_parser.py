from __future__ import annotations
import re
from datetime import datetime, date
from typing import NamedTuple

MONTH_MAP = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sept": 9, "sep": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}

MONTH_REGEX = r"(?:january|jan|february|feb|march|mar|april|apr|may|june|jun|july|jul|august|aug|september|sept|sep|october|oct|november|nov|december|dec)"


class ParsedQuery(NamedTuple):
    clean_query: str
    is_date_only: bool
    year: int | None
    month: int | None
    day: int | None
    start_date: str | None  # "YYYY-MM-DD"
    end_date: str | None    # "YYYY-MM-DD"
    raw_date_str: str | None


def parse_date_and_semantic_query(user_text: str) -> ParsedQuery:
    """
    Parses user query into semantic text query and structured date filters.

    Supports natural language formats:
    - "10 December 2025", "10 Dec 2025", "10th December 2025", "10th of December 2025"
    - "December 10 2025", "Dec 10, 2025", "December 10th 2025"
    - "10/12/2025", "10-12-2025", "10.12.2025", "2025-12-10", "2025/12/10"
    - "December 2025", "Dec 2025", "12/2025", "2025-12"
    - Conversational queries:
      "Show me photos from 10 December 2025"
      "Give me pictures taken on 10 December 2025"
      "Find photos from December 2025"
      "Show me dog photos from 10 December 2025"
    """
    raw = user_text.strip()
    low = raw.lower()

    year: int | None = None
    month: int | None = None
    day: int | None = None
    matched_span: tuple[int, int] | None = None
    matched_text: str | None = None

    # Prefix helper for date regexes
    # E.g. "from", "taken on", "taken in", "shot on", "dated", "on", "in", "of", "during", "for"
    DATE_PRE = r"(?:\b(?:taken\s+on|taken\s+in|shot\s+on|shot\s+in|dated|from|on|in|of|during|for)\s+)?"

    # Pattern 1: "10 December 2025", "10th Dec 2025", "10th of December 2025", "from 10 December 2025"
    p1 = re.compile(
        rf"{DATE_PRE}(\d{{1,2}})(?:st|nd|rd|th)?(?:\s+of)?\s+({MONTH_REGEX})\s*,?\s*(\d{{4}})\b",
        re.IGNORECASE
    )
    # Pattern 2: "December 10 2025", "Dec 10th, 2025", "December 10, 2025"
    p2 = re.compile(
        rf"{DATE_PRE}({MONTH_REGEX})\s+(\d{{1,2}})(?:st|nd|rd|th)?\s*,?\s*(\d{{4}})\b",
        re.IGNORECASE
    )
    # Pattern 3 YMD: "2025-12-10", "2025/12/10", "2025.12.10"
    p3_ymd = re.compile(
        rf"{DATE_PRE}(\d{{4}})[/\-\.](\d{{1,2}})[/\-\.](\d{{1,2}})\b",
        re.IGNORECASE
    )
    # Pattern 3 DMY/MDY: "10/12/2025", "10-12-2025", "10.12.2025"
    p3_dmy = re.compile(
        rf"{DATE_PRE}(\d{{1,2}})[/\-\.](\d{{1,2}})[/\-\.](\d{{4}})\b",
        re.IGNORECASE
    )
    # Pattern 4: "December 2025", "Dec 2025", "in December 2025"
    p4 = re.compile(
        rf"{DATE_PRE}({MONTH_REGEX})\s*,?\s*(\d{{4}})\b",
        re.IGNORECASE
    )
    # Pattern 5: "12/2025" or "12-2025" or "2025-12"
    p5_my = re.compile(
        rf"{DATE_PRE}(\d{{1,2}})[/\-](\d{{4}})\b",
        re.IGNORECASE
    )
    p5_ym = re.compile(
        rf"{DATE_PRE}(\d{{4}})[/\-](\d{{1,2}})\b",
        re.IGNORECASE
    )
    # Pattern 6: "in 2025", "from 2025", "year 2025"
    p6_year = re.compile(
        r"\b(?:from|in|of|for|year|during)\s+(\d{4})\b",
        re.IGNORECASE
    )

    m1 = p1.search(low)
    m2 = p2.search(low)
    m3_ymd = p3_ymd.search(low)
    m3_dmy = p3_dmy.search(low)
    m4 = p4.search(low)
    m5_my = p5_my.search(low)
    m5_ym = p5_ym.search(low)
    m6_year = p6_year.search(low)

    if m1:
        day = int(m1.group(1))
        month = MONTH_MAP.get(m1.group(2).lower())
        year = int(m1.group(3))
        matched_span = m1.span()
        matched_text = m1.group(0)
    elif m2:
        month = MONTH_MAP.get(m2.group(1).lower())
        day = int(m2.group(2))
        year = int(m2.group(3))
        matched_span = m2.span()
        matched_text = m2.group(0)
    elif m3_ymd:
        year = int(m3_ymd.group(1))
        month = int(m3_ymd.group(2))
        day = int(m3_ymd.group(3))
        matched_span = m3_ymd.span()
        matched_text = m3_ymd.group(0)
    elif m3_dmy:
        p_first = int(m3_dmy.group(1))
        p_second = int(m3_dmy.group(2))
        year = int(m3_dmy.group(3))
        # Default to DD/MM/YYYY
        day = p_first
        month = p_second
        # If month > 12 and day <= 12, swap to MM/DD/YYYY
        if month > 12 and day <= 12:
            day, month = month, day
        matched_span = m3_dmy.span()
        matched_text = m3_dmy.group(0)
    elif m4:
        month = MONTH_MAP.get(m4.group(1).lower())
        year = int(m4.group(2))
        matched_span = m4.span()
        matched_text = m4.group(0)
    elif m5_ym:
        year = int(m5_ym.group(1))
        month = int(m5_ym.group(2))
        matched_span = m5_ym.span()
        matched_text = m5_ym.group(0)
    elif m5_my:
        month = int(m5_my.group(1))
        year = int(m5_my.group(2))
        if 1 <= month <= 12:
            matched_span = m5_my.span()
            matched_text = m5_my.group(0)
        else:
            month = None
            year = None
    elif m6_year:
        year = int(m6_year.group(1))
        matched_span = m6_year.span()
        matched_text = m6_year.group(0)

    # Validate month/day ranges
    if month is not None and not (1 <= month <= 12):
        month = None
    if day is not None and not (1 <= day <= 31):
        day = None

    # Compute start_date and end_date strings ("YYYY-MM-DD")
    start_date = None
    end_date = None
    if year is not None:
        if month is not None:
            if day is not None:
                start_date = f"{year:04d}-{month:02d}-{day:02d}"
                end_date = f"{year:04d}-{month:02d}-{day:02d}"
            else:
                # Whole month
                start_date = f"{year:04d}-{month:02d}-01"
                if month in (1, 3, 5, 7, 8, 10, 12):
                    last_day = 31
                elif month in (4, 6, 9, 11):
                    last_day = 30
                else:
                    # Leap year check
                    last_day = 29 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 28
                end_date = f"{year:04d}-{month:02d}-{last_day:02d}"
        else:
            # Whole year
            start_date = f"{year:04d}-01-01"
            end_date = f"{year:04d}-12-31"

    # Extract clean semantic query by stripping out the date phrase and search filler words
    clean_text = raw
    if matched_span:
        start_idx, end_idx = matched_span
        clean_text = raw[:start_idx] + " " + raw[end_idx:]

    # Remove conversational prefixes/fillers
    # Handles: "show me", "give me", "find", "search for", "photos", "pictures", "images", etc.
    clean_text = re.sub(
        r"\b(?:show|give|find|search|get|display|bring|fetch|list|please|look\s+for|i\s+want|can\s+you\s+show|photos?|images?|pictures?|pics?|shots?|snapshots?|of|me|all|the|from|taken\s+on|taken\s+in|taken|shot\s+on|shot\s+in|shot|dated|in|on|at|during|for)\b",
        " ",
        clean_text,
        flags=re.IGNORECASE
    )
    # Strip punctuation and excess whitespace
    clean_text = re.sub(r"[^\w\s]", " ", clean_text)
    clean_text = re.sub(r"\s+", " ", clean_text).strip()

    is_date_only = (len(clean_text) == 0 and start_date is not None)

    return ParsedQuery(
        clean_query=clean_text,
        is_date_only=is_date_only,
        year=year,
        month=month,
        day=day,
        start_date=start_date,
        end_date=end_date,
        raw_date_str=matched_text,
    )
