"""Cloud Logging uyumlu yapılandırılmış loglama.

Uygulama düz metin stdout'a yazdığında Cloud Logging `severity` alanını
dolduramaz: `logger.error` ile `logger.info` aynı seviyede görünür ve
`severity>=ERROR` üzerine alarm kurulamaz. Üretim loglarında bu davranış
doğrulandı (tüm uygulama satırlarında severity boş).

Bu modül kök logger'ı, Cloud Logging'in özel alan olarak tanıdığı JSON
yapısına ("structured logging") çevirir. Uvicorn kendi logger'larını
`propagate=False` ile yönettiği için erişim logları etkilenmez.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any, Dict

# Cloud Logging'in LogSeverity enum'u ile birebir eşleşme.
_SEVERITY_BY_LEVEL: Dict[str, str] = {
    "DEBUG": "DEBUG",
    "INFO": "INFO",
    "WARNING": "WARNING",
    "ERROR": "ERROR",
    "CRITICAL": "CRITICAL",
}

# LogRecord'un standart alanları; bunlar dışındaki her şey çağıranın
# `extra=` ile geçirdiği yapılandırılmış alandır.
_RESERVED = frozenset(vars(logging.LogRecord("", 0, "", 0, "", (), None)).keys()) | {
    "asctime", "message", "taskName",
}


class CloudLoggingFormatter(logging.Formatter):
    """LogRecord'u Cloud Logging'in ayrıştırdığı tek satırlık JSON'a çevirir."""

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "severity": _SEVERITY_BY_LEVEL.get(record.levelname, "DEFAULT"),
            "message": record.getMessage(),
            "logger": record.name,
        }

        if record.exc_info:
            payload["stack_trace"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack_info"] = self.formatStack(record.stack_info)

        # `logger.info("...", extra={"session_id": ...})` ile geçirilen alanlar
        # Cloud Logging'de sorgulanabilir jsonPayload alanları olur; böylece
        # log-based metric'ler metin ayrıştırmadan türetilebilir.
        for key, value in record.__dict__.items():
            if key in _RESERVED or key.startswith("_"):
                continue
            try:
                json.dumps(value)
            except (TypeError, ValueError):
                value = repr(value)
            payload[key] = value

        return json.dumps(payload, ensure_ascii=False, default=str)


def configure(level: int = logging.INFO) -> None:
    """Kök logger'ı JSON formatına alır. Uygulama kurulmadan ÖNCE çağrılmalıdır."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(CloudLoggingFormatter())

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level)
