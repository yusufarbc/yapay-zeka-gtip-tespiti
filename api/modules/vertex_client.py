"""
Vertex AI / Google GenAI SDK Merkezi İstemci Modülü.
us-central1 bölgesinde Vertex AI entegrasyonu (gemini-2.5-flash, gemini-2.5-flash-lite, gemini-2.5-pro, text-embedding-005)
ve Application Default Credentials (ADC) yönetimi.
"""

import os
import logging
from typing import List, Optional
from api.config import settings

logger = logging.getLogger(__name__)

_genai_client = None

def get_genai_client():
    """
    Singleton Google GenAI / Vertex AI istemcisi döndürür.
    Production / GCP ortamında ADC ile Vertex AI modunu kullanır:
        genai.Client(vertexai=True, project=settings.GCP_PROJECT_ID, location=settings.GCP_REGION)
    Geliştirme veya API Key fallback durumunda:
        genai.Client(api_key=settings.GEMINI_API_KEY)
    """
    global _genai_client
    if _genai_client is not None:
        return _genai_client

    try:
        from google import genai

        # 1. Öncelik: Vertex AI (GCP Cloud Run / ADC)
        if not settings.USE_GCP_EMULATOR:
            try:
                _genai_client = genai.Client(
                    vertexai=True,
                    project=settings.GCP_PROJECT_ID,
                    location=settings.GCP_REGION
                )
                logger.info(
                    f"[Vertex AI] İstemci başarıyla başlatıldı (Project: {settings.GCP_PROJECT_ID}, Region: {settings.GCP_REGION})."
                )
                return _genai_client
            except Exception as e_vertex:
                logger.warning(f"[Vertex AI] Vertex modunda başlatma uyarısı: {e_vertex}. API Key fallback deneniyor...")

        # 2. Yedek: Gemini API Key
        if settings.GEMINI_API_KEY:
            _genai_client = genai.Client(api_key=settings.GEMINI_API_KEY)
            logger.info("[Vertex AI / GenAI] İstemci API Key ile başlatıldı.")
            return _genai_client

        # 3. Son Çare: Parametresiz (Ortam değişkenlerinden ADC veya GEMINI_API_KEY okur)
        _genai_client = genai.Client()
        return _genai_client

    except Exception as e:
        logger.error(f"[Vertex AI] GenAI Client oluşturulamadı: {e}")
        raise

def generate_embedding(text: str, model: str = None) -> List[float]:
    """
    Vertex AI text-embedding-005 ile 768 boyutlu semantik embedding üretir.
    gcp_architecture_report.md Bölüm 3 standardı.
    """
    client = get_genai_client()
    target_model = model or settings.EMBEDDING_MODEL
    try:
        response = client.models.embed_content(
            model=target_model,
            contents=text
        )
        if hasattr(response, "embeddings") and response.embeddings:
            return response.embeddings[0].values
        return []
    except Exception as e:
        logger.warning(f"[Vertex AI] Embedding üretme hatası ({e}). Fallback sıfır vektör dönülüyor.")
        return [0.0] * settings.VECTOR_DIM
