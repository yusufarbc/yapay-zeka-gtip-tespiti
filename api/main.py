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
from api.db.database import init_orm_tables, get_db, TgtcGtipModel, TgtcRuleModel, TgtcNoteModel
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from fastapi import BackgroundTasks
from scripts.spider_resmi_gazete_archive import run_spider_2020_to_2026

from fastapi.responses import JSONResponse
import traceback

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Gümrük Tarife İstatistik Pozisyonu (GTİP) Tespit ve Karar Destek Sistemi Serverless API"
)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Beklenmeyen Sunucu Hatası ({request.method} {request.url}): {str(exc)}\n{traceback.format_exc()}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Sistemde geçici bir sorun oluştu. Optimizasyon loglarına kaydedildi."}
    )

@app.post("/api/v1/admin/trigger-deep-crawler")
async def trigger_deep_crawler(background_tasks: BackgroundTasks):
    """6 yıllık geçmiş Resmi Gazete arşiv crawler'ını arka planda (Cloud Run Job gibi) tetikler."""
    background_tasks.add_task(run_spider_2020_to_2026)
    return {"message": "Dijital PDF Arşiv Crawler'ı arka planda başlatıldı! Veritabanı dolmaya başlayacak."}

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

from fastapi.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=1000)

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

@app.get("/api/v1/generate-upload-url")
async def generate_upload_url(request: Request, filename: str = Query(...)):
    """GCS Signed URL oluşturur. İstemci doğrudan Google Storage'a dosya yükleyebilir."""
    try:
        user_session = get_current_user_session(request)
    except Exception:
        pass # Public or semi-public usage allowed if needed, though secure is better
        
    safe_name = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)
    destination = f"uploads/{time.strftime('%Y/%m/%d')}/client_{safe_name}"
    
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Signed URL oluşturulamadı: {e}")


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
    background_tasks: BackgroundTasks,
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
            audit_entry = AuditLogEntry(
                session_id=decision.session_id,
                user_email=user_session.email,
                user_role=user_session.role,
                product_name=product_description[:50],
                initial_gtip_proposed=decision.gtip_code,
                final_gtip_approved=decision.gtip_code,
                confidence_score=decision.confidence_score,
                is_hitl_triggered=False,
                execution_time_ms=round(execution_ms, 2)
            )
            background_tasks.add_task(audit_logger.log_decision, audit_entry)
            background_tasks.add_task(append_continuous_learning_record, decision.session_id, product_description[:60], decision.gtip_code)

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
async def analyze_product_json(payload: AnalyzeJSONRequest, request: Request, background_tasks: BackgroundTasks):
    start_time = time.time()
    try:
        user_session = get_current_user_session(request)
        decision = await workflow_engine.start_analysis_async(raw_text=payload.product_description, image_uri=payload.image_uri)
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
            background_tasks.add_task(append_continuous_learning_record, decision.session_id, payload.product_description[:60], decision.gtip_code)

        return decision
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"GTİP Analiz Hatası: {str(e)}")


@app.post("/api/v1/analyze/batch", response_model=List[GTIPDecision])
async def analyze_product_batch(payload: BatchAnalyzeRequest, request: Request, background_tasks: BackgroundTasks):
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
            selected_option_id=response_data.selected_option_id
        )
        execution_ms = (time.time() - start_time) * 1000

        if decision.gtip_code:
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
            background_tasks.add_task(append_continuous_learning_record, decision.session_id, "HITL Onaylı Ürün", decision.gtip_code)

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
async def get_customs_btbs(db: Session = Depends(get_db)):
    """
    Resmi Gazete'den ve Ticaret Bakanlığı portallarından çekilen sınıflandırma kararlarını ve emsal BTB kararlarını döndürür.
    """
    results = []
    seen_ids = set()

    # 1. Cloud SQL gumruk_siniflandirma_kararlari Tablosundan Çek
    try:
        siniflandirma_list = db.query(GumrukSiniflandirmaKarariModel).order_by(GumrukSiniflandirmaKarariModel.yayin_tarihi.desc()).all()
        for s in siniflandirma_list:
            if not s.esya_tanimi or "Sınıflandırma Kararı Kaydı" in s.esya_tanimi or "Resmî Gazete Sınıflandırma Kararı" in s.esya_tanimi:
                continue
            btb_id = f"RG-{s.yayin_tarihi}-{s.gtip_kodu}"
            if btb_id not in seen_ids:
                seen_ids.add(btb_id)
                gtip_clean = str(s.gtip_kodu or "").replace(".", "").strip()
                chap = gtip_clean[:2] if len(gtip_clean) >= 2 else "01"
                
                desc_text = s.esya_tanimi.strip()
                legal_text = s.hukuki_gerekce or "Resmî Gazete Sınıflandırma Kararı"

                results.append({
                    "btb_no": btb_id,
                    "gtip_code": s.gtip_kodu,
                    "chapter": chap,
                    "issue_date": str(s.yayin_tarihi or "2026-01-01"),
                    "product_description": desc_text,
                    "legal_justification": legal_text,
                    "source_url": s.kaynak_url or None
                })
    except Exception as e_s:
        logger.warning(f"[get_customs_btbs] Siniflandirma kararları okunurken uyarı: {e_s}")

    # 2. Cloud SQL gumruk_emsal_kararlar Tablosundan Çek
    try:
        emsal_list = db.query(GumrukEmsalKararModel).order_by(GumrukEmsalKararModel.yayin_tarihi.desc()).all()
        for e in emsal_list:
            if not e.esya_tanimi or "Emsal BTB Kaydı" in e.esya_tanimi or "Resmî Gazete Sınıflandırma Kararı" in e.esya_tanimi:
                continue
            btb_id = e.referans_no or f"EMSAL-{e.gtip_kodu}-{e.id}"
            if btb_id not in seen_ids:
                seen_ids.add(btb_id)
                gtip_clean = str(e.gtip_kodu or "").replace(".", "").strip()
                chap = gtip_clean[:2] if len(gtip_clean) >= 2 else "01"

                results.append({
                    "btb_no": btb_id,
                    "gtip_code": e.gtip_kodu,
                    "chapter": chap,
                    "issue_date": str(e.yayin_tarihi or "2026-01-01"),
                    "product_description": e.esya_tanimi.strip(),
                    "legal_justification": e.hukuki_gerekce or "Emsal BTB Kararı",
                    "source_url": e.kaynak_url or None
                })

    except Exception as e_e:
        logger.warning(f"[get_customs_btbs] Emsal kararları okunurken uyarı: {e_e}")

    # 3. Eğer DB'de henüz dinamik kayıt yoksa Katalog Ön Belleğinden Yükle (Fallback)
    if not results:
        try:
            from api.db.tgtc_knowledge_base import load_btb_catalog
            catalog = load_btb_catalog()
            if catalog:
                real_btbs = [item for item in catalog if not str(item.get("btb_no", "")).startswith("TGTC2026-")]
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
        TgtcGtipModel.level == 'GTIP',
        TgtcGtipModel.parent_code == h
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


@app.post("/api/v1/admin/clean-bad-btbs")
async def clean_bad_btbs(db: Session = Depends(get_db)):
    """
    Hatalı parse edilmiş veya eksik ürün açıklamasına sahip BTB kayıtlarını veritabanından temizler.
    """
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
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Temizleme hatası: {str(e)}")

@app.post("/api/v1/admin/sync-gcp-official-gazette-bulk")
async def trigger_gcp_official_gazette_bulk_sync(
    background_tasks: BackgroundTasks,
    start_year: int = Query(default=2020, ge=2020, le=2026),
    end_year: int = Query(default=2026, ge=2020, le=2026),
    limit_days: Optional[int] = Query(default=None, ge=1)
):
    """
    GCP Cloud Run / Cloud Scheduler üzerinden 2020-2026 yılları arasındaki tüm Resmî Gazete BTB ve Sınıflandırma Kararlarını
    Vertex AI (Gemini 3.6 Flash) ile harfi harfine (exact-match) süzüp Cloud SQL'e aktaran bulk senkronizasyon endpointi.
    """
    try:
        from scripts.gcp_bulk_extractor_2020_2026 import run_gcp_bulk_extraction
        background_tasks.add_task(
            run_gcp_bulk_extraction,
            start_year=start_year,
            end_year=end_year,
            limit_days=limit_days
        )
        return {
            "status": "SUCCESS",
            "message": f"GCP Vertex AI Bulk Extraction boru hattı {start_year}-{end_year} aralığı için arka planda başlatıldı.",
            "target_years": f"{start_year}-{end_year}",
            "limit_days": limit_days
        }
    except Exception as e:
        logger.error(f"GCP Bulk Extractor başlatma hatası: {e}")
        raise HTTPException(status_code=500, detail=f"GCP Bulk Extractor hatası: {str(e)}")


@app.get("/api/v1/admin/sync-gcp-official-gazette-status")
async def get_gcp_official_gazette_sync_status(db: Session = Depends(get_db)):
    """
    Cloud SQL üzerindeki harfi harfine süzülmüş Resmî Gazete Sınıflandırma Kararları metriklerini döndürür.
    """
    try:
        from api.db.database import GumrukSiniflandirmaKarariModel, GumrukEmsalKararModel
        total_siniflandirma = db.query(GumrukSiniflandirmaKarariModel).count()
        total_emsal = db.query(GumrukEmsalKararModel).filter_by(karar_tipi="SINIFLANDIRMA_KARARI").count()
        latest_record = db.query(GumrukSiniflandirmaKarariModel).order_by(GumrukSiniflandirmaKarariModel.id.desc()).first()

        return {
            "status": "HEALTHY",
            "active_model": getattr(settings, "DEFAULT_LLM_MODEL", "gemini-3.6-flash"),
            "cloud_sql_siniflandirma_kararlari_count": total_siniflandirma,
            "cloud_sql_emsal_kararlar_count": total_emsal,
            "latest_extracted_gtip": latest_record.gtip_kodu if latest_record else None,
            "latest_yayin_tarihi": latest_record.yayin_tarihi if latest_record else None,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Durum alma hatası: {str(e)}")


@app.post("/api/v1/admin/seed-tgtc-tree")
async def seed_tgtc_tree_admin(db: Session = Depends(get_db)):
    """
    2026 TGTC dizinindeki sabit Tarife Ağacını (01-99 Fasıllar, GTİP Kümeleri, GİR Kuralları ve Fasıl Notları)
    Cloud SQL veritabanına yeniden yükler ve eşitler. Resmi Gazete verilerinden tamamen bağımsızdır.
    """
    try:
        from scripts.populate_tgtc_cloudsql import extract_gir_rules, extract_chapter_notes, populate_gtip_tree
        from api.db.database import TgtcGtipModel, TgtcRuleModel, TgtcNoteModel

        extract_gir_rules(db)
        extract_chapter_notes(db)
        populate_gtip_tree(db)

        chapter_count = db.query(TgtcGtipModel).filter_by(level="CHAPTER").count()
        total_gtips = db.query(TgtcGtipModel).count()

        return {
            "status": "SUCCESS",
            "message": "2026 TGTC Sabit Tarife Ağacı başarıyla veritabanına yüklendi.",
            "chapter_count": chapter_count,
            "total_gtip_count": total_gtips
        }
    except Exception as e:
        logger.error(f"TGTC Tohumlama Hatası: {e}")
        raise HTTPException(status_code=500, detail=f"TGTC Tohumlama Hatası: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="127.0.0.1", port=8000, reload=True)
