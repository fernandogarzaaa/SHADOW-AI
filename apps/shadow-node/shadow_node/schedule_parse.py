"""Natural-language scheduling parser for the Shadow Node.

Deterministic and regex-based: turns chat-style requests like
"remind me every weekday at 7am" into structured reminder proposals.
Anything ambiguous is rejected with a clarifying question, never guessed.
All times are node-local.
"""

from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass

from .reminders import RECURRENCES

_WEEKDAY_NUM = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}
_WEEKDAY_NAME = {v: k.capitalize() for k, v in _WEEKDAY_NUM.items()}

_TRIGGER = re.compile(r"\bremind\s+me\b", re.IGNORECASE)
_TIME_RE = re.compile(r"(?P<h>\d{1,2})(?::(?P<m>\d{2}))?\s*(?P<ap>[ap])\.?m\.?", re.IGNORECASE)
_BARE_TIME_RE = re.compile(r"(?P<h>\d{1,2})(?::(?P<m>\d{2}))?")
_WORD_TIME = {"noon": (12, 0), "midnight": (0, 0)}


@dataclass
class ScheduleProposal:
    title: str
    note: str
    due_at: float
    recurrence: str
    plain_cadence: str

    def as_dict(self) -> dict:
        return {
            "title": self.title,
            "note": self.note,
            "due_at": self.due_at,
            "recurrence": self.recurrence,
            "plain_cadence": self.plain_cadence,
        }


@dataclass
class ParseResult:
    status: str  # "parsed" | "needs_clarification" | "not_a_request"
    proposal: ScheduleProposal | None = None
    question: str | None = None

    def as_dict(self) -> dict:
        d: dict = {"status": self.status}
        if self.proposal is not None:
            d["proposal"] = self.proposal.as_dict()
        if self.question is not None:
            d["question"] = self.question
        return d


def _fmt_time(ts: float) -> str:
    dt = _dt.datetime.fromtimestamp(ts)
    h, m = dt.hour, dt.minute
    ap = "AM" if h < 12 else "PM"
    h12 = h % 12 or 12
    return f"{h12}:{m:02d} {ap}"


def describe_cadence(recurrence: str, due_at: float, now: float | None = None) -> str:
    """Plain-words cadence, e.g. "Every weekday at 7:00 AM"."""
    if recurrence not in RECURRENCES:
        raise ValueError(f"recurrence must be one of {RECURRENCES}")
    if recurrence == "hourly":
        return "Every hour"
    if recurrence == "daily":
        return f"Every day at {_fmt_time(due_at)}"
    if recurrence == "weekdays":
        return f"Every weekday at {_fmt_time(due_at)}"
    if recurrence == "weekly":
        day = _WEEKDAY_NAME[_dt.datetime.fromtimestamp(due_at).weekday()]
        return f"Every {day} at {_fmt_time(due_at)}"
    # one-shot
    now_dt = (
        _dt.datetime.fromtimestamp(time_now())
        if now is None
        else _dt.datetime.fromtimestamp(now)
    )
    dt = _dt.datetime.fromtimestamp(due_at)
    if dt.date() == now_dt.date():
        when = "today"
    elif dt.date() == (now_dt + _dt.timedelta(days=1)).date():
        when = "tomorrow"
    else:
        when = f"on {dt.strftime('%a, %b %d')}"
    return f"Once {when} at {_fmt_time(due_at)}"


def _parse_time_token(token: str) -> tuple[int, int] | None:
    """Parse "7am", "7:30pm", "19:00", "noon". Returns (hour, minute) or None
    when the token is a bare hour with no am/pm (genuinely ambiguous)."""
    token = token.strip().lower()
    if token in _WORD_TIME:
        return _WORD_TIME[token]
    m = _TIME_RE.fullmatch(token)
    if m and m.group("ap"):
        h = int(m.group("h"))
        minute = int(m.group("m") or 0)
        if not 1 <= h <= 12 or minute > 59:
            return None
        ap = m.group("ap").lower()
        if ap == "p" and h != 12:
            h += 12
        if ap == "a" and h == 12:
            h = 0
        return h, minute
    m = _BARE_TIME_RE.fullmatch(token)
    if m and not m.group("ap"):
        # 24h form like "19:00" is unambiguous; bare "7" is not.
        if ":" in token:
            h, minute = int(m.group("h")), int(m.group("m") or 0)
            if h <= 23 and minute <= 59:
                return h, minute
        return None
    return None


def _find_time(text: str) -> tuple[str, tuple[int, int] | str] | None:
    """Find the first time expression. Returns (matched_text, (h, m)) or
    (matched_text, "ambiguous") for a bare hour, or None."""
    for word in ("noon", "midnight"):
        if re.search(rf"\b{word}\b", text, re.IGNORECASE):
            return word, _WORD_TIME[word]
    m = re.search(r"\b\d{1,2}(?::\d{2})?\s*[ap]\.?m\.?\b", text, re.IGNORECASE)
    if m:
        parsed = _parse_time_token(m.group(0))
        if parsed is None:
            return m.group(0), "ambiguous"
        return m.group(0), parsed
    m = re.search(r"\b\d{1,2}:\d{2}\b", text)
    if m:
        parsed = _parse_time_token(m.group(0))
        if parsed is not None:
            return m.group(0), parsed
    m = re.search(r"(?<![\d:])\b\d{1,2}\b(?![\d:])", text)
    if m:
        return m.group(0), "ambiguous"
    return None


def _next_daily(h: int, minute: int, now: _dt.datetime) -> _dt.datetime:
    dt = now.replace(hour=h, minute=minute, second=0, microsecond=0)
    if dt <= now:
        dt += _dt.timedelta(days=1)
    return dt


def _next_weekday_on(
    day_num: int, h: int, minute: int, now: _dt.datetime
) -> _dt.datetime:
    dt = now.replace(hour=h, minute=minute, second=0, microsecond=0)
    delta = (day_num - dt.weekday()) % 7
    if delta == 0 and dt <= now:
        delta = 7
    return dt + _dt.timedelta(days=delta)


def _strip_phrase(text: str, phrase: str) -> str:
    idx = text.lower().find(phrase.lower())
    if idx == -1:
        return text
    return (text[:idx] + text[idx + len(phrase) :]).strip()


def _extract_title(body: str, *phrases: str) -> str:
    title = body
    for p in phrases:
        title = _strip_phrase(title, p)
    # Strip leftover cadence particles ("remind me to X every day at 7am"
    # leaves "to X at"; "every day at 7am to stretch" leaves "at to stretch").
    for _ in range(3):
        new = re.sub(r"^(to|at)\s+", "", title, flags=re.IGNORECASE).strip()
        if new == title:
            break
        title = new
    title = re.sub(r"\s+at\s*$", "", title, flags=re.IGNORECASE).strip()
    if title.lower() in ("at", "to"):
        title = ""
    title = re.sub(r"\s+", " ", title)
    return title


def parse_schedule(text: str, now: float | None = None) -> ParseResult:
    """Parse a scheduling request. Never guesses: ambiguous input yields
    needs_clarification with a concrete question."""
    now_f = time_now() if now is None else now
    now_dt = _dt.datetime.fromtimestamp(now_f)

    m = _TRIGGER.search(text or "")
    if not m:
        return ParseResult(status="not_a_request")
    body = text[m.end() :].strip()
    if not body:
        return ParseResult(
            status="needs_clarification", question="What should I remind you about?"
        )

    low = body.lower()

    # Sub-hourly intervals cannot fire reliably on the ambient tick.
    m_min = re.search(r"\b(?:every|each)\s+(\d+)\s+minutes?\b", low)
    if m_min:
        return ParseResult(
            status="needs_clarification",
            question=(
                "I can't reliably fire reminders more often than hourly. "
                "Did you mean every hour?"
            ),
        )
    m_hr = re.search(r"\b(?:every|each)\s+(\d+)\s+hours?\b", low)
    if m_hr:
        n = int(m_hr.group(1))
        if n != 1:
            return ParseResult(
                status="needs_clarification",
                question=(
                    f"I can do every hour, but not every {n} hours. "
                    "Did you mean every hour?"
                ),
            )
        title = _extract_title(body, m_hr.group(0))
        if not title:
            return ParseResult(
                status="needs_clarification", question="What should I remind you about?"
            )
        due = now_dt.replace(minute=0, second=0, microsecond=0)
        due += _dt.timedelta(hours=1)
        return _parsed(title, due, "hourly", now_f)

    m_hourly = re.search(r"\b(?:every\s+hour|hourly)\b", low)
    if m_hourly:
        title = _extract_title(body, m_hourly.group(0))
        if not title:
            return ParseResult(
                status="needs_clarification", question="What should I remind you about?"
            )
        due = now_dt.replace(minute=0, second=0, microsecond=0)
        due += _dt.timedelta(hours=1)
        return _parsed(title, due, "hourly", now_f)

    m_wd = re.search(r"\b(?:every|each)\s+weekdays?\b", low)
    if m_wd:
        return _daily_like(body, m_wd.group(0), "weekdays", now_dt, now_f)

    m_daily = re.search(r"\b(?:every\s+day|daily)\b", low)
    if m_daily:
        return _daily_like(body, m_daily.group(0), "daily", now_dt, now_f)

    m_wday = re.search(
        r"\bevery\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", low
    )
    if m_wday:
        day = m_wday.group(1)
        found = _find_time(low)
        if found is None:
            return ParseResult(
                status="needs_clarification",
                question=f"What time on {day.capitalize()}?",
            )
        matched, parsed = found
        if parsed == "ambiguous":
            return ParseResult(
                status="needs_clarification",
                question="Morning or evening? (e.g. 7am or 7pm)",
            )
        h, minute = parsed
        title = _extract_title(body, m_wday.group(0), matched)
        if not title:
            return ParseResult(
                status="needs_clarification", question="What should I remind you about?"
            )
        due = _next_weekday_on(_WEEKDAY_NUM[day], h, minute, now_dt)
        return _parsed(title, due, "weekly", now_f)

    m_week = re.search(r"\bevery\s+week\b", low)
    if m_week:
        found = _find_time(low)
        if found is None:
            return ParseResult(
                status="needs_clarification", question="What time each week?"
            )
        matched, parsed = found
        if parsed == "ambiguous":
            return ParseResult(
                status="needs_clarification",
                question="Morning or evening? (e.g. 7am or 7pm)",
            )
        h, minute = parsed
        title = _extract_title(body, m_week.group(0), matched)
        if not title:
            return ParseResult(
                status="needs_clarification", question="What should I remind you about?"
            )
        due = _next_daily(h, minute, now_dt)
        return _parsed(title, due, "weekly", now_f)

    # One-shots: "in 2 hours", "tomorrow at 9am", "on friday at 5pm", "at 3pm"
    m_in = re.search(r"\bin\s+(\d+)\s+(minutes?|hours?)\b", low)
    if m_in:
        n = int(m_in.group(1))
        unit = m_in.group(2)
        delta = (
            _dt.timedelta(hours=n)
            if unit.startswith("hour")
            else _dt.timedelta(minutes=n)
        )
        title = _extract_title(body, m_in.group(0))
        if not title:
            return ParseResult(
                status="needs_clarification", question="What should I remind you about?"
            )
        return _parsed(title, now_dt + delta, "none", now_f)

    m_tom = re.search(r"\btomorrow\s+at\s+(.+)", low)
    if m_tom:
        return _oneshot_at(
            body, m_tom.group(0), m_tom.group(1), now_dt + _dt.timedelta(days=1), now_f
        )

    m_on = re.search(
        r"\bon\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
        r"\s+at\s+(.+)",
        low,
    )
    if m_on:
        day, rest = m_on.group(1), m_on.group(2)
        found = _find_time(rest)
        if found is None:
            return ParseResult(
                status="needs_clarification",
                question=f"What time on {day.capitalize()}?",
            )
        matched, parsed = found
        if parsed == "ambiguous":
            return ParseResult(
                status="needs_clarification",
                question="Morning or evening? (e.g. 7am or 7pm)",
            )
        h, minute = parsed
        title = _extract_title(body, f"on {day} at {matched}")
        if not title:
            return ParseResult(
                status="needs_clarification", question="What should I remind you about?"
            )
        due = _next_weekday_on(_WEEKDAY_NUM[day], h, minute, now_dt)
        return _parsed(title, due, "none", now_f)

    m_at = re.search(r"\bat\s+(.+)", low)
    if m_at:
        found = _find_time(m_at.group(1))
        if found is None:
            return ParseResult(
                status="needs_clarification",
                question=(
                    "I couldn't find a time in that. Try 'remind me tomorrow at 9am'."
                ),
            )
        matched, parsed = found
        if parsed == "ambiguous":
            return ParseResult(
                status="needs_clarification",
                question="Morning or evening? (e.g. 7am or 7pm)",
            )
        h, minute = parsed
        title = _extract_title(body, f"at {matched}")
        if not title:
            return ParseResult(
                status="needs_clarification", question="What should I remind you about?"
            )
        due = _next_daily(h, minute, now_dt)
        return _parsed(title, due, "none", now_f)

    return ParseResult(
        status="needs_clarification",
        question=(
            "I couldn't tell when that should fire. "
            "Try 'remind me every weekday at 7am'."
        ),
    )


def _daily_like(
    body: str, cadence_phrase: str, recurrence: str, now_dt: _dt.datetime, now_f: float
) -> ParseResult:
    found = _find_time(body.lower())
    if found is None:
        when = "each day" if recurrence == "daily" else "each weekday"
        return ParseResult(status="needs_clarification", question=f"What time {when}?")
    matched, parsed = found
    if parsed == "ambiguous":
        return ParseResult(
            status="needs_clarification",
            question="Morning or evening? (e.g. 7am or 7pm)",
        )
    h, minute = parsed
    title = _extract_title(body, cadence_phrase, matched)
    if not title:
        return ParseResult(
            status="needs_clarification", question="What should I remind you about?"
        )
    due = _next_daily(h, minute, now_dt)
    if recurrence == "weekdays" and due.weekday() >= 5:
        due = _dt.datetime.fromtimestamp(_advance_weekday_ts(due.timestamp()))
    return _parsed(title, due, recurrence, now_f)


def _advance_weekday_ts(ts: float) -> float:
    dt = _dt.datetime.fromtimestamp(ts) + _dt.timedelta(days=1)
    while dt.weekday() >= 5:
        dt += _dt.timedelta(days=1)
    return dt.timestamp()


def _oneshot_at(
    body: str, full_phrase: str, time_part: str, base_day: _dt.datetime, now_f: float
) -> ParseResult:
    found = _find_time(time_part)
    if found is None:
        return ParseResult(status="needs_clarification", question="What time?")
    matched, parsed = found
    if parsed == "ambiguous":
        return ParseResult(
            status="needs_clarification",
            question="Morning or evening? (e.g. 7am or 7pm)",
        )
    h, minute = parsed
    title = _extract_title(body, f"tomorrow at {matched}")
    if not title:
        return ParseResult(
            status="needs_clarification", question="What should I remind you about?"
        )
    due = base_day.replace(hour=h, minute=minute, second=0, microsecond=0)
    return _parsed(title, due, "none", now_f)


def _parsed(
    title: str, due: _dt.datetime, recurrence: str, now: float | None = None
) -> ParseResult:
    due_f = due.timestamp()
    proposal = ScheduleProposal(
        title=title,
        note="",
        due_at=due_f,
        recurrence=recurrence,
        plain_cadence=describe_cadence(recurrence, due_f, now=now),
    )
    return ParseResult(status="parsed", proposal=proposal)


def time_now() -> float:
    import time as _time

    return _time.time()
