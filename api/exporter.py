from io import BytesIO
from api.schemas.product import GTIPDecision

class PDFExporter:
    """
    Resmi Gümrük GTİP Tespit ve BTB Dayanak Raporu PDF Oluşturucusu.
    """

    def generate_pdf_report(self, decision: GTIPDecision) -> bytes:
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib import colors

            buffer = BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
            story = []

            styles = getSampleStyleSheet()
            title_style = ParagraphStyle(
                'TitleStyle',
                parent=styles['Heading1'],
                fontName='Helvetica-Bold',
                fontSize=16,
                textColor=colors.HexColor("#1e293b"),
                alignment=1, # Center
                spaceAfter=20
            )

            heading_style = ParagraphStyle(
                'HeadingStyle',
                parent=styles['Heading2'],
                fontName='Helvetica-Bold',
                fontSize=12,
                textColor=colors.HexColor("#0f172a"),
                spaceBefore=10,
                spaceAfter=6
            )

            body_style = ParagraphStyle(
                'BodyStyle',
                parent=styles['Normal'],
                fontName='Helvetica',
                fontSize=10,
                textColor=colors.HexColor("#334155"),
                spaceAfter=6
            )

            # Başlık
            story.append(Paragraph("GÜMRÜK TARİFE İSTATİSTİK POZİSYONU (GTİP) TESPİT VE GEREKÇE RAPORU", title_style))
            story.append(Spacer(1, 10))

            # Genel Bilgiler Tablosu
            data = [
                [Paragraph("<b>Oturum Kimliği:</b>", body_style), Paragraph(decision.session_id, body_style)],
                [Paragraph("<b>Nihai GTİP Kodu:</b>", body_style), Paragraph(f"<b>{decision.gtip_code or 'Tespit Edilemedi'}</b>", body_style)],
                [Paragraph("<b>Güven Skoru:</b>", body_style), Paragraph(f"%{int(decision.confidence_score * 100)}", body_style)],
                [Paragraph("<b>Durum:</b>", body_style), Paragraph(decision.status, body_style)]
            ]

            t = Table(data, colWidths=[150, 380])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#f8fafc")),
                ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#cbd5e1")),
                ('PADDING', (0,0), (-1,-1), 6),
            ]))
            story.append(t)
            story.append(Spacer(1, 15))

            # Uygulanan GİR Kuralları
            story.append(Paragraph("1. UYGULANAN GÜMRÜK GENEL YORUM KURALLARI (GİR)", heading_style))
            for rule in decision.applied_gir_rules:
                story.append(Paragraph(f"• {rule}", body_style))
            story.append(Spacer(1, 10))

            # Hukuki Gerekçe
            story.append(Paragraph("2. HUKUKİ GEREKÇE VE MEVZUAT DAYANAĞI", heading_style))
            story.append(Paragraph(decision.legal_justification or "Resmi tebliğler uyarınca.", body_style))
            story.append(Spacer(1, 10))

            # Emsal BTB Kararları
            if decision.precedent_btbs:
                story.append(Paragraph("3. TİCARET BAKANLIĞI EMSAL BTB KARARLARI", heading_style))
                btb_data = [["BTB No", "Tarih", "GTİP", "Ürün Açıklaması"]]
                for btb in decision.precedent_btbs:
                    btb_data.append([
                        Paragraph(btb.btb_no, body_style),
                        Paragraph(btb.issue_date, body_style),
                        Paragraph(btb.gtip_code, body_style),
                        Paragraph(btb.product_description[:80] + "...", body_style)
                    ])

                btb_table = Table(btb_data, colWidths=[110, 70, 100, 250])
                btb_table.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#e2e8f0")),
                    ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#cbd5e1")),
                    ('PADDING', (0,0), (-1,-1), 4),
                ]))
                story.append(btb_table)

            doc.build(story)
            pdf_bytes = buffer.getvalue()
            buffer.close()
            return pdf_bytes
        except ImportError:
            # Fallback simple text PDF header if reportlab is not yet installed locally
            text_content = f"GTİP TESPİT RAPORU\nOturum: {decision.session_id}\nGTİP: {decision.gtip_code}\nGüven: %{int(decision.confidence_score*100)}\n"
            return text_content.encode("utf-8")

pdf_exporter = PDFExporter()
