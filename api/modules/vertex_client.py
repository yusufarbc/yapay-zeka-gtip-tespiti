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
                    location=settings.VERTEX_AI_LOCATION,
                    http_options={"timeout": settings.LLM_TIMEOUT_MS},
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

_grounded_client = None


def get_grounded_search_client():
    """
    Google Search Grounding çağrıları için ayrı, uzun timeout'lu istemci.

    Varsayılan istemci `LLM_TIMEOUT_MS` (15s) ile kurulur; grounding'li arama bu
    bütçeye sığmadığı için üretimde sürekli 504 DEADLINE_EXCEEDED üretiyordu.
    """
    global _grounded_client
    if _grounded_client is not None:
        return _grounded_client

    from google import genai

    timeout = settings.GROUNDED_SEARCH_TIMEOUT_MS
    if not settings.USE_GCP_EMULATOR:
        try:
            _grounded_client = genai.Client(
                vertexai=True,
                project=settings.GCP_PROJECT_ID,
                location=settings.VERTEX_AI_LOCATION,
                http_options={"timeout": timeout},
            )
            return _grounded_client
        except Exception as exc:
            logger.warning(f"[Vertex AI] Grounded istemci Vertex modunda kurulamadı: {exc}")

    if settings.GEMINI_API_KEY:
        _grounded_client = genai.Client(
            api_key=settings.GEMINI_API_KEY,
            http_options={"timeout": timeout},
        )
        return _grounded_client

    _grounded_client = genai.Client(http_options={"timeout": timeout})
    return _grounded_client


def generate_embedding(text: str, model: str = None) -> List[float]:
    """
    Vertex AI text-embedding-005 ile 768 boyutlu semantik embedding üretir.
    gcp_architecture_report.md Bölüm 3 standardı.
    """
    target_model = model or settings.EMBEDDING_MODEL
    try:
        # text-embedding-005 uses a regional endpoint, independent of Gemini global.
        from google import genai
        client = genai.Client(
            vertexai=True,
            project=settings.GCP_PROJECT_ID,
            location=settings.GCP_REGION,
            http_options={"timeout": settings.EMBEDDING_TIMEOUT_MS},
        )
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


def generation_config(model: str, *, reasoning: bool = False, **kwargs):
    """Use Gemini 3 thinking levels; retain budget compatibility for older overrides."""
    from google.genai import types
    thinking = (types.ThinkingConfig(thinking_level="HIGH" if reasoning else "LOW")
                if model.startswith("gemini-3") else
                types.ThinkingConfig(thinking_budget=settings.THINKING_BUDGET_VERIFIER
                                     if reasoning else settings.THINKING_BUDGET_EXTRACTOR))
    return types.GenerateContentConfig(thinking_config=thinking, **kwargs)
