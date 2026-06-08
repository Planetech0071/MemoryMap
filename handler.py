"""
MemoryMap  Query Handler
Parses natural language questions about object locations and routes
them to the appropriate memory query.

Supports patterns:
  - "Where is my X?"
  - "Where are my X?"
  - "What is on my desk?" / "What's in the kitchen?"
  - "Did I move my X today?"
  - "When did I last see my X?"
  - "Can you see my X?"
  - "I can't find my X"
  - "What objects are visible right now?"
"""

from __future__ import annotations
import refrom datetime import datetime, timedelta
from enum import Enum, autofrom typing import Optional
from loguru import logger
from core.config import CURRENT_VISIBLE_WINDOW_SEC, MAX_QUERY_RESULTS
from memory.object_record import object_recordfrom memory.store import MemoryStore


class QueryIntent(Enum):
    FIND_OBJECT = auto()        # "where is my X"
    LIST_ZONE = auto()          # "what's on my desk"
    MOVEMENT_CHECK = auto()     # "did I move my X"
    LAST_SEEN = auto()          # "when did I last see X"
    CURRENT_VIEW = auto()       # "what can you see right now"
    UNKNOWN = auto()


class QueryResult:
    """Structured result of a memory query, passed to the responder."""

    def __init__(
        self,
        intent: QueryIntent,
        query_label: Optional[str] = None,
        query_zone: Optional[str] = None,
        records: Optional[list[ObjectRecord]] = None,
        now: Optional[datetime] = None,
    ) -> None:
        self.intent = intent        self.query_label = query_label        self.query_zone = query_zone        self.records: list[ObjectRecord] = records or []
        self.now = now or datetime.now()


#  Intent detection 

_FIND_PATTERNS = [
    r"\bwhere\s+(?:is|are)\b",
    r"\bcan(?:'t| not)? (?:you )?find\b",
    r"\blooking for\b",
    r"\bi can'?t find\b",
    r"\blocate\b",
    r"\bshow me\b",
]

_MOVEMENT_PATTERNS = [
    r"\bdid i (?:move|take|put|leave)\b",
    r"\bhas (?:my|the) .+ moved\b",
    r"\bwhere did i (?:put|leave|place)\b",
]

_LAST_SEEN_PATTERNS = [
    r"\bwhen did i last\b",
    r"\blast (?:seen|time)\b",
    r"\bhow long (?:since|ago)\b",
    r"\bwhen was\b",
]

_ZONE_PATTERNS = [
    r"\bwhat(?:'s| is) (?:on|in|at) (?:my |the )?\b(\w+)\b",
    r"\blist (?:everything|all|objects?) (?:on|in|at) (?:my |the )?\b(\w+)\b",
    r"\bwhat (?:objects?|things?) (?:are|is) (?:on|in|at) (?:my |the )?\b(\w+)\b",
]

_CURRENT_VIEW_PATTERNS = [
    r"\bwhat can you see\b",
    r"\bwhat(?:'s| is) (?:visible|in view|in the (?:room|frame|camera))\b",
    r"\bwhat(?:'s| do you see) (?:right )?now\b",
    r"\bcurrent(?:ly)? (?:visible|in view)\b",
    r"\bshow all objects\b",
]


def _extract_object_label(text: str) -> Optional[str]:
    """
    Extract the target object noun from a query.
    Strips possessives, determiners, and filler words.
    """
    # Remove common filler phrases
    cleaned = re.sub(
        r"\b(?:where(?:'s| is| are)|can you|find|locate|see|my|the|a|an|"
        r"i can'?t find|looking for|show me|did i (?:move|put|leave|take)|"
        r"when did i last (?:see)?|last seen|last time|how long since|"
        r"has|have|been|please|currently|right now)\b",
        " ",
        text,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ?.,!")

    # Take the remaining significant words
    words = [w for w in cleaned.split() if len(w) > 1]
    return " ".join(words[:3]) if words else None

def _extract_zone(text: str) -> Optional[str]:
    """Extract a zone name from a zone-query."""
    for pattern in _ZONE_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return m.group(1).lower()
    return None

def classify_intent(text: str) -> QueryIntent:
    """Classify the intent of a natural-language query."""
    t = text.lower()

    if any(re.search(p, t) for p in _CURRENT_VIEW_PATTERNS):
        return QueryIntent.CURRENT_VIEW
    if any(re.search(p, t) for p in _LAST_SEEN_PATTERNS):
        return QueryIntent.LAST_SEEN
    if any(re.search(p, t) for p in _MOVEMENT_PATTERNS):
        return QueryIntent.MOVEMENT_CHECK
    if any(re.search(p, t) for p in _ZONE_PATTERNS):
        return QueryIntent.LIST_ZONE
    if any(re.search(p, t) for p in _FIND_PATTERNS):
        return QueryIntent.FIND_OBJECT
    # Default: treat as find if there's a recognisable noun
    return QueryIntent.FIND_OBJECT

#  Query handler 

class QueryHandler:
    """
    Routes a natural language query to memory primitives and returns a
    QueryResult for the Responder to format.
    """

    def __init__(self, store: MemoryStore) -> None:
        self._store = store
    def handle(self, text: str) -> QueryResult:
        """Main entry point: parse and execute a query."""
        text = text.strip()
        now = datetime.now()
        intent = classify_intent(text)

        logger.debug("Query intent: {}  text={!r}", intent.name, text)

        if intent == QueryIntent.CURRENT_VIEW:
            return self._current_view(now)

        if intent == QueryIntent.LIST_ZONE:
            zone = _extract_zone(text)
            return self._list_zone(zone, now)

        # For everything else we need an object label
        label = _extract_object_label(text)

        if not label:
            return QueryResult(intent=QueryIntent.UNKNOWN, now=now)

        if intent == QueryIntent.LAST_SEEN:
            return self._last_seen(label, now)

        if intent == QueryIntent.MOVEMENT_CHECK:
            return self._movement_check(label, now)

        # FIND_OBJECT (default)
        return self._find_object(label, now)

    #  Intent handlers 

    def _find_object(self, label: str, now: datetime) -> QueryResult:
        records = self._store.query_by_label(label, include_stale=True)
        return QueryResult(
            intent=QueryIntent.FIND_OBJECT,
            query_label=label,
            records=records[:MAX_QUERY_RESULTS],
            now=now,
        )

    def _last_seen(self, label: str, now: datetime) -> QueryResult:
        records = self._store.query_by_label(label, include_stale=True)
        return QueryResult(
            intent=QueryIntent.LAST_SEEN,
            query_label=label,
            records=records[:1],
            now=now,
        )

    def _movement_check(self, label: str, now: datetime) -> QueryResult:
        records = self._store.query_by_label(label, include_stale=True)
        return QueryResult(
            intent=QueryIntent.MOVEMENT_CHECK,
            query_label=label,
            records=records[:1],
            now=now,
        )

    def _list_zone(self, zone: Optional[str], now: datetime) -> QueryResult:
        if zone:
            records = self._store.query_by_zone(zone)
        else:
            records = self._store.all_current(within_seconds=CURRENT_VISIBLE_WINDOW_SEC)

        records.sort(key=lambda r: r.last_seen, reverse=True)
        return QueryResult(
            intent=QueryIntent.LIST_ZONE,
            query_zone=zone or "current view",
            records=records[:MAX_QUERY_RESULTS],
            now=now,
        )

    def _current_view(self, now: datetime) -> QueryResult:
        records = self._store.all_current(within_seconds=CURRENT_VISIBLE_WINDOW_SEC)
        records.sort(key=lambda r: r.label)
        return QueryResult(
            intent=QueryIntent.CURRENT_VIEW,
            records=records[:MAX_QUERY_RESULTS],
            now=now,
        )