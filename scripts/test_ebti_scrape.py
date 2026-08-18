import os
import sys

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from scripts.sync_customs_data import scrape_eu_ebti, scrape_ggm_btb

def test_ebti():
    print("Scraping EU EBTI...")
    ebti_decisions = scrape_eu_ebti()
    print(f"Found {len(ebti_decisions)} EBTI decisions.")
    
    print("Scraping GGM BTB...")
    ggm_decisions = scrape_ggm_btb()
    print(f"Found {len(ggm_decisions)} GGM decisions.")

if __name__ == "__main__":
    test_ebti()
