import urllib.request
import json

base_url = "https://gtip-backend-gu6pxpqefa-uc.a.run.app"

def test():
    print("=== CANLI TEST: Kullanıcının Girdiği 'ahşap sandalye' ===")
    url1 = f"{base_url}/api/v1/analyze-json"
    desc = "ahşap sandalye"
    data1 = json.dumps({"product_description": desc, "image_uri": None}).encode("utf-8")
    req1 = urllib.request.Request(url1, data=data1, headers={"Content-Type": "application/json"})

    with urllib.request.urlopen(req1, timeout=120) as resp1:
        res1 = json.loads(resp1.read().decode("utf-8"))

    print("STATUS:", res1.get("status"))
    print("GTIP:", res1.get("gtip_code"))
    hitl = res1.get("hitl_question")
    if hitl:
        print("HITL QUESTION ID:", hitl.get("question_id"))
        print("HITL QUESTION TEXT:", hitl.get("question_text"))
        print("HITL OPTIONS:")
        for opt in hitl.get("options", []):
            print(f"  [{opt['option_id']}] {opt['text']}")
        
        # Test responding to the question:
        print("\n=== 2. ADIM: HITL Sorusuna Yanıt Gönderiliyor ===")
        selected_opt = hitl["options"][0]["option_id"]
        url2 = f"{base_url}/api/v1/hitl/respond"
        data2 = json.dumps({
            "session_id": res1["session_id"],
            "question_id": hitl["question_id"],
            "selected_option_id": selected_opt,
            "custom_note": "Kullanıcı tercihi"
        }).encode("utf-8")
        req2 = urllib.request.Request(url2, data=data2, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req2, timeout=120) as resp2:
            res2 = json.loads(resp2.read().decode("utf-8"))
        print("FINAL STATUS:", res2.get("status"))
        print("FINAL GTIP:", res2.get("gtip_code"))
        print("FINAL STATUTE:", res2.get("official_statute_text"))
        print("FINAL AUDIT:", res2.get("audit_notes"))
        print("FINAL LEGAL SOURCES COUNT:", len(res2.get("legal_sources", [])))
    else:
        print("AUDIT NOTES:", res1.get("audit_notes"))

if __name__ == "__main__":
    test()
