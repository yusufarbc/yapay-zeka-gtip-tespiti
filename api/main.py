import time
import os
import json
from fastapi import FastAPI, HTTPException, Depends, Response, Form, UploadFile, File, Request
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List
from pydantic import BaseModel

from api.config import settings
from api.schemas.product import GTIPDecision, HITLResponse
from api.schemas.audit import AuditLogEntry, AuditLogQueryResponse
from api.graph.workflow import workflow_engine
from api.exporter import pdf_exporter
from api.db.audit_logger import audit_logger
from api.db.gcp_emulator import local_state_store

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Gümrük Tarife İstatistik Pozisyonu (GTİP) Tespit ve Karar Destek Sistemi Serverless API"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AnalyzeJSONRequest(BaseModel):
    product_description: str
    image_uri: Optional[str] = None

class BatchAnalyzeRequest(BaseModel):
    product_descriptions: List[str]

def append_continuous_learning_record(session_id: str, product_name: str, gtip_code: str):
    """
    Continuous Learning (Geri Beslemeli Öğrenen Sistem):
    Kullanıcının/Müşavirin onayladığı yeni GTİP kararlarını kurumsal emsal veritabanına ekler.
    """
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        dataset_file = os.path.join(base_dir, "api", "data", "official_btb_database.json")
        records = []
        if os.path.exists(dataset_file):
            with open(dataset_file, "r", encoding="utf-8") as f:
                records = json.load(f)

        new_entry = {
            "btb_no": f"KURUMSAL-EMSAL-{session_id[:8].upper()}",
            "gtip_code": gtip_code,
            "chapter": gtip_code[:2],
            "heading": gtip_code[:4],
            "issue_date": time.strftime("%Y-%m-%d"),
            "product_description": product_name,
            "legal_justification": f"Gümrük Müşaviri tarafından onaylanan kurumsal emsal karar ({session_id[:8]})."
        }
        records.append(new_entry)
        os.makedirs(os.path.dirname(dataset_file), exist_ok=True)
        with open(dataset_file, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("Continuous Learning kaydı uyarısı:", e)

@app.get("/api/v1/health")
def health_check():
    return {
        "status": "healthy",
        "environment": settings.ENVIRONMENT,
        "region": settings.GCP_REGION,
        "emulator_mode": settings.USE_GCP_EMULATOR,
        "version": settings.VERSION
    }

@app.post("/api/v1/analyze", response_model=GTIPDecision)
async def analyze_product(
    product_description: str = Form(...),
    image: Optional[UploadFile] = File(None)
):
    start_time = time.time()
    try:
        image_uri = f"local_storage://{image.filename}" if image else None
        decision = workflow_engine.start_analysis(raw_text=product_description, image_uri=image_uri)
        execution_ms = (time.time() - start_time) * 1000

        if decision.status == "COMPLETED" and decision.gtip_code:
            audit_logger.log_decision(AuditLogEntry(
                session_id=decision.session_id,
                user_email="ahmet@musavir.com",
                user_role="senior_broker",
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

@app.post("/api/v1/analyze-json", response_model=GTIPDecision)
async def analyze_product_json(payload: AnalyzeJSONRequest):
    start_time = time.time()
    try:
        decision = workflow_engine.start_analysis(raw_text=payload.product_description, image_uri=payload.image_uri)
        execution_ms = (time.time() - start_time) * 1000

        if decision.status == "COMPLETED" and decision.gtip_code:
            audit_logger.log_decision(AuditLogEntry(
                session_id=decision.session_id,
                user_email="ahmet@musavir.com",
                user_role="senior_broker",
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
async def analyze_product_batch(payload: BatchAnalyzeRequest):
    """
    Toplu Fatura / Multi-Item Batch GTİP Analizi Endpoint'i.
    Faturadaki tüm ürün kalemlerini satır satır ayrıştırıp her kalem için 6 aşamalı boru hattını çalıştırır.
    """
    if not payload.product_descriptions:
        raise HTTPException(status_code=400, detail="En az bir ürün tanımı gönderilmelidir.")
    
    results = []
    for desc in payload.product_descriptions[:20]: # Güvenli toplu iş sınırı
        if desc.strip():
            dec = workflow_engine.start_analysis(raw_text=desc.strip())
            results.append(dec)

    return results

@app.post("/api/v1/hitl/respond", response_model=GTIPDecision)
async def respond_hitl(response_data: HITLResponse):
    start_time = time.time()
    try:
        decision = workflow_engine.resume_analysis(
            session_id=response_data.session_id,
            selected_option_id=response_data.selected_option_id
        )
        execution_ms = (time.time() - start_time) * 1000

        if decision.gtip_code:
            audit_logger.log_decision(AuditLogEntry(
                session_id=decision.session_id,
                user_email="ahmet@musavir.com",
                user_role="senior_broker",
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
async def get_pdf_report(session_id: str):
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
    session_ids: list[str]

@app.post("/api/v1/report/pdf/bulk")
async def get_bulk_pdf_report(payload: BulkPDFRequest):
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
async def get_audit_logs(limit: int = 50):
    logs = audit_logger.get_all_logs(limit=limit)
    return AuditLogQueryResponse(total_count=len(logs), entries=logs)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="127.0.0.1", port=8000, reload=True)
