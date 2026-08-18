import os
import sys

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from api.db.database import SessionLocal, GumrukEmsalKararModel
from api.db.tgtc_knowledge_base import OfficialBTBModel

def clean_database():
    print("Connecting to DB...")
    session = SessionLocal()
    
    count1 = session.query(OfficialBTBModel).count()
    count2 = session.query(GumrukEmsalKararModel).count()
    print(f"Found {count1} records in OfficialBTBModel, {count2} records in GumrukEmsalKararModel.")
    
    if count1 > 0:
        session.query(OfficialBTBModel).delete()
    if count2 > 0:
        session.query(GumrukEmsalKararModel).delete()
        
    session.commit()
    print("Deleted all records from both tables.")
    
    t1 = session.query(OfficialBTBModel).count()
    t2 = session.query(GumrukEmsalKararModel).count()
    print(f"Remaining: OfficialBTBModel={t1}, GumrukEmsalKararModel={t2}")
    session.close()

if __name__ == "__main__":
    clean_database()
