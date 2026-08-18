import os
import sys

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from api.db.database import SessionLocal, GumrukEmsalKararModel
from api.db.tgtc_knowledge_base import OfficialBTBModel

def clear_mock_data():
    session = SessionLocal()
    try:
        print("Clearing old mock decisions from OfficialBTBModel...")
        deleted_btbs = session.query(OfficialBTBModel).filter(
            OfficialBTBModel.btb_no.like("RG-Gumruk Genel Tebli%") | OfficialBTBModel.btb_no.like("Teblig Takip%")
        ).delete(synchronize_session=False)
        
        print(f"Deleted {deleted_btbs} mock records from official_btbs table.")

        print("Clearing old mock decisions from GumrukEmsalKararModel...")
        deleted_emsal = session.query(GumrukEmsalKararModel).filter(
            GumrukEmsalKararModel.referans_no.like("Gumruk Genel Tebligi%") | GumrukEmsalKararModel.referans_no.like("Teblig Takip%")
        ).delete(synchronize_session=False)

        print(f"Deleted {deleted_emsal} mock records from gumruk_emsal_kararlar table.")

        session.commit()
        print("Successfully wiped mock data from database!")
    except Exception as e:
        session.rollback()
        print(f"Error: {e}")
    finally:
        session.close()

if __name__ == '__main__':
    clear_mock_data()
