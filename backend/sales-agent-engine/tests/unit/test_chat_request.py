"""What a chat message may be: long enough for a pasted document, plus the note naming attached files."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.api.chat import ATTACHMENT_NOTE_CHARS, MAX_MESSAGE_CHARS, ChatRequest


def test_a_message_can_be_as_long_as_the_app_allows_plus_the_attachment_note():
    assert ChatRequest(message="x" * MAX_MESSAGE_CHARS).message
    note = "\n\nAttached files (saved to the knowledge base; read them with the knowledge base tools before answering): a.pdf, b.docx"
    assert ChatRequest(message="x" * MAX_MESSAGE_CHARS + note).message


def test_longer_or_empty_messages_are_refused():
    with pytest.raises(ValidationError):
        ChatRequest(message="x" * (MAX_MESSAGE_CHARS + ATTACHMENT_NOTE_CHARS + 1))
    with pytest.raises(ValidationError):
        ChatRequest(message="")
