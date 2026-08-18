import os
import sys

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from scripts.scrape_rg_siniflandirma_2020_2026 import parse_customs_pdf

def test_pdf():
    pdf_path = os.path.join(root_dir, "2026 TGTC", "20251230M1-2.pdf")
    if not os.path.exists(pdf_path):
        print("PDF not found!")
        return
        
    print(f"Parsing {pdf_path}...")
    decisions = parse_customs_pdf(pdf_path)
    print(f"Found {len(decisions)} decisions!")
    for d in decisions[:5]:
        print(d)

if __name__ == "__main__":
    test_pdf()
