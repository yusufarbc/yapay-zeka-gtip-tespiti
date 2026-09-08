"""
İki Aşamalı Hukuki Arama Protokolü (MCP / Tool Engine).
gcp_architecture_report.md Bölüm 5 Şartnamesi:
1. Aşama (Keşif): LLM anlamsal sorgu atar; veritabanı sadece en alakalı 3 kaydın UUID ve başlık bilgisini döner.
2. Aşama (Kesin Getirme): LLM, listelenen UUID'ler arasından seçim yaparak fetch_exact_article_by_id(uuid) çağırır.
   Veritabanından ham metin ve doğrulanmış URL çekilir.
"""

import logging
import re
from typing import List, Dict, Any, Optional
from google.genai import types
from sqlalchemy.orm import Session
from sqlalchemy import or_, text
from api.modules.vertex_client import generate_embedding
from api.db.database import GumrukMevzuatMaddesiModel, SessionLocal

logger = logging.getLogger(__name__)

mcp_customs_tools = [
    types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name="search_customs_articles",
                description="Mevzuatta semantik arama yaparak ilgili madde UUID'lerini ve başlıklarını listeler (Aşama 1: Keşif).",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "query": types.Schema(type=types.Type.STRING, description="Aranacak hukuki konu, tarife tanımı veya mevzuat sorusu")
                    },
                    required=["query"]
                )
            ),
            types.FunctionDeclaration(
                name="fetch_exact_article_by_id",
                description="Belirtilen UUID'ye sahip resmi mevzuat maddesinin harfi harfine ham metnini ve Resmi Gazete linkini getirir (Aşama 2: Kesin Getirme).",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "article_id": types.Schema(type=types.Type.STRING, description="Maddenin benzersiz UUID değeri")
                    },
                    required=["article_id"]
                )
            )
        ]
    )
]

def execute_search_customs_articles(query: str, session: Optional[Session] = None) -> List[Dict[str, Any]]:
    """
    1. Aşama (Keşif):
    Semantik vektör araması ile en alakalı ilk 3 maddeyi UUID ve başlık olarak listeler.
    """
    close_session = False
    if session is None:
        session = SessionLocal()
        close_session = True

    try:
        query_vector = generate_embedding(query)
        
        # 1. PostgreSQL pgvector / AlloyDB ScaNN ortamı
        if session.bind.dialect.name == "postgresql" and query_vector and any(query_vector):
            sql_query = text("""
                SELECT id, kanun_no, madde_kodu, tarih,
                       1 - (icerik_vektor <=> CAST(:vector AS vector)) AS similarity
                FROM gumruk_mevzuat_maddeleri
                WHERE icerik_vektor IS NOT NULL
                ORDER BY icerik_vektor <=> CAST(:vector AS vector)
                LIMIT 3;
            """)
            result = session.execute(sql_query, {"vector": str(query_vector)}).fetchall()
            if result:
                return [
                    {
                        "article_id": str(r[0]),
                        "summary": f"{r[1]} Sayılı Kanun {r[2]} ({r[3]})",
                        "similarity": round(float(r[4]), 4)
                    }
                    for r in result
                ]

        # 2. Embedding yoksa PostgreSQL ve SQLite için deterministik metin araması.
        search_terms = [
            term for term in re.findall(r"[\wçğıöşüÇĞİÖŞÜ]+", query)
            if len(term) >= 3
        ][:6]
        if not search_terms:
            return []
        conditions = []
        for term in search_terms:
            conditions.extend([
                GumrukMevzuatMaddesiModel.madde_metni.ilike(f"%{term}%"),
                GumrukMevzuatMaddesiModel.madde_kodu.ilike(f"%{term}%"),
                GumrukMevzuatMaddesiModel.kanun_no.ilike(f"%{term}%"),
            ])
        items = session.query(GumrukMevzuatMaddesiModel).filter(or_(*conditions)).limit(3).all()
        
        if items:
            return [
                {
                    "article_id": str(item.id),
                    "summary": f"{item.kanun_no} Sayılı Kanun {item.madde_kodu} ({item.tarih})",
                    "similarity": 0.95
                }
                for item in items
            ]
            
        return []
    except Exception as e:
        logger.warning(f"[MCP Customs Tool] search_customs_articles hatası: {e}")
        return []
    finally:
        if close_session:
            session.close()

def execute_fetch_exact_article_by_id(article_id: str, session: Optional[Session] = None) -> Dict[str, Any]:
    """
    2. Aşama (Kesin Getirme):
    UUID ile veritabanındaki Resmi Gazete ham metnini ve doğrulanmış URL'yi döner.
    """
    close_session = False
    if session is None:
        session = SessionLocal()
        close_session = True

    try:
        item = session.query(GumrukMevzuatMaddesiModel).filter(
            GumrukMevzuatMaddesiModel.id == article_id
        ).first()

        if item:
            return {
                "kanun_no": item.kanun_no,
                "madde_kodu": item.madde_kodu,
                "ham_metin": item.madde_metni,
                "kaynak_url": item.kaynak_url,
                "resmi_gazete": f"{item.tarih} / Sayı: {item.resmi_gazete_sayisi}"
            }
        return {"error": "Belirtilen ID'ye sahip mevzuat maddesi bulunamadı."}
    except Exception as e:
        logger.error(f"[MCP Customs Tool] fetch_exact_article_by_id hatası: {e}")
        return {"error": str(e)}
    finally:
        if close_session:
            session.close()
