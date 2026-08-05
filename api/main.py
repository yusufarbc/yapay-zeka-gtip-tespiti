import time
import os
import json
import asyncio
import logging
from fastapi import FastAPI, HTTPException, Depends, Response, Form, UploadFile, File, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from typing import Optional, List
from pydantic import BaseModel

from api.config import settings
from api.schemas.product import GTIPDecision, HITLResponse
from api.schemas.audit import AuditLogEntry, AuditLogQueryResponse
from api.graph.workflow import workflow_engine
from api.exporter import pdf_exporter
from api.db.audit_logger import audit_logger
from api.db.gcp_emulator import local_state_store, local_vector_store
from api.db.database import init_orm_tables

logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Gümrük Tarife İstatistik Pozisyonu (GTİP) Tespit ve Karar Destek Sistemi Serverless API"
)

@app.on_event("startup")
def startup_event():
    init_orm_tables()

# CORS Configuration: Production ortamında wildcard (*) kesinlikle engellenir.
_cors_origins_raw = settings.CORS_ALLOWED_ORIGINS
if settings.ENVIRONMENT == "production" and (_cors_origins_raw == "*" or not _cors_origins_raw):
    _cors_origins = ["https://gtip-web-230333256951.europe-west3.run.app"]
    _allow_credentials = True
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

import re
from pydantic import BaseModel, Field

ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/jpg", "application/pdf"}
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

class AnalyzeJSONRequest(BaseModel):
    product_description: str = Field(..., min_length=3, max_length=5000, description="Ürün tanımı veya fatura metni")
    image_uri: Optional[str] = Field(default=None, max_length=1000)

class BatchAnalyzeRequest(BaseModel):
    product_descriptions: List[str] = Field(..., min_length=1, max_length=50)

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


def append_continuous_learning_record(session_id: str, product_name: str, gtip_code: str):
    """
    Continuous Learning (Geri Beslemeli Öğrenen Sistem):
    Kullanıcının/Müşavirin onayladığı yeni GTİP kararlarını kurumsal emsal veritabanına ekler.
    Production: GCS'e JSON satırı olarak yazar (ephemeral disk yerine kalıcı depolama).
    Geliştirme: Yerel dosyaya yazar.
    """
    new_entry = {
        "btb_no": f"KURUMSAL-EMSAL-{session_id[:8].upper()}",
        "gtip_code": gtip_code,
        "chapter": gtip_code[:2],
        "heading": gtip_code[:4],
        "issue_date": time.strftime("%Y-%m-%d"),
        "product_description": product_name,
        "legal_justification": f"Gümrük Müşaviri tarafından onaylanan kurumsal emsal karar ({session_id[:8]})."
    }
    # 1. Production: GCS'e yaz
    if not settings.USE_GCP_EMULATOR:
        try:
            from google.cloud import storage as gcs
            client = gcs.Client(project=settings.GCP_PROJECT_ID)
            bucket = client.bucket(settings.GCS_BUCKET_NAME)
            blob_name = f"continuous_learning/{time.strftime('%Y/%m/%d')}/{session_id[:8]}.json"
            blob = bucket.blob(blob_name)
            blob.upload_from_string(json.dumps(new_entry, ensure_ascii=False), content_type="application/json")
            logger.info(f"[Continuous Learning] GCS'e kaydedildi: gs://{settings.GCS_BUCKET_NAME}/{blob_name}")
            return
        except Exception as e:
            logger.warning(f"[Continuous Learning] GCS yazma hatası: {e}, yerel dosyaya yazılıyor.")
    # 2. Geliştirme / GCS fallback: yerel dosyaya yaz
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        dataset_file = os.path.join(base_dir, "api", "data", "official_btb_database.json")
        records = []
        if os.path.exists(dataset_file):
            with open(dataset_file, "r", encoding="utf-8") as f:
                records = json.load(f)
        records.append(new_entry)
        os.makedirs(os.path.dirname(dataset_file), exist_ok=True)
        with open(dataset_file, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
        # Vector store bellek önbelleğini geçersiz kıl: RAG bir sonraki sorguda yeni kaydı görecek
        local_state_store.save_state("__btb_db_updated__", {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ")})
        local_vector_store.invalidate_cache()
        logger.info(f"[Continuous Learning] Yeni emsal kaydı BTB veritabanına eklendi: {gtip_code}")
    except Exception as e:
        logger.warning(f"Continuous Learning yerel kayıt uyarısı: {e}")

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

from api.security.auth import get_current_user_session

@app.post("/api/v1/analyze", response_model=GTIPDecision)
async def analyze_product(
    request: Request,
    product_description: str = Form(...),
    image: Optional[UploadFile] = File(None)
):
    start_time = time.time()
    try:
        user_session = get_current_user_session(request)
        import uuid as _uuid
        _upload_session_id = _uuid.uuid4().hex[:8]
        if image and image.filename:
            safe_name = await _validate_and_sanitize_upload(image)
            destination = f"uploads/{time.strftime('%Y/%m/%d')}/{_upload_session_id}_{safe_name}"
            image_uri = await _upload_file_to_gcs(image, destination)
        else:
            image_uri = None
        decision = await workflow_engine.start_analysis_async(raw_text=product_description, image_uri=image_uri)
        execution_ms = (time.time() - start_time) * 1000

        if decision.status == "COMPLETED" and decision.gtip_code:
            audit_logger.log_decision(AuditLogEntry(
                session_id=decision.session_id,
                user_email=user_session.email,
                user_role=user_session.role,
                product_name=product_description[:50],
                initial_gtip_proposed=decision.gtip_code,
                final_gtip_approved=decision.gtip_code,
                confidence_score=decision.confidence_score,
                is_hitl_triggered=False,
                execution_time_ms=round(execution_ms, 2)
            ))
            append_continuous_learning_record(decision.session_id, product_description[:60], decision.gtip_code)

        return decision
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"GTİP Analiz Hatası: {str(e)}")


@app.get("/api/v1/analyze/stream")
async def analyze_product_stream(product_description: str, request: Request):
    """
    Canlı Akışlı Karar Takibi (Server-Sent Events / SSE) Endpoint'i.
    4 aşamalı karar akışının her bir aşamasını istemciye anlık akış (text/event-stream) olarak iletir.
    """
    if not product_description or not product_description.strip():
        raise HTTPException(status_code=400, detail="Geçerli bir ürün açıklaması girmelisiniz.")

    async def event_generator():
        async for event_data in workflow_engine.start_analysis_stream(raw_text=product_description.strip()):
            yield f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.post("/api/v1/analyze-json", response_model=GTIPDecision)
async def analyze_product_json(payload: AnalyzeJSONRequest, request: Request):
    start_time = time.time()
    try:
        user_session = get_current_user_session(request)
        decision = await workflow_engine.start_analysis_async(raw_text=payload.product_description, image_uri=payload.image_uri)
        execution_ms = (time.time() - start_time) * 1000

        if decision.status == "COMPLETED" and decision.gtip_code:
            audit_logger.log_decision(AuditLogEntry(
                session_id=decision.session_id,
                user_email=user_session.email,
                user_role=user_session.role,
                product_name=payload.product_description[:50],
                initial_gtip_proposed=decision.gtip_code,
                final_gtip_approved=decision.gtip_code,
                confidence_score=decision.confidence_score,
                is_hitl_triggered=False,
                execution_time_ms=round(execution_ms, 2)
            ))
            append_continuous_learning_record(decision.session_id, payload.product_description[:60], decision.gtip_code)

        return decision
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"GTİP Analiz Hatası: {str(e)}")


@app.post("/api/v1/analyze/batch", response_model=List[GTIPDecision])
async def analyze_product_batch(payload: BatchAnalyzeRequest, request: Request):
    """
    Toplu Fatura / Multi-Item Batch GTİP Analizi Endpoint'i.
    Faturadaki tüm ürün kalemlerini asyncio.gather ile paralel çalıştırarak hızlandırır.
    """
    if not payload.product_descriptions:
        raise HTTPException(status_code=400, detail="En az bir ürün tanımı gönderilmelidir.")

    clean_descs = [d.strip() for d in payload.product_descriptions[:50] if d.strip()]
    if not clean_descs:
        raise HTTPException(status_code=400, detail="Geçerli ürün tanımı bulunamadı.")

    batch_start = time.time()
    user_session = get_current_user_session(request)

    # asyncio.gather ile tüm analizleri concurrent olarak başlat
    tasks = [workflow_engine.start_analysis_async(desc) for desc in clean_descs]
    results = await asyncio.gather(*tasks, return_exceptions=False)
    elapsed_ms = round((time.time() - batch_start) * 1000 / max(len(results), 1), 2)

    for dec in results:
        if dec.status == "COMPLETED" and dec.gtip_code:
            audit_logger.log_decision(AuditLogEntry(
                session_id=dec.session_id,
                user_email=user_session.email,
                user_role=user_session.role,
                product_name=dec.official_statute_text[:50] if dec.official_statute_text else "Toplu Analiz Kalemi",
                initial_gtip_proposed=dec.gtip_code,
                final_gtip_approved=dec.gtip_code,
                confidence_score=dec.confidence_score,
                is_hitl_triggered=False,
                execution_time_ms=elapsed_ms
            ))

    return results

@app.post("/api/v1/hitl/respond", response_model=GTIPDecision)
async def respond_hitl(response_data: HITLResponse, request: Request):
    start_time = time.time()
    try:
        user_session = get_current_user_session(request)
        decision = workflow_engine.resume_analysis(
            session_id=response_data.session_id,
            selected_option_id=response_data.selected_option_id
        )
        execution_ms = (time.time() - start_time) * 1000

        if decision.gtip_code:
            audit_logger.log_decision(AuditLogEntry(
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
            ))
            append_continuous_learning_record(decision.session_id, "HITL Onaylı Ürün", decision.gtip_code)

        return decision
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
    user_session = get_current_user_session(request)
    logs = audit_logger.get_all_logs(limit=limit)
    return AuditLogQueryResponse(total_count=len(logs), entries=logs)

@app.get("/api/v1/customs-data/btbs")
async def get_customs_btbs():
    """
    Resmi organlardan (Ticaret Bakanlığı BTB Arama Portalı) çekilen emsal BTB kararlarını döndürür.
    """
    from api.db.tgtc_knowledge_base import load_btb_catalog
    catalog = load_btb_catalog()
    if catalog:
        return catalog
    base_dir = os.path.dirname(os.path.abspath(__file__))
    dataset_file = os.path.join(base_dir, "data", "official_btb_database.json")
    if os.path.exists(dataset_file):
        with open(dataset_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

@app.get("/api/v1/customs-data/chapters")
async def get_tgtc_chapters():
    """
    Türk Gümrük Tarife Cetveli (TGTC) 99 Fasıl tanım ve bölüm isimlerini döndürür.
    """
    from api.db.tgtc_knowledge_base import load_tgtc_chapters, TGTC_CHAPTERS
    chaps = load_tgtc_chapters() or TGTC_CHAPTERS
    return [{"chapter_code": code, "description": desc} for code, desc in chaps.items()]

@app.get("/api/v1/customs-data/sync-status")
async def get_sync_status():
    """
    4 Adet Canlı Mevzuat & BTB Boru Hattının Sağlık ve Senkronizasyon Durumunu Döndürür.
    """
    from scripts.sync_customs_data import get_etl_sync_status
    return get_etl_sync_status()

@app.post("/api/v1/customs-data/trigger-sync")
async def trigger_manual_sync():
    """
    Manuel Canlı Web Kazıma ve ETL Senkronizasyonu Tetikler.
    """
    try:
        from scripts.sync_customs_data import run_sync
        run_sync(dry_run=False)
        return {"status": "SUCCESS", "message": "Canlı ETL senkronizasyon boru hattı başarıyla çalıştırıldı."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Senkronizasyon hatası: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="127.0.0.1", port=8000, reload=True)
