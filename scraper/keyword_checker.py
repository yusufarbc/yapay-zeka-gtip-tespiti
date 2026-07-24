TRIGGER_KEYWORDS = [
    "gümrük tarife cetveli",
    "ithalat rejimi kararında değişiklik",
    "tarife kontenjanı",
    "ek mali yükümlülük",
    "bağlayıcı tarife bilgisi",
    "gümrük genel tebliği"
]

def check_text_for_triggers(title: str, body_text: str = "") -> bool:
    combined = (title + " " + body_text).lower()
    for kw in TRIGGER_KEYWORDS:
        if kw in combined:
            return True
    return False
