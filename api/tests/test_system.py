from api.schemas.product import ProductFeatures
from api.modules.rule_engine import rule_engine
from api.graph.workflow import workflow_engine
from api.exporter import pdf_exporter

def test_rule_engine_gir3b():
    features = ProductFeatures(
        product_name="Pamuklu Dokuma Kumaş",
        primary_material="Pamuk",
        composition_percentages={"cotton": 0.60, "polyester": 0.40},
        intended_use="Tekstil"
    )
    allowed_chapters, rules = rule_engine.apply_rules(features)
    assert "52" in allowed_chapters
    assert "55" not in allowed_chapters

def test_workflow_end_to_end():
    # 1. Diş Fırçası (Motorlu ev aleti)
    decision = workflow_engine.start_analysis("Şarj edilebilir dahili 3.7V elektrik motorlu diş fırçası, ağırlığı 250 gram.")
    assert decision.gtip_code == "8509.80.00.00.00"
    assert decision.status == "COMPLETED"
    assert decision.confidence_score >= 0.90

    # 2. PDF Rapor Oluşturma
    pdf_bytes = pdf_exporter.generate_pdf_report(decision)
    assert pdf_bytes is not None
    assert len(pdf_bytes) > 50
