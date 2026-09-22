"""Cloud Logging severity eşlemesinin doğrulanması.

Üretimde uygulama logları düz metin gittiği için `severity` boş kalıyordu ve
`severity>=ERROR` üzerine alarm kurulamıyordu. Bu testler eşlemenin geri
kaymasını engeller.
"""

import json
import logging

from api.logging_config import CloudLoggingFormatter


def _emit(level: int, message: str, **extra) -> dict:
    record = logging.LogRecord(
        name="TestLogger", level=level, pathname=__file__, lineno=1,
        msg=message, args=(), exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return json.loads(CloudLoggingFormatter().format(record))


def test_every_level_maps_to_cloud_logging_severity():
    assert _emit(logging.DEBUG, "d")["severity"] == "DEBUG"
    assert _emit(logging.INFO, "i")["severity"] == "INFO"
    assert _emit(logging.WARNING, "w")["severity"] == "WARNING"
    assert _emit(logging.ERROR, "e")["severity"] == "ERROR"
    assert _emit(logging.CRITICAL, "c")["severity"] == "CRITICAL"


def test_extra_fields_become_queryable_json_payload():
    """Log-based metric'ler metin ayrıştırmadan bu alanlardan türetilir."""
    payload = _emit(logging.INFO, "pipeline", session_id="abc", duration_ms=12.5, btb_hits=3)
    assert payload["session_id"] == "abc"
    assert payload["duration_ms"] == 12.5
    assert payload["btb_hits"] == 3
    assert payload["logger"] == "TestLogger"


def test_exception_carries_stack_trace():
    try:
        raise ValueError("patladı")
    except ValueError:
        import sys
        record = logging.LogRecord(
            name="TestLogger", level=logging.ERROR, pathname=__file__, lineno=1,
            msg="hata", args=(), exc_info=sys.exc_info(),
        )
    payload = json.loads(CloudLoggingFormatter().format(record))
    assert payload["severity"] == "ERROR"
    assert "ValueError" in payload["stack_trace"]


def test_output_is_single_line_json():
    """Çok satırlı çıktı Cloud Logging'de ayrı girdilere bölünür."""
    record = logging.LogRecord(
        name="TestLogger", level=logging.INFO, pathname=__file__, lineno=1,
        msg="birinci satır\nikinci satır", args=(), exc_info=None,
    )
    rendered = CloudLoggingFormatter().format(record)
    assert "\n" not in rendered
    assert json.loads(rendered)["message"] == "birinci satır\nikinci satır"


def test_unserializable_extra_does_not_break_logging():
    payload = _emit(logging.INFO, "m", weird=object())
    assert isinstance(payload["weird"], str)
