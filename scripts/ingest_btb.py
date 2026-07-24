import json
import os

def clean_and_ingest_btb(input_file: str, output_file: str):
    """
    Ticaret Bakanlığı BTB ham verilerini temizler ve vektör indekslemeye uygun hale getirir.
    """
    if not os.path.exists(input_file):
        print(f"Girdi dosyası bulunamadı: {input_file}")
        return

    with open(input_file, "r", encoding="utf-8") as f:
        raw_btbs = json.load(f)

    cleaned_records = []
    for btb in raw_btbs:
        gtip = btb.get("gtip_code", "").replace(".", "").strip()
        cleaned_records.append({
            "btb_no": btb.get("btb_no"),
            "gtip_code": btb.get("gtip_code"),
            "chapter": gtip[:2] if len(gtip) >= 2 else "",
            "heading": gtip[:4] if len(gtip) >= 4 else "",
            "issue_date": btb.get("issue_date"),
            "product_description": btb.get("product_description", "").strip(),
            "legal_justification": btb.get("legal_justification", "").strip()
        })

    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(cleaned_records, f, ensure_ascii=False, indent=2)

    print(f"ETL İşlemi Başarılı! {len(cleaned_records)} adet BTB kaydı işlendi: {output_file}")

if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    inp = os.path.join(base_dir, "api", "data", "mock_btb_data.json")
    out = os.path.join(base_dir, "api", "data", "cleaned_btb_vector_index.json")
    clean_and_ingest_btb(inp, out)
