import urllib.request
import json
import sys

base_url = "https://gtip-web-gu6pxpqefa-uc.a.run.app"

def test():
    print("=== CANLI DOĞRULAMA TESTİ: 'ahşap sandalye' (Web Nginx Proxy Üzerinden) ===")
    url1 = f"{base_url}/api/v1/analyze-json"
    desc = "ahşap sandalye"
    data1 = json.dumps({"product_description": desc, "image_uri": None}).encode("utf-8")
    req1 = urllib.request.Request(url1, data=data1, headers={"Content-Type": "application/json"})

    with urllib.request.urlopen(req1, timeout=120) as resp1:
        res = json.loads(resp1.read().decode("utf-8"))

    step = 1
    session_id = res.get("session_id")
    print(f"\n[Adım {step}] Durum: {res.get('status')}, GTİP: {res.get('gtip_code')}")

    while res.get("status") == "WAITING_FOR_USER":
        hitl = res.get("hitl_question")
        if not hitl:
            print("HATA: WAITING_FOR_USER durumunda hitl_question bulunamadı!")
            sys.exit(1)
        
        print(f"\n--- Soru {step}: {hitl.get('question_text')} ---")
        options = hitl.get("options", [])
        for opt in options:
            print(f"  [{opt['option_id']}] {opt['text']}")

        # İlk uygulanabilir seçeneği seç (DISC_0 -> C2 veya C1)
        chosen = options[0]["option_id"]
        # Eğer DISC_0 seçilmişse 2. adımda C2'yi tercih et (genel kullanım)
        if step == 2 and any(o["option_id"] == "C2" for o in options):
            chosen = "C2"

        print(f"-> Seçilen Seçenek: [{chosen}]")
        url_respond = f"{base_url}/api/v1/hitl/respond"
        data_respond = json.dumps({
            "session_id": session_id,
            "question_id": hitl["question_id"],
            "selected_option_id": chosen,
            "custom_note": "Otomatik doğrulama"
        }).encode("utf-8")
        req_respond = urllib.request.Request(url_respond, data=data_respond, headers={"Content-Type": "application/json"})
        
        with urllib.request.urlopen(req_respond, timeout=120) as resp_next:
            res = json.loads(resp_next.read().decode("utf-8"))
        
        step += 1
        print(f"[Adım {step}] Durum: {res.get('status')}, GTİP: {res.get('gtip_code')}")

    print("\n==================== DOĞRULAMA SONUCU ====================")
    print(f"Nihai Durum: {res.get('status')}")
    print(f"Nihai 12 Haneli GTİP: {res.get('gtip_code')}")
    print(f"Güven Skoru: %{int(res.get('confidence_score', 0) * 100)}")
    print(f"Resmi Mevzuat: {res.get('official_statute_text')[:120]}...")
    print(f"Uygulanan GİR: {res.get('applied_gir_rules')}")
    print(f"Gerekçe Kayıtları: {res.get('audit_notes')}")

    assert res.get("status") == "COMPLETED", f"Beklenen COMPLETED fakat durum: {res.get('status')}"
    assert str(res.get("gtip_code")).replace(".", "").startswith("9401"), "GTİP 9401 ile başlamalıdır"
    print("\n>>> BAŞARILI: Canlı sistem çok adımlı soru-cevap ve nihai 12 haneli GTİP atamasını kusursuz tamamladı! <<<")

if __name__ == "__main__":
    test()
