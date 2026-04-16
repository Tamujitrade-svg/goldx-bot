"""
GoldX Bot — Economic Calendar Feed
Scrapes or fetches upcoming high-impact economic events.
Sources: ForexFactory RSS / Investing.com / fallback mock.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
import re

import requests
from bs4 import BeautifulSoup
import pytz

from utils.logger import logger
from config import HIGH_IMPACT_EVENTS, SUSPEND_MINUTES_BEFORE_NEWS, SUSPEND_MINUTES_AFTER_NEWS

UTC = pytz.UTC


@dataclass
class EconomicEvent:
    name: str
    impact: str          # HIGH / MEDIUM / LOW
    datetime_utc: Optional[datetime]
    currency: str = "USD"
    actual: str = ""
    forecast: str = ""
    previous: str = ""

    @property
    def is_high_impact(self) -> bool:
        return self.impact.upper() == "HIGH"

    @property
    def minutes_until(self) -> Optional[float]:
        if self.datetime_utc is None:
            return None
        now = datetime.now(tz=UTC)
        delta = (self.datetime_utc - now).total_seconds() / 60
        return delta

    def is_in_suspension_window(self) -> bool:
        """Return True if we are within SUSPEND_MINUTES before/after this event."""
        m = self.minutes_until
        if m is None:
            return False
        return -SUSPEND_MINUTES_AFTER_NEWS <= m <= SUSPEND_MINUTES_BEFORE_NEWS

    def __str__(self) -> str:
        t = self.datetime_utc.strftime("%Y-%m-%d %H:%M UTC") if self.datetime_utc else "TBD"
        return f"[{self.impact}] {self.name} ({self.currency}) @ {t}"


class CalendarFeed:
    """Provides upcoming economic events."""

    FOREXFACTORY_CALENDAR = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

    def fetch_forexfactory(self) -> list[EconomicEvent]:
        """
        ForexFactory publishes a weekly JSON calendar.
        URL: https://nfs.faireconomy.media/ff_calendar_thisweek.json
        """
        try:
            resp = requests.get(self.FOREXFACTORY_CALENDAR, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            events: list[EconomicEvent] = []
            for item in data:
                impact_raw = item.get("impact", "").strip().upper()
                if impact_raw not in ("HIGH", "MEDIUM", "LOW"):
                    impact_raw = "LOW"
                dt_str = item.get("date", "")
                dt = self._parse_ff_datetime(dt_str)
                events.append(EconomicEvent(
                    name=item.get("title", ""),
                    impact=impact_raw,
                    datetime_utc=dt,
                    currency=item.get("country", "USD"),
                    forecast=str(item.get("forecast", "")),
                    previous=str(item.get("previous", "")),
                    actual=str(item.get("actual", "")),
                ))
            logger.info("ForexFactory calendar: {} events loaded.", len(events))
            return events
        except Exception as exc:
            logger.error("ForexFactory calendar fetch error: {}", exc)
            return self._mock_events()

    def _parse_ff_datetime(self, dt_str: str) -> Optional[datetime]:
        """Parse ForexFactory date format: '2025-01-15T08:30:00-05:00'"""
        if not dt_str:
            return None
        try:
            # Handle timezone offset
            dt = datetime.fromisoformat(dt_str)
            return dt.astimezone(UTC)
        except Exception:
            return None

    def get_upcoming_high_impact(self, hours_ahead: int = 24) -> list[EconomicEvent]:
        """Return HIGH impact USD events in the next N hours."""
        events = self.fetch_forexfactory()
        now = datetime.now(tz=UTC)
        cutoff = now + timedelta(hours=hours_ahead)
        result = []
        for e in events:
            if e.datetime_utc is None:
                continue
            if e.currency != "USD":
                continue
            if e.impact != "HIGH":
                continue
            if now <= e.datetime_utc <= cutoff:
                result.append(e)
        result.sort(key=lambda x: x.datetime_utc)
        return result

    def is_news_blackout(self) -> tuple[bool, Optional[EconomicEvent]]:
        """
        Returns (True, event) if we are in a suspension window around any
        HIGH impact event. Returns (False, None) otherwise.
        """
        events = self.fetch_forexfactory()
        for e in events:
            if e.is_high_impact and e.is_in_suspension_window():
                return True, e
        return False, None

    def get_next_event(self) -> Optional[EconomicEvent]:
        """Return the next upcoming USD HIGH impact event."""
        upcoming = self.get_upcoming_high_impact(hours_ahead=168)  # 1 week
        return upcoming[0] if upcoming else None

    def _mock_events(self) -> list[EconomicEvent]:
        now = datetime.now(tz=UTC)
        return [
            EconomicEvent(
                name="CPI m/m",
                impact="HIGH",
                datetime_utc=now + timedelta(hours=2),
                currency="USD",
                forecast="0.3%",
                previous="0.4%",
            ),
            EconomicEvent(
                name="FOMC Statement",
                impact="HIGH",
                datetime_utc=now + timedelta(hours=26),
                currency="USD",
                forecast="4.75%",
                previous="5.00%",
            ),
            EconomicEvent(
                name="NFP",
                impact="HIGH",
                datetime_utc=now + timedelta(hours=72),
                currency="USD",
                forecast="185K",
                previous="227K",
            ),
        ]
