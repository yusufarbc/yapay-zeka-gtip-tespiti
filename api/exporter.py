import os
from io import BytesIO
from typing import List
from api.schemas.product import GTIPDecision

class PDFExporter:
    """
    Resmi Gümrük GTİP Tespit ve BTB Dayanak Raporu PDF Oluşturucusu.
    Türkçe karakter (UTF-8) tam desteği ile tekli ve toplu rapor üretir.
    """

    def _setup_turkish_font(self):
        """
        ReportLab TTFont ve Font Family kaydı yapar.
        registerFontFamily çağrısı <b>, <strong> ve <i> etiketlerinin Helvetica'ya düşmesini engeller.
        """
        try:
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont

            if "TR-Font" in pdfmetrics.getRegisteredFontNames():
                return "TR-Font"

            font_candidates = [
                ("C:\\Windows\\Fonts\\arial.ttf", "C:\\Windows\\Fonts\\arialbd.ttf"),
                ("C:\\Windows\\Fonts\\segoeui.ttf", "C:\\Windows\\Fonts\\segoeuib.ttf"),
                ("C:\\Windows\\Fonts\\calibri.ttf", "C:\\Windows\\Fonts\\calibrib.ttf"),
                ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
                ("/usr/share/fonts/TTF/DejaVuSans.ttf", "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"),
                ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
            ]

            for reg_path, bold_path in font_candidates:
                if os.path.exists(reg_path):
                    pdfmetrics.registerFont(TTFont("TR-Font", reg_path))
                    bold_font_name = "TR-Font"
                    if os.path.exists(bold_path):
                        pdfmetrics.registerFont(TTFont("TR-Font-Bold", bold_path))
                        bold_font_name = "TR-Font-Bold"

                    # KRİTİK: Font Ailesi Kaydı (HTML <b>, <i> etiketleri için)
                    pdfmetrics.registerFontFamily(
                        "TR-Font",
                        normal="TR-Font",
                        bold=bold_font_name,
                        italic="TR-Font",
                        boldItalic=bold_font_name
                    )
                    return "TR-Font"

        except Exception as e:
            print(f"Font kayıt uyarısı: {e}")

        return "Helvetica"

    def _build_story_for_decision(self, decision: GTIPDecision, font_family: str, index: int = 1):
        from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib import colors

        title_style = ParagraphStyle(
            f'TitleStyle_{index}',
            fontName=font_family,
            fontSize=13,
            textColor=colors.HexColor("#0f172a"),
            alignment=1, # Center
            spaceAfter=14,
            leading=17
        )

        heading_style = ParagraphStyle(
            f'HeadingStyle_{index}',
            fontName=font_family,
            fontSize=10.5,
            textColor=colors.HexColor("#1e293b"),
            spaceBefore=10,
            spaceAfter=4,
            leading=13
        )

        body_style = ParagraphStyle(
            f'BodyStyle_{index}',
            fontName=font_family,
            fontSize=9,
            textColor=colors.HexColor("#334155"),
            spaceAfter=4,
            leading=12
        )

        elements = []

        # Başlık
        elements.append(Paragraph(f"<b>GÜMRÜK TARİFE İSTATİSTİK POZİSYONU (GTİP) TESPİT VE GEREKÇE RAPORU</b>", title_style))
        elements.append(Spacer(1, 6))

        # Genel Bilgiler Tablosu
        data = [
            [Paragraph("<b>Oturum Kimliği:</b>", body_style), Paragraph(decision.session_id, body_style)],
            [Paragraph("<b>Nihai GTİP Kodu:</b>", body_style), Paragraph(f"<b>{decision.gtip_code or 'Tespit Edilemedi'}</b>", body_style)],
            [Paragraph("<b>Güven Skoru:</b>", body_style), Paragraph(f"<b>%{int(decision.confidence_score * 100)}</b>", body_style)],
            [Paragraph("<b>Durum:</b>", body_style), Paragraph(decision.status, body_style)]
        ]

        t = Table(data, colWidths=[140, 390])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#f8fafc")),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#cbd5e1")),
            ('PADDING', (0,0), (-1,-1), 5),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 10))

        # Uygulanan GİR Kuralları
        elements.append(Paragraph("<b>1. UYGULANAN GÜMRÜK GENEL YORUM KURALLARI (GİR)</b>", heading_style))
        if decision.applied_gir_rules:
            for rule in decision.applied_gir_rules:
                elements.append(Paragraph(f"• {rule}", body_style))
        else:
            elements.append(Paragraph("• GİR 1 ve GİR 6 temel kuralları uygulandı.", body_style))
        elements.append(Spacer(1, 8))

        # 2. Orijinal Resmi Mevzuat Maddesi (Veritabanı Kaydı - SIFIR HALÜSİNASYON)
        elements.append(Paragraph("<b>2. RESMİ MEVZUAT VE İZAHNAME HÜKMÜ (VERİTABANI ORİJİNAL KAYDI)</b>", heading_style))
        statute_text = decision.official_statute_text or decision.legal_justification or "Resmi Gümrük Tarife Cetveli (TGTC) hükümleri uyarınca."
        elements.append(Paragraph(statute_text, body_style))
        elements.append(Spacer(1, 8))

        # 3. Yapay Zeka Ajan Yorumu (LLM Commentary)
        if decision.llm_reasoning_commentary:
            elements.append(Paragraph("<b>3. YAPAY ZEKA AJAN DEĞERLENDİRMESİ (LLM COMMENTARY)</b>", heading_style))
            elements.append(Paragraph(decision.llm_reasoning_commentary, body_style))
            elements.append(Spacer(1, 8))

        # 4. Emsal BTB Kararları
        if decision.precedent_btbs:
            elements.append(Paragraph("<b>4. TİCARET BAKANLIĞI EMSAL BTB KARARLARI</b>", heading_style))
            btb_data = [[
                Paragraph("<b>BTB No</b>", body_style),
                Paragraph("<b>Tarih</b>", body_style),
                Paragraph("<b>GTİP Kodu</b>", body_style),
                Paragraph("<b>Emsal Ürün Açıklaması</b>", body_style)
            ]]
            for btb in decision.precedent_btbs:
                btb_data.append([
                    Paragraph(btb.btb_no, body_style),
                    Paragraph(btb.issue_date, body_style),
                    Paragraph(f"<b>{btb.gtip_code}</b>", body_style),
                    Paragraph(btb.product_description[:90] + ("..." if len(btb.product_description) > 90 else ""), body_style)
                ])

            btb_table = Table(btb_data, colWidths=[115, 65, 95, 255])
            btb_table.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#e2e8f0")),
                ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#cbd5e1")),
                ('PADDING', (0,0), (-1,-1), 4),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ]))
            elements.append(btb_table)

        return elements

    def generate_pdf_report(self, decision: GTIPDecision) -> bytes:
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.platypus import SimpleDocTemplate
            font_family = self._setup_turkish_font()

            buffer = BytesIO()
            doc = SimpleDocTemplate(
                buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36
            )
            story = self._build_story_for_decision(decision, font_family, index=1)
            doc.build(story)
            pdf_bytes = buffer.getvalue()
            buffer.close()
            return pdf_bytes
        except Exception as e:
            print("PDF tekli rapor hatası:", e)
            text_content = f"GTİP TESPİT RAPORU\nOturum: {decision.session_id}\nGTİP: {decision.gtip_code}\n"
            return text_content.encode("utf-8")

    def generate_bulk_pdf_report(self, decisions: List[GTIPDecision]) -> bytes:
        """
        Seçilen birden fazla GTİP kararını konsolide tek bir toplu PDF raporda birleştirir.
        """
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
            from reportlab.lib.styles import ParagraphStyle
            from reportlab.lib import colors

            font_family = self._setup_turkish_font()

            buffer = BytesIO()
            doc = SimpleDocTemplate(
                buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36
            )
            story = []

            main_title_style = ParagraphStyle(
                'MainTitleStyle',
                fontName=font_family,
                fontSize=14,
                textColor=colors.HexColor("#0f172a"),
                alignment=1,
                spaceAfter=14,
                leading=18
            )

            body_style = ParagraphStyle(
                'BulkBodyStyle',
                fontName=font_family,
                fontSize=9,
                textColor=colors.HexColor("#334155"),
                spaceAfter=4,
                leading=12
            )

            # 1. TOPLU KAPAK / ÖZET SAYFASI
            story.append(Paragraph("<b>TOPLU GÜMRÜK TARİFE İSTATİSTİK POZİSYONU (GTİP) RAPORU</b>", main_title_style))
            story.append(Paragraph(f"Toplam <b>{len(decisions)} adet</b> GTİP analizi için konsolide karar ve gerekçe belgesi.", body_style))
            story.append(Spacer(1, 10))

            # Özet Tablosu
            summary_data = [[
                Paragraph("<b>#</b>", body_style),
                Paragraph("<b>Oturum ID</b>", body_style),
                Paragraph("<b>Nihai GTİP Kodu</b>", body_style),
                Paragraph("<b>Güven Skoru</b>", body_style),
                Paragraph("<b>Durum</b>", body_style)
            ]]

            for idx, d in enumerate(decisions, 1):
                summary_data.append([
                    Paragraph(str(idx), body_style),
                    Paragraph(d.session_id[:12] + "...", body_style),
                    Paragraph(f"<b>{d.gtip_code or 'Belirsiz'}</b>", body_style),
                    Paragraph(f"<b>%{int(d.confidence_score * 100)}</b>", body_style),
                    Paragraph(d.status, body_style)
                ])

            summary_table = Table(summary_data, colWidths=[30, 150, 160, 90, 100])
            summary_table.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#e2e8f0")),
                ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#cbd5e1")),
                ('PADDING', (0,0), (-1,-1), 5),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ]))
            story.append(summary_table)
            story.append(Spacer(1, 15))

            # 2. HER BİR KARAR İÇİN DETAY SAYFALARI
            for idx, d in enumerate(decisions, 1):
                story.append(PageBreak())
                item_story = self._build_story_for_decision(d, font_family, index=idx)
                story.extend(item_story)

            doc.build(story)
            pdf_bytes = buffer.getvalue()
            buffer.close()
            return pdf_bytes
        except Exception as e:
            print("PDF toplu rapor hatası:", e)
            text_content = f"TOPLU GTİP TESPİT RAPORU\nToplam {len(decisions)} adet karar.\n"
            return text_content.encode("utf-8")

pdf_exporter = PDFExporter()
