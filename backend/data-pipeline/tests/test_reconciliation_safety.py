"""Reconciliation must never tombstone documents on weak evidence.

A sweep decides what to DELETE, so these pin the guards: an incomplete listing
proves nothing, a mass deletion is refused, and a provider that omits
permissions must not be read as "nobody has access".
"""
from datetime import datetime, timezone

from module_1_document_processing.composio_connector.events.canonical_event import CanonicalEvent, EventType
from module_1_document_processing.del_acl_and_reconc.acl_sync import ACLSyncService
from module_1_document_processing.del_acl_and_reconc.deletion_handler import DeletionHandler
from module_1_document_processing.del_acl_and_reconc.live_source_lister import (
    SWEEPABLE_SOURCES,
    LiveListing,
    LiveSourceLister,
)
from module_1_document_processing.del_acl_and_reconc.reconciliation_sweeper import ReconciliationSweeper
from module_1_document_processing.pipeline.canonical_store import CanonicalStore

TENANT = "tenant_recon"
SOURCE = "gdrive"


def _seed(store: CanonicalStore, external_ids, acl=("u1@example.com",)):
    for ext in external_ids:
        store.record_event(
            CanonicalEvent(
                event_id=f"evt_{ext}", event_type=EventType.CREATE, source=SOURCE,
                tenant_id=TENANT, user_id="u1", external_id=ext, raw_ref={},
                acl=list(acl), timestamp=datetime.now(timezone.utc),
            ),
            status="PARSED_SUCCESS",
        )


def _sweeper(store):
    return ReconciliationSweeper(store, DeletionHandler(store), ACLSyncService(store))


def test_incomplete_listing_never_deletes():
    store = CanonicalStore()
    _seed(store, ["f1", "f2"])

    report = _sweeper(store).sweep_source(TENANT, SOURCE, live_source_docs=[], complete=False)

    assert report.missed_deletions_found == 2, "absences should still be detected"
    assert report.corrections_applied == 0, "but nothing may be tombstoned"
    assert report.skipped_deletions == 2
    assert store.get_document(f"{TENANT}:{SOURCE}:u1:f1").status != "DELETED"


def test_mass_deletion_is_refused():
    store = CanonicalStore()
    _seed(store, [f"f{i}" for i in range(6)])

    # Only one of six survives at the source -> 83% deletion, over the 50% limit.
    report = _sweeper(store).sweep_source(
        TENANT, SOURCE, live_source_docs=[{"external_id": "f0"}], complete=True
    )

    assert report.aborted is True
    assert report.corrections_applied == 0
    assert report.skipped_deletions == 5
    assert "safety limit" in report.reason
    assert store.get_document(f"{TENANT}:{SOURCE}:u1:f3").status != "DELETED"


def test_deletion_applied_when_listing_is_complete_and_modest():
    store = CanonicalStore()
    _seed(store, ["keep", "gone"])

    report = _sweeper(store).sweep_source(
        TENANT, SOURCE, live_source_docs=[{"external_id": "keep"}], complete=True
    )

    assert report.aborted is False
    assert report.corrections_applied == 1
    assert store.get_document(f"{TENANT}:{SOURCE}:u1:gone").status == "DELETED"
    assert store.get_document(f"{TENANT}:{SOURCE}:u1:keep").status != "DELETED"


def test_missing_acl_field_does_not_rewrite_permissions():
    store = CanonicalStore()
    _seed(store, ["f1"], acl=["u1@example.com", "u2@example.com"])

    # Provider returned the file but reported no permissions at all.
    report = _sweeper(store).sweep_source(
        TENANT, SOURCE, live_source_docs=[{"external_id": "f1"}], complete=True
    )

    assert report.acl_drift_found == 0
    assert "u2@example.com" in store.get_document(f"{TENANT}:{SOURCE}:u1:f1").acl


def test_reported_acl_drift_is_corrected():
    store = CanonicalStore()
    _seed(store, ["f1"], acl=["u1@example.com"])

    report = _sweeper(store).sweep_source(
        TENANT,
        SOURCE,
        live_source_docs=[{"external_id": "f1", "acl": ["u1@example.com", "u9@example.com"]}],
        complete=True,
    )

    assert report.acl_drift_found == 1
    assert "u9@example.com" in store.get_document(f"{TENANT}:{SOURCE}:u1:f1").acl


def test_unbounded_sources_are_not_sweepable():
    """Mailboxes and chat histories cannot prove deletion from a partial page."""
    assert "gmail" not in SWEEPABLE_SOURCES
    assert "slack" not in SWEEPABLE_SOURCES

    listing = LiveSourceLister(composio_client=None).list_source("gmail", "u1")
    assert isinstance(listing, LiveListing)
    assert listing.complete is False
    assert listing.items == []


def test_failed_listing_is_marked_incomplete():
    class _Boom:
        class _composio:
            class tools:
                @staticmethod
                def execute(**_kwargs):
                    raise RuntimeError("composio down")

    listing = LiveSourceLister(_Boom()).list_source("gdrive", "u1")
    assert listing.complete is False
    assert listing.items == []


class _Reply(dict):
    """A whole Composio response, served as-is instead of being wrapped as {"data": page}."""


def _rejected(message="Invalid page token value.", status_code=400):
    """What Composio returns - without raising - when the provider rejects the call.

    Shape observed live for GOOGLECALENDAR_EVENTS_LIST with an invalid page token and
    with an unknown calendar id: successful=False, and data holding only the error.
    """
    return _Reply(
        successful=False,
        error=message,
        data={"http_error": message, "message": message, "status_code": status_code},
    )


class _RecordingCalendar:
    """Fake Composio client that serves scripted calendar pages and records calls."""

    def __init__(self, pages):
        self.pages = list(pages)
        self.calls = []
        outer = self

        class _Tools:
            @staticmethod
            def execute(**kwargs):
                outer.calls.append(kwargs)
                if not outer.pages:
                    raise RuntimeError("no more pages scripted")
                page = outer.pages.pop(0)
                if isinstance(page, Exception):
                    raise page
                if isinstance(page, _Reply):
                    return dict(page)
                return {"data": page}

        class _Composio:
            tools = _Tools

        self._composio = _Composio


def test_calendar_listing_follows_every_page():
    """A calendar bigger than one page must still yield a COMPLETE listing.

    It used to stop after a single page of 250, so every real calendar was
    "incomplete" and reconciliation silently never removed a deleted event.
    """
    fake = _RecordingCalendar([
        {"items": [{"id": "e1"}, {"id": "e2"}], "nextPageToken": "page-2"},
        {"items": [{"id": "e3"}]},
    ])

    listing = LiveSourceLister(fake).list_source("google_calendar", "u1")

    assert listing.complete is True
    assert listing.external_ids == {"e1", "e2", "e3"}
    assert "pageToken" not in fake.calls[0]["arguments"]
    assert fake.calls[1]["arguments"]["pageToken"] == "page-2"
    # Attendee lists are what overflow the Composio response limit; ids are all we need.
    assert all(call["arguments"]["maxAttendees"] == 1 for call in fake.calls)


def test_calendar_listing_calls_only_the_tool_composio_publishes():
    """GOOGLECALENDAR_LIST_EVENTS does not exist; trying it first cost a 404 per sweep."""
    fake = _RecordingCalendar([{"items": [{"id": "e1"}]}])

    LiveSourceLister(fake).list_source("calendar", "u1")  # colloquial alias

    assert [call["slug"] for call in fake.calls] == ["GOOGLECALENDAR_EVENTS_LIST"]


def test_calendar_listing_never_falls_back_to_an_unreadable_shape():
    """A failed call must not fall back to FIND_EVENT: its results sit under
    "event_data", which the lister cannot read, so the fallback would produce an
    empty listing that can pass for complete and look like everything was deleted.
    """
    fake = _RecordingCalendar([])  # the only call raises

    listing = LiveSourceLister(fake).list_source("google_calendar", "u1")

    assert listing.complete is False
    assert listing.items == []
    assert [call["slug"] for call in fake.calls] == ["GOOGLECALENDAR_EVENTS_LIST"]


def test_calendar_listing_that_fails_part_way_is_incomplete():
    fake = _RecordingCalendar([{"items": [{"id": "e1"}], "nextPageToken": "p2"}])  # page 2 raises

    listing = LiveSourceLister(fake).list_source("google_calendar", "u1")

    assert listing.complete is False
    assert listing.items == []


def test_calendar_listing_truncated_at_the_page_cap_is_incomplete(monkeypatch):
    monkeypatch.setenv("RECONCILIATION_MAX_PAGES", "2")
    fake = _RecordingCalendar([
        {"items": [{"id": "e1"}], "nextPageToken": "p2"},
        {"items": [{"id": "e2"}], "nextPageToken": "p3"},
    ])

    listing = LiveSourceLister(fake).list_source("google_calendar", "u1")

    assert listing.complete is False
    assert len(fake.calls) == 2


def _seed_calendar(store: CanonicalStore, external_ids):
    """Calendar events are persisted under source="google_calendar"; keying them
    "calendar" is the mismatch that once made every calendar sweep match nothing."""
    for ext in external_ids:
        store.record_event(
            CanonicalEvent(
                event_id=f"evt_{ext}", event_type=EventType.CREATE, source="google_calendar",
                tenant_id=TENANT, user_id="u1", external_id=ext, raw_ref={},
                acl=["u1@example.com"], timestamp=datetime.now(timezone.utc),
            ),
            status="PARSED_SUCCESS",
        )


def test_multi_page_calendar_now_lets_a_deleted_event_be_tombstoned():
    """The outcome the fix exists for, end to end through lister and sweeper.

    Before, a calendar spanning more than one page was always an incomplete
    listing, so an event deleted in Google Calendar stayed in the index forever.
    """
    store = CanonicalStore()
    _seed_calendar(store, ["e1", "e2", "e3", "gone"])
    fake = _RecordingCalendar([
        {"items": [{"id": "e1"}, {"id": "e2"}], "nextPageToken": "p2"},
        {"items": [{"id": "e3"}]},
    ])

    listing = LiveSourceLister(fake).list_source("google_calendar", "u1")
    report = _sweeper(store).sweep_source(
        TENANT, "google_calendar", live_source_docs=listing.items, complete=listing.complete
    )

    assert listing.complete is True
    assert report.aborted is False
    assert report.corrections_applied == 1
    assert store.get_document(f"{TENANT}:google_calendar:u1:gone").status == "DELETED"
    assert store.get_document(f"{TENANT}:google_calendar:u1:e3").status != "DELETED"


def test_truncated_calendar_listing_still_deletes_nothing():
    """The safety rule must survive the fix: running out of pages proves nothing."""
    store = CanonicalStore()
    _seed_calendar(store, ["e1", "e2", "gone"])

    report = _sweeper(store).sweep_source(
        TENANT, "google_calendar",
        live_source_docs=[{"external_id": "e1"}, {"external_id": "e2"}],
        complete=False,
    )

    assert report.corrections_applied == 0
    assert report.skipped_deletions == 1
    assert store.get_document(f"{TENANT}:google_calendar:u1:gone").status != "DELETED"


def _too_large():
    """The error Composio raises when a tool response exceeds its size limit."""
    return RuntimeError(
        "Error code: 413 - {'error': {'message': 'The tool response payload is too large.', "
        "'slug': 'Upstream_PayloadTooLarge', 'status': 413}}"
    )


def test_calendar_listing_shrinks_the_page_when_the_response_is_too_large():
    """A heavy calendar must not silently disable reconciliation: halve and retry."""
    fake = _RecordingCalendar([_too_large(), {"items": [{"id": "e1"}]}])

    listing = LiveSourceLister(fake).list_source("google_calendar", "u1")

    assert listing.complete is True
    assert [call["arguments"]["maxResults"] for call in fake.calls] == [2500, 1250]


def test_calendar_listing_gives_up_once_even_the_smallest_page_is_too_large():
    fake = _RecordingCalendar([_too_large() for _ in range(20)])

    listing = LiveSourceLister(fake).list_source("google_calendar", "u1")

    assert listing.complete is False
    assert listing.reason == "listing call failed"
    sizes = [call["arguments"]["maxResults"] for call in fake.calls]
    assert sizes == [2500, 1250, 625, 312, 156, 78, 50], "shrinking must stop at the floor"


def test_a_413_inside_a_request_id_is_not_mistaken_for_an_oversized_response():
    """Retrying on any "413" substring would loop on unrelated failures."""
    unrelated = RuntimeError("Error code: 500 - {'error': {'request_id': 'ab4130cd', 'status': 500}}")
    fake = _RecordingCalendar([unrelated])

    listing = LiveSourceLister(fake).list_source("google_calendar", "u1")

    assert listing.complete is False
    assert len(fake.calls) == 1


# --- calls the provider rejected --------------------------------------------
# Composio does not raise when Google rejects a call: it answers successful=False
# with only the error in data - no items and no next-page token, which is exactly
# what the last page of a listing looks like.


def test_a_rejected_first_page_is_a_failed_listing_not_an_empty_calendar():
    fake = _RecordingCalendar([_rejected("Calendar not found for ID 'primary'.", 404)])

    listing = LiveSourceLister(fake).list_source("google_calendar", "u1")

    assert listing.complete is False
    assert listing.items == []


def test_a_rejected_later_page_does_not_pass_the_first_page_off_as_the_whole_calendar():
    fake = _RecordingCalendar([{"items": [{"id": "e1"}], "nextPageToken": "p2"}, _rejected()])

    listing = LiveSourceLister(fake).list_source("google_calendar", "u1")

    assert listing.complete is False
    assert listing.items == []


def test_a_rejected_page_deletes_nothing_end_to_end():
    """With fewer than 5 documents the mass-deletion guard does not apply, so the
    listing is the only thing standing between a failed call and a tombstone."""
    store = CanonicalStore()
    _seed_calendar(store, ["e1", "e2", "e3"])
    fake = _RecordingCalendar([{"items": [{"id": "e1"}], "nextPageToken": "p2"}, _rejected()])

    listing = LiveSourceLister(fake).list_source("google_calendar", "u1")
    report = _sweeper(store).sweep_source(
        TENANT, "google_calendar", live_source_docs=listing.items, complete=listing.complete
    )

    assert report.corrections_applied == 0
    for ext in ("e1", "e2", "e3"):
        assert store.get_document(f"{TENANT}:google_calendar:u1:{ext}").status != "DELETED"


def test_an_oversized_response_reported_without_raising_still_shrinks_the_page():
    fake = _RecordingCalendar([_rejected("Upstream_PayloadTooLarge", 413), {"items": [{"id": "e1"}]}])

    listing = LiveSourceLister(fake).list_source("google_calendar", "u1")

    assert listing.complete is True
    assert [call["arguments"]["maxResults"] for call in fake.calls] == [2500, 1250]


def test_drive_and_notion_listings_the_provider_rejects_are_incomplete():
    class _Rejecting:
        class _composio:
            class tools:
                @staticmethod
                def execute(**_kwargs):
                    return dict(_rejected("Request had insufficient authentication scopes.", 403))

    for source in ("gdrive", "notion"):
        listing = LiveSourceLister(_Rejecting()).list_source(source, "u1")
        assert listing.complete is False, source
        assert listing.items == [], source
