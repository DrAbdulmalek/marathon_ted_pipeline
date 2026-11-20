from pathlib import Path

from src.telegram_ingestion_state import TelegramIngestionState


def test_message_is_idempotent(tmp_path: Path):
    state = TelegramIngestionState(str(tmp_path / "state.sqlite3"))
    assert state.claim("channel-1", 10)
    state.mark_done("channel-1", 10)

    assert state.is_done("channel-1", 10)
    assert not state.claim("channel-1", 10)
    assert state.count_done("channel-1") == 1


def test_failed_claim_can_retry(tmp_path: Path):
    state = TelegramIngestionState(str(tmp_path / "state.sqlite3"))
    assert state.claim("channel-1", 11)
    assert not state.claim("channel-1", 11)

    state.release("channel-1", 11)
    assert state.claim("channel-1", 11)


def test_channels_are_isolated(tmp_path: Path):
    state = TelegramIngestionState(str(tmp_path / "state.sqlite3"))
    assert state.claim("channel-a", 1)
    state.mark_done("channel-a", 1)

    assert not state.claim("channel-a", 1)
    assert state.claim("channel-b", 1)


def test_cursor_persists(tmp_path: Path):
    state = TelegramIngestionState(str(tmp_path / "state.sqlite3"))
    assert state.get_cursor("channel-1") == 0
    state.set_cursor("channel-1", 42)

    reopened = TelegramIngestionState(str(tmp_path / "state.sqlite3"))
    assert reopened.get_cursor("channel-1") == 42
