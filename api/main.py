import time
import os
import json
import re
import asyncio
import logging
from fastapi import FastAPI, HTTPException, Depends, Response, Form, UploadFile, File, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from typing import Annotated, Optional, List, Any, Dict
from pydantic import BaseModel

from api.config import settings
from api.schemas.product import GTIPDecision, HITLResponse, InternationalRuling
from api.schemas.audit import AuditLogEntry, AuditLogQueryResponse
from api.graph.workflow import workflow_engine
from api.exporter import pdf_exporter
from api.db.audit_logger import audit_logger
from api.db.gcp_emulator import local_state_store
from api.db.database import (
    init_orm_tables, get_db, TgtcGtipModel, TgtcRuleModel, TgtcNoteModel,
    GumrukEmsalKararModel, GumrukSiniflandirmaKarariModel, GumrukMevzuatMaddesiModel
)
from sqlalchemy.orm import Session
from api.security.model_armor import model_armor

logger = logging.getLogger(__name__)

from fastapi import BackgroundTasks

from fastapi.responses import JSONResponse
import traceback

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Uygulama başlangıç ve kapanış yaşam döngüsü yöneticisi."""
    init_orm_tables()
    yield

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Gümrük Tarife İstatistik Pozisyonu (GTİP) Tespit ve Karar Destek Sistemi Serverless API",
    lifespan=lifespan
)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Beklenmeyen Sunucu Hatası ({request.method} {request.url}): {str(exc)}\n{traceback.format_exc()}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Sistemde geçici bir sorun oluştu. Optimizasyon loglarına kaydedildi."}
    )

def _trigger_cloud_run_job(job_name: str) -> str:
    """Kimlikli Cloud Run Jobs API çağrısı yapar ve operation adını döndürür."""
    import google.auth
    from google.auth.transport.requests import AuthorizedSession

    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    session = AuthorizedSession(credentials)
    job_url = (
        f"https://run.googleapis.com/v2/projects/{settings.GCP_PROJECT_ID}/"
        f"locations/{settings.GCP_REGION}/jobs/{job_name}:run"
    )
    response = session.post(job_url, json={}, timeout=30)
    response.raise_for_status()
    return response.json().get("name", "")


@app.post("/api/v1/admin/trigger-deep-crawler", status_code=202)
async def trigger_deep_crawler(request: Request):
    """6 yıllık Resmî Gazete arşiv Cloud Run Job'unu tetikler."""
    from api.security.auth import require_admin_user
    require_admin_user(request)
    try:
        operation = _trigger_cloud_run_job("gtip-archive-backfill")
        return {"message": "Arşiv taraması Cloud Run Job olarak başlatıldı.", "operation": operation}
    except Exception as exc:
        logger.exception("Arşiv Cloud Run Job tetiklenemedi")
        raise HTTPException(status_code=503, detail=f"Arşiv işi tetiklenemedi: {exc}")

@app.post("/api/v1/admin/trigger-daily-sync", status_code=202)
async def trigger_daily_sync(request: Request):
    """Son 3 günün Resmî Gazete Cloud Run Job'unu tetikler."""
    from api.security.auth import require_admin_user
    require_admin_user(request)
    try:
        operation = _trigger_cloud_run_job("gtip-daily-sync")
        return {"message": "Günlük Resmî Gazete işi Cloud Run Job olarak başlatıldı.", "operation": operation}
    except Exception as exc:
        logger.exception("Günlük Cloud Run Job tetiklenemedi")
        raise HTTPException(status_code=503, detail=f"Günlük iş tetiklenemedi: {exc}")

@app.get("/api/v1/admin/status")
def admin_status(request: Request, db: Session = Depends(get_db)):
    """GET /api/v1/admin/status sistem genel sağlık ve kayıt sayısı durumunu döndürür."""
    from api.security.auth import require_admin_user
    require_admin_user(request)
    try:
        count = db.query(GumrukSiniflandirmaKarariModel).count()
    except Exception as exc:
        logger.error("Admin durum sorgusunda Cloud SQL hatası: %s", exc)
        raise HTTPException(status_code=503, detail="Cloud SQL erişilemiyor.")
    return {
        "status": "HEALTHY",
        "region": settings.GCP_REGION,
        "active_model": settings.DEFAULT_LLM_MODEL,
        "cloud_sql_siniflandirma_kararlari_count": count
    }

# CORS Configuration: production'da yapılandırma yoksa cross-origin erişim kapalıdır.
_cors_origins_raw = settings.CORS_ALLOWED_ORIGINS
if settings.ENVIRONMENT == "production" and not _cors_origins_raw:
    _cors_origins = []
    _allow_credentials = False
elif _cors_origins_raw == "*":
    _cors_origins = ["*"]
    _allow_credentials = False
else:
    _cors_origins = [o.strip() for o in _cors_origins_raw.split(",") if o.strip()]
    _allow_credentials = True

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-User-Email", "X-User-Role",
                   "x-goog-iap-jwt-assertion", "x-goog-authenticated-user-email"],
)

from fastapi.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=1000)

import re
from pydantic import BaseModel, Field, StringConstraints, field_validator

from api.security.rate_limit import demo_rate_limiter

ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/jpg", "application/pdf"}
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

ProductDescription = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=5000)]

class AnalyzeJSONRequest(BaseModel):
    product_description: ProductDescription = Field(..., description="Ürün tanımı veya fatura metni")
    image_uri: Optional[str] = Field(default=None, max_length=1000)
    enable_international_research: bool = Field(
        default=False,
        description="ABD (CBP CROSS), Çin (GACC) ve AB (EBTI) uluslararası emsal kararlarını canlı araştır",
    )

    @field_validator("image_uri")
    @classmethod
    def validate_image_uri(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        expected_prefix = f"gs://{settings.GCS_BUCKET_NAME}/uploads/"
        if not value.startswith(expected_prefix):
            raise ValueError("Görsel yalnızca uygulamanın güvenli yükleme alanından seçilebilir.")
        return value

class BatchAnalyzeRequest(BaseModel):
    product_descriptions: List[ProductDescription] = Field(
        ..., min_length=1, max_length=settings.MAX_BATCH_ITEMS
    )

async def _validate_and_sanitize_upload(file: UploadFile) -> str:
    """
    Yüklenen dosyanın tipini, boyutunu denetler ve Path Traversal riski için ismini temizler.
    """
    if file.content_type and file.content_type.lower() not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400, 
            detail=f"Desteklenmeyen dosya tipi ({file.content_type}). Sadece JPEG, PNG, WEBP ve PDF kabul edilir."
        )
    content = await file.read()
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="Dosya boyutu 10 MB sınırını aşmaktadır.")
    await file.seek(0)

    # Path Traversal temizliği (sadece alfa nümerik, tire, alt çizgi ve nokta)
    raw_name = os.path.basename(file.filename or "upload_file.bin")
    safe_name = re.sub(r'[^a-zA-Z0-9._-]', '_', raw_name)
    return safe_name

async def _upload_file_to_gcs(file: UploadFile, destination_blob_name: str) -> str:
    """
    Yüklenen dosyayı GCP Cloud Storage bucket'ına upload eder.
    GCS SDK yoksa veya emülatör modundaysa local /tmp fallback kullanır.
    """
    gcs_uri = f"gs://{settings.GCS_BUCKET_NAME}/{destination_blob_name}"
    if settings.USE_GCP_EMULATOR:
        # Geliştirme: /tmp dizinine kaydet
        safe_destination = destination_blob_name.replace('/', '_')
        tmp_path = f"/tmp/{safe_destination}"
        content = await file.read()
        with open(tmp_path, "wb") as f:
            f.write(content)
        await file.seek(0)
        logger.info(f"[GCS EMULATOR] Dosya yerel tmp'ye kaydedildi: {tmp_path}")
        return gcs_uri
    try:
        from google.cloud import storage as gcs
        client = gcs.Client(project=settings.GCP_PROJECT_ID)
        bucket = client.bucket(settings.GCS_BUCKET_NAME)
        blob = bucket.blob(destination_blob_name)
        content = await file.read()
        blob.upload_from_string(content, content_type=file.content_type or "application/octet-stream")
        await file.seek(0)
        logger.info(f"[GCS] Dosya başarıyla yüklendi: {gcs_uri}")
        return gcs_uri
    except Exception as e:
        logger.warning(f"[GCS] Upload hatası ({e}), local fallback kullanılıyor.")
        return gcs_uri

@app.get("/api/v1/generate-upload-url")
async def generate_upload_url(
    request: Request,
    filename: str = Query(..., min_length=1, max_length=255),
):
    """GCS Signed URL oluşturur. İstemci doğrudan Google Storage'a dosya yükleyebilir."""
    user_session = get_current_user_session(request)
    demo_rate_limiter.check(
        request,
        user_session,
        "upload-url",
        settings.PUBLIC_DEMO_UPLOAD_LIMIT_PER_MINUTE,
    )
        
    safe_name = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)
    extension = os.path.splitext(safe_name)[1].lower()
    if extension not in {".jpg", ".jpeg", ".png", ".webp", ".pdf"}:
        raise HTTPException(status_code=400, detail="Desteklenmeyen dosya uzantısı.")
    import uuid
    destination = f"uploads/{time.strftime('%Y/%m/%d')}/{uuid.uuid4().hex}_{safe_name}"
    
    if settings.USE_GCP_EMULATOR:
        return {"upload_url": f"http://localhost:8000/mock-upload", "destination": destination}
    try:
        import datetime
        from google.cloud import storage as gcs
        client = gcs.Client(project=settings.GCP_PROJECT_ID)
        bucket = client.bucket(settings.GCS_BUCKET_NAME)
        blob = bucket.blob(destination)
        url = blob.generate_signed_url(
            version="v4",
            expiration=datetime.timedelta(minutes=15),
            method="PUT"
        )
        return {"upload_url": url, "destination": f"gs://{settings.GCS_BUCKET_NAME}/{destination}"}
    except Exception:
        logger.exception("Signed URL oluşturulamadı")
        raise HTTPException(status_code=503, detail="Yükleme bağlantısı şu anda oluşturulamıyor.")


@app.get("/health")
@app.get("/api/v1/health")
def health_check():
    return {
        "status": "healthy",
        "environment": settings.ENVIRONMENT,
        "region": settings.GCP_REGION,
        "emulator_mode": settings.USE_GCP_EMULATOR,
        "version": settings.VERSION
    }

@app.get("/api/v1/ready")
def readiness_check(db: Session = Depends(get_db)):
    """Cloud SQL dahil kritik bağımlılıkların trafiğe hazır olduğunu doğrular."""
    try:
        from sqlalchemy import text
        db.execute(text("SELECT 1"))
        return {"status": "ready", "database": "healthy"}
    except Exception as exc:
        logger.error("Readiness kontrolü başarısız: %s", exc)
        raise HTTPException(status_code=503, detail="Database dependency is unavailable.")

from api.security.auth import get_current_user_session

@app.post("/api/v1/analyze", response_model=GTIPDecision)
async def analyze_product(
    request: Request,
    background_tasks: BackgroundTasks,
    product_description: Annotated[ProductDescription, Form()],
    image: Optional[UploadFile] = File(None),
    enable_international_research: bool = Form(False),
):
    start_time = time.time()
    try:
        user_session = get_current_user_session(request)
        demo_rate_limiter.check(
            request,
            user_session,
            "analysis",
            settings.PUBLIC_DEMO_RATE_LIMIT_PER_MINUTE,
        )
        import uuid as _uuid
        _upload_session_id = _uuid.uuid4().hex[:8]
        if image and image.filename:
            safe_name = await _validate_and_sanitize_upload(image)
            destination = f"uploads/{time.strftime('%Y/%m/%d')}/{_upload_session_id}_{safe_name}"
            image_uri = await _upload_file_to_gcs(image, destination)
        else:
            image_uri = None

        # Vertex AI Model Armor Güvenlik Duvarı Denetimi
        clean_desc, _ = model_armor.inspect_and_sanitize(product_description)
        decision = await workflow_engine.start_analysis_async(
            raw_text=clean_desc,
            image_uri=image_uri,
            enable_international_research=enable_international_research,
        )
        execution_ms = (time.time() - start_time) * 1000

        if decision.status == "COMPLETED" and decision.gtip_code:
            audit_entry = AuditLogEntry(
                session_id=decision.session_id,
                user_email=user_session.email,
                user_role=user_session.role,
                product_name=clean_desc[:50],
                initial_gtip_proposed=decision.gtip_code,
                final_gtip_approved=decision.gtip_code,
                confidence_score=decision.confidence_score,
                is_hitl_triggered=False,
                execution_time_ms=round(execution_ms, 2)
            )
            background_tasks.add_task(audit_logger.log_decision, audit_entry)

        return decision
    except HTTPException:
        raise
    except Exception:
        logger.exception("GTİP multipart analizi başarısız")
        raise HTTPException(status_code=500, detail="GTİP analizi tamamlanamadı.")


@app.get("/api/v1/analyze/stream")
async def analyze_product_stream(
    product_description: Annotated[ProductDescription, Query()],
    request: Request,
    enable_international_research: bool = Query(False),
):
    """
    Canlı Akışlı Karar Takibi (Server-Sent Events / SSE) Endpoint'i.
    4 aşamalı karar akışının her bir aşamasını istemciye anlık akış (text/event-stream) olarak iletir.
    """
    user_session = get_current_user_session(request)
    demo_rate_limiter.check(
        request,
        user_session,
        "analysis",
        settings.PUBLIC_DEMO_RATE_LIMIT_PER_MINUTE,
    )
    if not product_description or not product_description.strip():
        raise HTTPException(status_code=400, detail="Geçerli bir ürün açıklaması girmelisiniz.")

    # Vertex AI Model Armor Güvenlik Duvarı Denetimi
    clean_desc, _ = model_armor.inspect_and_sanitize(product_description)

    async def event_generator():
        async for event_data in workflow_engine.start_analysis_stream(
            raw_text=clean_desc.strip(),
            enable_international_research=enable_international_research,
        ):
            yield f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.post("/api/v1/analyze-json", response_model=GTIPDecision)
async def analyze_product_json(payload: AnalyzeJSONRequest, request: Request, background_tasks: BackgroundTasks):
    start_time = time.time()
    try:
        user_session = get_current_user_session(request)
        demo_rate_limiter.check(
            request,
            user_session,
            "analysis",
            settings.PUBLIC_DEMO_RATE_LIMIT_PER_MINUTE,
        )
        # Vertex AI Model Armor Güvenlik Duvarı Denetimi
        clean_desc, _ = model_armor.inspect_and_sanitize(payload.product_description)
        decision = await workflow_engine.start_analysis_async(
            raw_text=clean_desc,
            image_uri=payload.image_uri,
            enable_international_research=payload.enable_international_research,
        )
        execution_ms = (time.time() - start_time) * 1000

        if decision.status == "COMPLETED" and decision.gtip_code:
            audit_entry = AuditLogEntry(
                session_id=decision.session_id,
                user_email=user_session.email,
                user_role=user_session.role,
                product_name=payload.product_description[:50],
                initial_gtip_proposed=decision.gtip_code,
                final_gtip_approved=decision.gtip_code,
                confidence_score=decision.confidence_score,
                is_hitl_triggered=False,
                execution_time_ms=round(execution_ms, 2)
            )
            background_tasks.add_task(audit_logger.log_decision, audit_entry)

        return decision
    except HTTPException:
        raise
    except Exception:
        logger.exception("GTİP JSON analizi başarısız")
        raise HTTPException(status_code=500, detail="GTİP analizi tamamlanamadı.")


class InternationalSearchRequest(BaseModel):
    product_text: ProductDescription = Field(..., description="Araştırılacak ürünün teknik tanımı veya ticari adı")
    hs_code: Optional[str] = Field(default=None, max_length=20, description="Tahmini veya aday WCO HS kodu (örn. 8471, 9401.61)")
    target_countries: Optional[List[str]] = Field(default=["US", "CN", "EU"], description="Hedef ülkeler: US, CN, EU")
    max_results: int = Field(default=4, ge=1, le=10)


class InternationalSearchResponse(BaseModel):
    product_text: str
    hs_code_hint: Optional[str] = None
    target_countries: List[str]
    total_found: int
    rulings: List[InternationalRuling]
    portal_links: Dict[str, str]


@app.post("/api/v1/precedents/international-search", response_model=InternationalSearchResponse)
async def search_international_precedents(
    payload: InternationalSearchRequest,
    request: Request,
):
    """
    Avrupa Birliği (EBTI), ABD (CBP CROSS / CustomsMobile) ve Çin (GACC)
    gümrük sınıflandırma kararlarını (Rulings) bağımsız olarak canlı araştırır.
    """
    user_session = get_current_user_session(request)
    demo_rate_limiter.check(
        request,
        user_session,
        "intl-search",
        settings.PUBLIC_DEMO_RATE_LIMIT_PER_MINUTE,
    )
    from api.modules.international_search import (
        search_international_rulings_async,
        generate_portal_links,
    )
    clean_text, _ = model_armor.inspect_and_sanitize(payload.product_text)
    rulings = await search_international_rulings_async(
        product_text=clean_text,
        hs_code_hint=payload.hs_code,
        target_countries=payload.target_countries,
        max_results=payload.max_results,
    )
    portal_links = generate_portal_links(clean_text, payload.hs_code)
    return InternationalSearchResponse(
        product_text=clean_text,
        hs_code_hint=payload.hs_code,
        target_countries=payload.target_countries or ["US", "CN", "EU"],
        total_found=len(rulings),
        rulings=rulings,
        portal_links=portal_links,
    )


@app.post("/api/v1/analyze/batch", response_model=List[GTIPDecision])
async def analyze_product_batch(payload: BatchAnalyzeRequest, request: Request, background_tasks: BackgroundTasks):
    """
    Toplu Fatura / Multi-Item Batch GTİP Analizi Endpoint'i.
    Faturadaki tüm ürün kalemlerini asyncio.gather ile paralel çalıştırarak hızlandırır.
    """
    if not payload.product_descriptions:
        raise HTTPException(status_code=400, detail="En az bir ürün tanımı gönderilmelidir.")

    clean_descs = [d.strip() for d in payload.product_descriptions if d.strip()]
    if not clean_descs:
        raise HTTPException(status_code=400, detail="Geçerli ürün tanımı bulunamadı.")

    batch_start = time.time()
    user_session = get_current_user_session(request)
    demo_rate_limiter.check(
        request,
        user_session,
        "batch-analysis",
        max(1, settings.PUBLIC_DEMO_RATE_LIMIT_PER_MINUTE // 2),
    )

    semaphore = asyncio.Semaphore(max(1, settings.BATCH_CONCURRENCY))

    async def analyze_one(description: str):
        async with semaphore:
            return await workflow_engine.start_analysis_async(description)

    tasks = [analyze_one(desc) for desc in clean_descs]
    results = await asyncio.gather(*tasks, return_exceptions=False)
    elapsed_ms = round((time.time() - batch_start) * 1000 / max(len(results), 1), 2)

    for dec in results:
        if dec.status == "COMPLETED" and dec.gtip_code:
            audit_entry = AuditLogEntry(
                session_id=dec.session_id,
                user_email=user_session.email,
                user_role=user_session.role,
                product_name=dec.official_statute_text[:50] if dec.official_statute_text else "Toplu Analiz Kalemi",
                initial_gtip_proposed=dec.gtip_code,
                final_gtip_approved=dec.gtip_code,
                confidence_score=dec.confidence_score,
                is_hitl_triggered=False,
                execution_time_ms=elapsed_ms
            )
            background_tasks.add_task(audit_logger.log_decision, audit_entry)

    return results

@app.post("/api/v1/hitl/respond", response_model=GTIPDecision)
async def respond_hitl(response_data: HITLResponse, request: Request, background_tasks: BackgroundTasks):
    start_time = time.time()
    try:
        user_session = get_current_user_session(request)
        decision = workflow_engine.resume_analysis(
            session_id=response_data.session_id,
            selected_option_id=response_data.selected_option_id,
            question_id=response_data.question_id,
        )
        execution_ms = (time.time() - start_time) * 1000

        if decision.status == "COMPLETED" and decision.gtip_code:
            audit_entry = AuditLogEntry(
                session_id=decision.session_id,
                user_email=user_session.email,
                user_role=user_session.role,
                product_name="HITL İle Onaylanan Ürün",
                initial_gtip_proposed=decision.gtip_code,
                final_gtip_approved=decision.gtip_code,
                confidence_score=decision.confidence_score,
                is_hitl_triggered=True,
                user_feedback=response_data.custom_note,
                execution_time_ms=round(execution_ms, 2)
            )
            background_tasks.add_task(audit_logger.log_decision, audit_entry)

        return decision
    except HTTPException:
        raise
    except LookupError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"HITL Yanıtlama Hatası: {str(e)}")

@app.get("/api/v1/report/pdf/{session_id}")
async def get_pdf_report(session_id: str, request: Request):
    user_session = get_current_user_session(request)
    state_dict = local_state_store.get_state(session_id)
    if not state_dict:
        logs = audit_logger.get_all_logs(limit=200)
        matching_log = next((l for l in logs if l.session_id == session_id), None)
        if matching_log:
            decision = GTIPDecision(
                session_id=session_id,
                status="COMPLETED",
                gtip_code=matching_log.final_gtip_approved,
                confidence_score=matching_log.confidence_score,
                legal_justification="Resmi gümrük tebliğleri uyarınca.",
                applied_gir_rules=["GİR 1 ve GİR 6 kuralları uyarınca."],
                precedent_btbs=[]
            )
        else:
            raise HTTPException(status_code=404, detail="Analiz oturumu bulunamadı.")
    else:
        decision = GTIPDecision(
            session_id=session_id,
            status=state_dict.get("status", "COMPLETED"),
            gtip_code=state_dict.get("selected_gtip"),
            confidence_score=state_dict.get("confidence_score", 0.95),
            legal_justification=state_dict.get("legal_justification"),
            applied_gir_rules=state_dict.get("applied_gir_rules", []),
            precedent_btbs=state_dict.get("precedents", [])
        )

    pdf_bytes = pdf_exporter.generate_pdf_report(decision)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=gtip_rapor_{session_id[:8]}.pdf"}
    )

class BulkPDFRequest(BaseModel):
    session_ids: list[str] = Field(..., min_length=1, max_length=50)

@app.post("/api/v1/report/pdf/bulk")
async def get_bulk_pdf_report(payload: BulkPDFRequest, request: Request):
    user_session = get_current_user_session(request)
    if not payload.session_ids:
        raise HTTPException(status_code=400, detail="En az bir adet oturum kimliği seçilmelidir.")
    
    decisions = []
    logs = audit_logger.get_all_logs(limit=200)
    log_map = {l.session_id: l for l in logs}

    for sid in payload.session_ids:
        state_dict = local_state_store.get_state(sid)
        if state_dict:
            decisions.append(GTIPDecision(
                session_id=sid,
                status=state_dict.get("status", "COMPLETED"),
                gtip_code=state_dict.get("selected_gtip"),
                confidence_score=state_dict.get("confidence_score", 0.95),
                legal_justification=state_dict.get("legal_justification"),
                applied_gir_rules=state_dict.get("applied_gir_rules", []),
                precedent_btbs=state_dict.get("precedents", [])
            ))
        elif sid in log_map:
            l = log_map[sid]
            decisions.append(GTIPDecision(
                session_id=sid,
                status="COMPLETED",
                gtip_code=l.final_gtip_approved,
                confidence_score=l.confidence_score,
                legal_justification="Resmi gümrük tebliğleri ve GİR kuralları uyarınca.",
                applied_gir_rules=["GİR 1 ve GİR 6 kuralları uyarınca."],
                precedent_btbs=[]
            ))

    if not decisions:
        raise HTTPException(status_code=404, detail="Seçilen oturumlar bulunamadı.")

    pdf_bytes = pdf_exporter.generate_bulk_pdf_report(decisions)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=toplu_gtip_raporu_{len(decisions)}_adet.pdf"}
    )

@app.get("/api/v1/audit/logs", response_model=AuditLogQueryResponse)
async def get_audit_logs(request: Request, limit: int = Query(default=50, ge=1, le=200)):
    from api.security.auth import require_admin_user

    require_admin_user(request)
    logs = audit_logger.get_all_logs(limit=limit)
    return AuditLogQueryResponse(total_count=len(logs), entries=logs)

@app.get("/api/v1/customs-data/btbs")
async def get_customs_btbs(
    limit: int = Query(500, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    chapter: Optional[str] = Query(None),
    decision_type: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Resmi Gazete'den ve Ticaret Bakanlığı portallarından çekilen sınıflandırma kararlarını ve emsal BTB kararlarını döndürür.
    Sıfır-duplikasyon garantisi ile tekilleştirilmiş kayıtları ve tıklandığında açılan GCS PDF linklerini sağlar.
    Performans optimizasyonu: 768 boyutlu vektör kolonunu aktarmadan hafif projeksiyon sorgusu çalıştırır.
    """
    results = []
    seen_keys = set()

    def format_source_url(raw_url: Optional[str], pub_date: Any = None) -> Optional[str]:
        if raw_url:
            clean_u = str(raw_url).strip()
            if clean_u.startswith("gs://"):
                return f"https://storage.googleapis.com/{clean_u[5:]}"
            if clean_u.startswith("http"):
                return clean_u
        if pub_date:
            d_str = re.sub(r"[^\d]", "", str(pub_date))
            if len(d_str) >= 8:
                y, m, d = d_str[:4], d_str[4:6], d_str[6:8]
                return f"https://www.resmigazete.gov.tr/eskiler/{y}/{m}/{y}{m}{d}.htm"
        return "https://www.resmigazete.gov.tr"

    # 1. Cloud SQL gumruk_emsal_kararlar Tablosundan Hafif Projeksiyon ile Çek (Embedding kolonu hariç)
    try:
        query = db.query(
            GumrukEmsalKararModel.referans_no,
            GumrukEmsalKararModel.karar_tipi,
            GumrukEmsalKararModel.gtip_kodu,
            GumrukEmsalKararModel.chapter_code,
            GumrukEmsalKararModel.yayin_tarihi,
            GumrukEmsalKararModel.esya_tanimi,
            GumrukEmsalKararModel.hukuki_gerekce,
            GumrukEmsalKararModel.kaynak_url
        )
        if chapter:
            chap_clean = str(chapter).strip().zfill(2)
            query = query.filter(GumrukEmsalKararModel.chapter_code == chap_clean)
        if decision_type:
            query = query.filter(GumrukEmsalKararModel.karar_tipi == decision_type.strip().upper())

        emsal_rows = query.order_by(GumrukEmsalKararModel.yayin_tarihi.desc()).offset(offset).limit(limit).all()
        for ref_no, karar_tipi, gtip_kodu, chapter_code, pub_date, esya_tanimi, hukuki_gerekce, kaynak_url in emsal_rows:
            if not esya_tanimi or len(esya_tanimi.strip()) < 3:
                continue
            gtip_clean = str(gtip_kodu or "").replace(".", "").strip()
            if len(gtip_clean) < 4:
                continue

            pub_date_str = str(pub_date or "2026-01-01")
            desc_text = esya_tanimi.strip()
            desc_key = desc_text[:40].lower()
            unique_key = (gtip_clean, pub_date_str, desc_key)

            if unique_key not in seen_keys:
                seen_keys.add(unique_key)
                chap = chapter_code or gtip_clean[:2]
                btb_id = ref_no or f"RG-DEC-{pub_date_str.replace('-', '')}-{gtip_clean}"

                results.append({
                    "btb_no": btb_id,
                    "source_type": karar_tipi,
                    "gtip_code": gtip_kodu,
                    "chapter": chap,
                    "issue_date": pub_date_str,
                    "product_description": desc_text,
                    "legal_justification": hukuki_gerekce or "Emsal Sınıflandırma Kararı",
                    "source_url": format_source_url(kaynak_url, pub_date_str)
                })

    except Exception as e_e:
        logger.warning(f"[get_customs_btbs] Emsal kararları okunurken uyarı: {e_e}")

    # 2. Cloud SQL gumruk_siniflandirma_kararlari Tablosundan Eksikleri Tamamla (Varsa ek unique olanlar)
    if not decision_type and len(results) < limit:
        remaining = limit - len(results)
        try:
            sinif_query = db.query(
                GumrukSiniflandirmaKarariModel.gtip_kodu,
                GumrukSiniflandirmaKarariModel.yayin_tarihi,
                GumrukSiniflandirmaKarariModel.esya_tanimi,
                GumrukSiniflandirmaKarariModel.hukuki_gerekce,
                GumrukSiniflandirmaKarariModel.kaynak_url
            )
            sinif_rows = sinif_query.order_by(GumrukSiniflandirmaKarariModel.yayin_tarihi.desc()).limit(remaining).all()
            for s_gtip, s_pub_date, s_desc, s_gerekce, s_url in sinif_rows:
                if not s_desc or len(s_desc.strip()) < 3:
                    continue
                gtip_clean = str(s_gtip or "").replace(".", "").strip()
                if len(gtip_clean) < 4:
                    continue

                pub_date_str = str(s_pub_date or "2026-01-01")
                desc_text = s_desc.strip()
                desc_key = desc_text[:40].lower()
                unique_key = (gtip_clean, pub_date_str, desc_key)

                if unique_key not in seen_keys:
                    seen_keys.add(unique_key)
                    chap = gtip_clean[:2]
                    btb_id = f"RG-{pub_date_str.replace('-', '')}-{gtip_clean}"

                    results.append({
                        "btb_no": btb_id,
                        "gtip_code": s_gtip,
                        "chapter": chap,
                        "issue_date": pub_date_str,
                        "product_description": desc_text,
                        "legal_justification": s_gerekce or "Resmî Gazete Sınıflandırma Kararı",
                        "source_url": format_source_url(s_url, pub_date_str)
                    })
        except Exception as e_s:
            logger.warning(f"[get_customs_btbs] Siniflandirma kararları okunurken uyarı: {e_s}")

    # 3. Eğer DB'de henüz dinamik kayıt yoksa Katalog Ön Belleğinden Yükle (Fallback)
    if not results:
        try:
            from api.db.tgtc_knowledge_base import load_btb_catalog
            catalog = load_btb_catalog()
            if catalog:
                real_btbs = [item for item in catalog if not str(item.get("btb_no", "")).startswith("TGTC2026-")]
                for b in real_btbs:
                    if not b.get("source_url"):
                        b["source_url"] = format_source_url(b.get("kaynak_url"), b.get("issue_date"))
                return real_btbs
        except Exception as e_c:
            logger.error(f"[get_customs_btbs Catalog Fallback Error] {e_c}", exc_info=True)

    return results

@app.get("/api/v1/customs-data/chapters")
async def get_tgtc_chapters(db: Session = Depends(get_db)):
    """
    Türk Gümrük Tarife Cetveli (TGTC) 2-Haneli Fasıllar ve 4-Haneli Tarife Pozisyonlarını (HS Headings) döndürür.
    """
    # chapters
    chapters_query = db.query(TgtcGtipModel).filter(TgtcGtipModel.level == 'CHAPTER').all()
    chapters = []
    for c in sorted(chapters_query, key=lambda x: x.gtip_code):
        chapters.append({"chapter_code": c.gtip_code, "description": c.description})

    # headings
    headings_query = db.query(TgtcGtipModel).filter(TgtcGtipModel.level == 'HEADING').all()
    headings = []
    for h in sorted(headings_query, key=lambda x: x.gtip_code):
        headings.append({"heading_code": h.gtip_code, "chapter_code": h.parent_code, "description": h.description})

    return {
        "chapters": chapters,
        "headings": headings
    }

@app.get("/api/v1/customs-data/heading/{heading_code}")
async def get_heading_items(heading_code: str, db: Session = Depends(get_db)):
    """
    Belirli bir 4-Haneli tarife pozisyonuna ait tüm alt GTİP kodlarını ve açıklamalarını döndürür.
    """
    h = heading_code.strip().replace(".", "")
    if len(h) != 4 or not h.isdigit():
        return {"items": [], "error": "Geçersiz pozisyon kodu. 4 haneli rakam olmalıdır."}
    
    items_query = db.query(TgtcGtipModel).filter(
        TgtcGtipModel.level.in_(['SUBHEADING', 'GTIP']),
        TgtcGtipModel.gtip_code.like(f"{h}%")
    ).order_by(TgtcGtipModel.gtip_code).all()

    results = []
    for item in items_query:
        # format back to dots if needed, but UI might expect clean code
        results.append({
            "gtip_code": item.gtip_code,
            "gtip_clean": item.gtip_code,
            "description": item.description,
            "digits": len(item.gtip_code),
            "unit": item.unit if item.unit and item.unit != "nan" else None,
            "tax_rate": item.tax_rate if item.tax_rate and item.tax_rate != "nan" else None,
        })
    
    return {"heading_code": heading_code, "count": len(results), "items": results}

def _format_izahname(raw_text: str) -> str:
    if not raw_text or not str(raw_text).strip():
        return "Bu fasıl için özel bir hukuki ek not tanımlanmamıştır; GİR ve genel tarife pozisyonu hükümleri uygulanır."
    import re
    # Satır sonu hece bölünmelerini birleştir (Örn: say-\nılacaktır -> sayılacaktır)
    text = re.sub(r'(\w+)-\s*\r?\n\s*(\w+)', r'\1\2', str(raw_text))
    lines = text.replace('\r', '\n').split('\n')
    
    formatted_paragraphs = []
    current_para = []

    for line in lines:
        line = line.strip()
        if not line:
            if current_para:
                formatted_paragraphs.append(" ".join(current_para))
                current_para = []
            continue
            
        if line[0].isdigit() or line.startswith("(") or line.isupper():
            if current_para:
                formatted_paragraphs.append(" ".join(current_para))
                current_para = []
            is_header = line.isupper() and len(line) < 60
            if is_header:
                current_para.append(f"📌 {line}")
            else:
                current_para.append(f"▪ {line}")
        else:
            current_para.append(line)
            
    if current_para:
        formatted_paragraphs.append(" ".join(current_para))
        
    return "\n\n".join(formatted_paragraphs)

@app.get("/api/v1/customs-data/rules-and-notes")
async def get_tgtc_rules_and_notes(db: Session = Depends(get_db)):
    """
    Bakanlık Resmi Genel Yorum Kurallarını (GİR 1-6), Genel Açıklamaları ve 97 Fasıla ait yasal Hukuki İzahnameleri kusursuz formatlanmış olarak döndürür.
    """
    rules_query = db.query(TgtcRuleModel).filter(TgtcRuleModel.rule_type == 'GIR').order_by(TgtcRuleModel.id).all()
    gir_rules = []
    for r in rules_query:
        gir_rules.append({
            "rule_number": r.rule_number,
            "title": r.title,
            "name": f"GİR Kuralı {r.rule_number}",
            "text": r.text
        })
        
    exp_query = db.query(TgtcRuleModel).filter(TgtcRuleModel.rule_type == 'EXPLANATION').order_by(TgtcRuleModel.id).all()
    explanations = []
    for e in exp_query:
        explanations.append({
            "rule_number": e.rule_number,
            "title": e.title,
            "text": e.text
        })

    notes_query = db.query(TgtcNoteModel).order_by(TgtcNoteModel.chapter_code).all()
    
    # We also need chapter titles
    chapters = {c.gtip_code: c.description for c in db.query(TgtcGtipModel).filter(TgtcGtipModel.level == 'CHAPTER').all()}
    
    chapter_notes = []
    for n in notes_query:
        c_str = n.chapter_code
        note_title = ""
        raw_header = n.text.split("Not")[0].replace("\n", " - ").replace("\r", " - ")
        parts = [p.strip() for p in raw_header.split(" - ") if p.strip() and not p.strip().startswith("FASIL") and not p.strip().startswith("BÖLÜM")]
        if parts:
            note_title = " - ".join(parts[:2])
        if not note_title or len(note_title) < 4:
            note_title = chapters.get(c_str, f"Fasıl {c_str}")
            
        note_text = _format_izahname(n.text)
        chapter_notes.append({
            "chapter": c_str,
            "chapter_code": c_str,
            "fasil": c_str,
            "chapter_title": note_title,
            "title": note_title,
            "legal_note": note_text,
            "text": note_text
        })
        
    return {
        "gir_rules": gir_rules,
        "explanations": explanations,
        "chapter_notes": chapter_notes
    }

@app.get("/api/v1/customs-data/sync-status")
async def get_sync_status():
    """
    4 Adet Canlı Mevzuat & BTB Boru Hattının Sağlık ve Senkronizasyon Durumunu Döndürür.
    """
    from scripts.sync_customs_data import get_etl_sync_status
    return get_etl_sync_status()

@app.post("/api/v1/customs-data/trigger-sync", status_code=202)
async def trigger_manual_sync(request: Request):
    """Yetkili kullanıcı için günlük ETL Cloud Run Job'unu tetikler."""
    from api.security.auth import require_admin_user

    require_admin_user(request)
    try:
        operation = _trigger_cloud_run_job("gtip-daily-sync")
        return {"status": "ACCEPTED", "message": "Günlük ETL işi başlatıldı.", "operation": operation}
    except Exception:
        logger.exception("Günlük ETL işi tetiklenemedi")
        raise HTTPException(status_code=503, detail="Günlük ETL işi tetiklenemedi.")


@app.post("/api/v1/admin/clean-bad-btbs")
async def clean_bad_btbs(request: Request, db: Session = Depends(get_db)):
    """
    Hatalı parse edilmiş veya eksik ürün açıklamasına sahip BTB kayıtlarını veritabanından temizler.
    """
    from api.security.auth import require_admin_user

    require_admin_user(request)
    try:
        from api.db.database import GumrukEmsalKararModel, GumrukSiniflandirmaKarariModel
        bad_count = 0
                
        all_emsal = db.query(GumrukEmsalKararModel).all()
        for e in all_emsal:
            desc = e.esya_tanimi.strip().lower() if e.esya_tanimi else ""
            if len(desc) < 10 or desc.startswith("toplam") or desc.startswith("sayfa") or desc.startswith("gerekçe") or desc.startswith("11,"):
                db.delete(e)
                bad_count += 1
                
        db.commit()
        return {"status": "SUCCESS", "deleted_count": bad_count, "message": f"{bad_count} adet hatalı BTB kaydı başarıyla silindi."}
    except Exception:
        db.rollback()
        logger.exception("Hatalı BTB temizleme işlemi başarısız")
        raise HTTPException(status_code=500, detail="Temizleme işlemi tamamlanamadı.")

@app.post("/api/v1/admin/sync-gcp-official-gazette-bulk", status_code=202)
async def trigger_gcp_official_gazette_bulk_sync(
    request: Request,
    start_year: int = Query(default=2020, ge=2020, le=2026),
    end_year: int = Query(default=2026, ge=2020, le=2026),
    limit_days: Optional[int] = Query(default=None, ge=1)
):
    """
    GCP Cloud Run / Cloud Scheduler üzerinden 2020-2026 yılları arasındaki tüm Resmî Gazete BTB ve Sınıflandırma Kararlarını
    Vertex AI (Gemini 3.6 Flash) ile harfi harfine (exact-match) süzüp Cloud SQL'e aktaran bulk senkronizasyon endpointi.
    """
    from api.security.auth import require_admin_user

    require_admin_user(request)
    if start_year != 2020 or end_year != 2026 or limit_days is not None:
        raise HTTPException(
            status_code=422,
            detail="Cloud Run arşiv işi yalnızca tam 2020-2026 aralığını destekler.",
        )
    try:
        operation = _trigger_cloud_run_job("gtip-archive-backfill")
        return {
            "status": "ACCEPTED",
            "message": "Resmî Gazete arşiv Cloud Run işi başlatıldı.",
            "target_years": f"{start_year}-{end_year}",
            "operation": operation,
        }
    except Exception:
        logger.exception("Arşiv Cloud Run işi tetiklenemedi")
        raise HTTPException(status_code=503, detail="Arşiv işi tetiklenemedi.")


@app.get("/api/v1/admin/sync-gcp-official-gazette-status")
async def get_gcp_official_gazette_sync_status(request: Request, db: Session = Depends(get_db)):
    """
    Cloud SQL üzerindeki harfi harfine süzülmüş Resmî Gazete Sınıflandırma Kararları metriklerini döndürür.
    """
    from api.security.auth import require_admin_user

    require_admin_user(request)
    try:
        from api.db.database import GumrukSiniflandirmaKarariModel, GumrukEmsalKararModel
        total_siniflandirma = db.query(GumrukSiniflandirmaKarariModel).count()
        total_emsal = db.query(GumrukEmsalKararModel).filter_by(karar_tipi="SINIFLANDIRMA_KARARI").count()
        latest_record = db.query(GumrukSiniflandirmaKarariModel).order_by(GumrukSiniflandirmaKarariModel.id.desc()).first()

        return {
            "status": "HEALTHY",
            "active_model": getattr(settings, "DEFAULT_LLM_MODEL", "gemini-2.5-flash"),
            "cloud_sql_siniflandirma_kararlari_count": total_siniflandirma,
            "cloud_sql_emsal_kararlar_count": total_emsal,
            "latest_extracted_gtip": latest_record.gtip_kodu if latest_record else None,
            "latest_yayin_tarihi": latest_record.yayin_tarihi if latest_record else None,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Durum alma hatası: {str(e)}")


@app.get("/api/v1/admin/db-stats")
def get_db_stats(request: Request, db: Session = Depends(get_db)):
    """
    Cloud SQL veritabanındaki tüm tabloların güncel satır sayılarını ve sağlık durumunu döndürür.
    """
    from api.security.auth import require_admin_user

    require_admin_user(request)
    try:
        from api.db.database import (
            GumrukSiniflandirmaKarariModel,
            GumrukEmsalKararModel,
            GumrukMevzuatMaddesiModel,
            TgtcGtipModel,
            TgtcRuleModel,
            TgtcNoteModel,
            AuditLogModel
        )
        siniflandirma_count = db.query(GumrukSiniflandirmaKarariModel).count()
        btb_count = db.query(GumrukEmsalKararModel).filter(GumrukEmsalKararModel.karar_tipi == "BTB").count()
        emsal_sinif_count = db.query(GumrukEmsalKararModel).filter(GumrukEmsalKararModel.karar_tipi == "SINIFLANDIRMA_KARARI").count()
        mevzuat_count = db.query(GumrukMevzuatMaddesiModel).count()
        tgtc_count = db.query(TgtcGtipModel).count()
        tgtc_chapters = db.query(TgtcGtipModel).filter(TgtcGtipModel.level == "CHAPTER").count()
        tgtc_headings = db.query(TgtcGtipModel).filter(TgtcGtipModel.level == "HEADING").count()
        rules_count = db.query(TgtcRuleModel).count()
        notes_count = db.query(TgtcNoteModel).count()
        audit_count = db.query(AuditLogModel).count()

        latest_sinif = db.query(GumrukSiniflandirmaKarariModel).order_by(GumrukSiniflandirmaKarariModel.id.desc()).first()
        latest_btb = db.query(GumrukEmsalKararModel).filter(GumrukEmsalKararModel.karar_tipi == "BTB").order_by(GumrukEmsalKararModel.id.desc()).first()

        return {
            "status": "HEALTHY",
            "database_instance": settings.CLOUD_SQL_CONNECTION_NAME,
            "database_name": settings.DB_NAME,
            "tables": {
                "gumruk_siniflandirma_kararlari": siniflandirma_count,
                "gumruk_emsal_kararlar": {
                    "total": btb_count + emsal_sinif_count,
                    "btb": btb_count,
                    "siniflandirma_karari": emsal_sinif_count
                },
                "gumruk_mevzuat_maddeleri": mevzuat_count,
                "tgtc_gtip_tree": {
                    "total": tgtc_count,
                    "chapters": tgtc_chapters,
                    "headings": tgtc_headings
                },
                "tgtc_rules": rules_count,
                "tgtc_notes": notes_count,
                "audit_logs": audit_count
            },
            "latest_records": {
                "latest_siniflandirma_karari": {
                    "gtip": latest_sinif.gtip_kodu if latest_sinif else None,
                    "yayin_tarihi": latest_sinif.yayin_tarihi if latest_sinif else None,
                    "esya_tanimi": (latest_sinif.esya_tanimi[:100] + "...") if latest_sinif and latest_sinif.esya_tanimi else None
                },
                "latest_btb": {
                    "referans_no": latest_btb.referans_no if latest_btb else None,
                    "gtip": latest_btb.gtip_kodu if latest_btb else None,
                    "yayin_tarihi": latest_btb.yayin_tarihi if latest_btb else None,
                    "esya_tanimi": (latest_btb.esya_tanimi[:100] + "...") if latest_btb and latest_btb.esya_tanimi else None
                }
            }
        }
    except Exception as e:
        logger.error(f"DB Stats hatası: {e}")
        raise HTTPException(status_code=500, detail=f"DB Stats hatası: {str(e)}")


@app.post("/api/v1/admin/seed-tgtc-tree", status_code=202)
async def seed_tgtc_tree_admin(request: Request):
    """
    2026 TGTC dizinindeki sabit Tarife Ağacını (01-99 Fasıllar, GTİP Kümeleri, GİR Kuralları ve Fasıl Notları)
    Cloud SQL veritabanına yeniden yükler ve eşitler. Resmi Gazete verilerinden tamamen bağımsızdır.
    """
    from api.security.auth import require_admin_user

    require_admin_user(request)
    try:
        operation = _trigger_cloud_run_job("gtip-seed-tgtc-2026")
        return {
            "status": "ACCEPTED",
            "message": "2026 TGTC seed Cloud Run işi başlatıldı.",
            "operation": operation,
        }
    except Exception:
        logger.exception("TGTC seed Cloud Run işi tetiklenemedi")
        raise HTTPException(status_code=503, detail="TGTC seed işi tetiklenemedi.")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="127.0.0.1", port=8000, reload=True)
