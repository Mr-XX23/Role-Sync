"""Re-lists what actually exists at a connected source, for reconciliation.

Composio triggers are create/update oriented: providers do not reliably emit
delete or permission-change events ("because webhooks lie" - doc/arch.md). The
only dependable way to catch a missed deletion or ACL drift is to periodically
re-list the source and diff it against the canonical store.

SAFETY: every listing carries a `complete` flag. If a call fails, is truncated,
or the source cannot be exhaustively listed, `complete` is False and the sweeper
MUST NOT infer deletions from it - otherwise one failed API call would tombstone
a tenant's entire corpus.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Optional

# Sources whose contents are a bounded, listable set. Mailboxes and chat
# histories are unbounded streams: a partial page says nothing about deletion,
# so they are never swept for tombstones.
# These must match the `source` values actually persisted on documents, not the
# connector's colloquial name: calendar events are stored as "google_calendar",
# so keying this "calendar" made every calendar sweep match zero documents while
# still spending Composio executions.
SWEEPABLE_SOURCES = ("gdrive", "notion", "google_calendar")

# Colloquial names accepted from callers, mapped to the stored source value.
SOURCE_ALIASES = {"calendar": "google_calendar", "googlecalendar": "google_calendar"}
UNSWEEPABLE_REASON = (
    "source is an unbounded message stream; a partial listing cannot prove deletion"
)


# events.list allows up to 2500 events per page. With attendee lists trimmed to a
# single entry, a full page fits the Composio response limit for a real calendar
# (verified live). A calendar with unusually heavy events can still exceed it, so a
# too-large response halves the page and retries rather than failing the sweep.
_CALENDAR_PAGE_SIZE = 2500
_CALENDAR_MIN_PAGE_SIZE = 50


def _payload_too_large(error: Optional[str]) -> bool:
    """Composio rejects an oversized tool response with 413 Upstream_PayloadTooLarge.

    Matches the error code phrase, not a bare "413", which could appear by chance
    inside a request id.
    """
    if not error:
        return False
    text = error.lower()
    return "payloadtoolarge" in text or "error code: 413" in text


def _max_pages() -> int:
    try:
        return max(1, int(os.environ.get("RECONCILIATION_MAX_PAGES", "10")))
    except (TypeError, ValueError):
        return 10


@dataclass
class LiveListing:
    """What the source currently holds. `complete=False` disables deletion inference."""

    source: str
    items: list[dict[str, Any]] = field(default_factory=list)
    complete: bool = False
    reason: str = ""

    @property
    def external_ids(self) -> set[str]:
        return {str(item.get("external_id")) for item in self.items if item.get("external_id")}


class LiveSourceLister:
    """Lists live external ids (and ACLs where the provider returns them)."""

    def __init__(self, composio_client: Any) -> None:
        self.composio = composio_client
        # Message from the most recent failed call, so a caller can tell a response
        # that was merely too large (retry smaller) from a genuine failure.
        self._last_error: Optional[str] = None

    # ---- helpers ---------------------------------------------------------
    def _execute(self, slug: str, arguments: dict[str, Any], user_id: str) -> Optional[dict[str, Any]]:
        self._last_error = None
        try:
            res = self.composio._composio.tools.execute(
                slug=slug,
                arguments=arguments,
                user_id=user_id,
                dangerously_skip_version_check=True,
            )
            data = res.get("data", {}) if isinstance(res, dict) else getattr(res, "data", {})
            return data if isinstance(data, dict) else None
        except Exception as err:
            self._last_error = str(err)
            print(f"[LiveSourceLister] {slug} failed for user_id={user_id}: {err}")
            return None

    @staticmethod
    def _unwrap(data: dict[str, Any], *keys: str) -> list[dict[str, Any]]:
        for key in keys:
            value = data.get(key)
            if isinstance(value, list):
                return value
            nested = data.get("data")
            if isinstance(nested, dict) and isinstance(nested.get(key), list):
                return nested[key]
        return []

    # ---- per-source listings --------------------------------------------
    def list_source(self, source: str, user_id: str) -> LiveListing:
        key = (source or "").lower()
        key = SOURCE_ALIASES.get(key, key)
        if key not in SWEEPABLE_SOURCES:
            return LiveListing(source=key, complete=False, reason=UNSWEEPABLE_REASON)

        if key == "gdrive":
            return self._list_gdrive(user_id)
        if key == "notion":
            return self._list_notion(user_id)
        return self._list_calendar(user_id)

    def _list_gdrive(self, user_id: str) -> LiveListing:
        items: list[dict[str, Any]] = []
        page_token: Optional[str] = None
        for _ in range(_max_pages()):
            args: dict[str, Any] = {
                "pageSize": 1000,
                "supportsAllDrives": True,
                "includeItemsFromAllDrives": True,
            }
            if page_token:
                args["pageToken"] = page_token

            data = self._execute("GOOGLEDRIVE_LIST_FILES", args, user_id)
            if data is None:
                return LiveListing(source="gdrive", complete=False, reason="listing call failed")

            files = self._unwrap(data, "files")
            for entry in files:
                if not isinstance(entry, dict) or not entry.get("id"):
                    continue
                item: dict[str, Any] = {"external_id": str(entry["id"])}
                # Only carry acl when the provider actually returned permissions -
                # a missing field must not be read as "no one has access".
                permissions = entry.get("permissions")
                if isinstance(permissions, list):
                    item["acl"] = [
                        str(p.get("emailAddress") or p.get("id"))
                        for p in permissions
                        if isinstance(p, dict) and (p.get("emailAddress") or p.get("id"))
                    ]
                items.append(item)

            nested = data.get("data") if isinstance(data.get("data"), dict) else {}
            page_token = data.get("nextPageToken") or (nested.get("nextPageToken") if nested else None)
            if not page_token:
                return LiveListing(source="gdrive", items=items, complete=True)

        return LiveListing(source="gdrive", items=items, complete=False, reason="listing truncated at page cap")

    def _list_notion(self, user_id: str) -> LiveListing:
        data = self._execute("NOTION_SEARCH_NOTION_PAGE", {"page_size": 100}, user_id)
        if data is None:
            return LiveListing(source="notion", complete=False, reason="listing call failed")

        results = self._unwrap(data, "results", "pages")
        items = [
            {"external_id": str(entry["id"])}
            for entry in results
            if isinstance(entry, dict) and entry.get("id")
        ]
        nested = data.get("data") if isinstance(data.get("data"), dict) else {}
        has_more = bool(data.get("has_more") or (nested.get("has_more") if nested else False))
        if has_more:
            return LiveListing(source="notion", items=items, complete=False, reason="listing truncated (has_more)")
        return LiveListing(source="notion", items=items, complete=True)

    def _list_calendar(self, user_id: str) -> LiveListing:
        # GOOGLECALENDAR_EVENTS_LIST (Google events.list) is the only listing tool
        # Composio publishes for calendar, and there is deliberately no fallback:
        #   - GOOGLECALENDAR_LIST_EVENTS does not exist; trying it first 404ed on
        #     every sweep before the real tool ran.
        #   - GOOGLECALENDAR_FIND_EVENT nests results under "event_data", which
        #     _unwrap cannot read. Falling back to it yields an EMPTY listing that can
        #     look complete - exactly the weak evidence a sweep must never delete on.
        # A failed call therefore returns an incomplete listing, which deletes nothing.
        #
        # This paginates like _list_gdrive. It used to stop after one page of 250, so
        # any calendar larger than that was always "incomplete" and reconciliation
        # never removed a deleted event. singleEvents expands every recurring meeting
        # across all time, so real calendars run to thousands of instances.
        items: list[dict[str, Any]] = []
        page_token: Optional[str] = None
        page_size = _CALENDAR_PAGE_SIZE
        pages = 0
        while pages < _max_pages():
            args: dict[str, Any] = {
                "maxResults": page_size,
                # Expand recurring events into instances, matching how they are indexed.
                "singleEvents": True,
                # Only event ids are needed. Attendee lists are what push a full page
                # past the Composio response limit, so trim them to one entry.
                "maxAttendees": 1,
            }
            if page_token:
                args["pageToken"] = page_token

            data = self._execute("GOOGLECALENDAR_EVENTS_LIST", args, user_id)
            if data is None:
                # An oversized response says nothing is wrong with the calendar: retry
                # the same page smaller. The size only ever shrinks, which bounds this.
                if _payload_too_large(self._last_error) and page_size > _CALENDAR_MIN_PAGE_SIZE:
                    page_size = max(_CALENDAR_MIN_PAGE_SIZE, page_size // 2)
                    continue
                return LiveListing(source="google_calendar", complete=False, reason="listing call failed")

            pages += 1
            for entry in self._unwrap(data, "items", "events"):
                if isinstance(entry, dict) and entry.get("id"):
                    items.append({"external_id": str(entry["id"])})

            nested = data.get("data") if isinstance(data.get("data"), dict) else {}
            page_token = data.get("nextPageToken") or (nested.get("nextPageToken") if nested else None)
            if not page_token:
                return LiveListing(source="google_calendar", items=items, complete=True)

        return LiveListing(source="google_calendar", items=items, complete=False, reason="listing truncated at page cap")
