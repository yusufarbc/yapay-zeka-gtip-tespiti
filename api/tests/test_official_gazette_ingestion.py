from bs4 import BeautifulSoup

from scripts.scraper_function import extract_customs_articles, is_customs_related
from scripts.scrape_official_btb import _page_rows, parse_btb_detail


def test_extract_customs_articles_splits_madde_hierarchy():
    raw_html = """
    <html><body>
      <h1>GÜMRÜK YÖNETMELİĞİNDE DEĞİŞİKLİK YAPILMASINA DAİR YÖNETMELİK</h1>
      <p>MADDE 1 – 4458 sayılı Gümrük Kanununun uygulamasında beyan usulü değiştirilmiştir.</p>
      <p>GEÇİCİ MADDE 2 – Bu maddenin yayımından önce yapılan başvurular geçerlidir.</p>
    </body></html>
    """

    articles = extract_customs_articles(raw_html)

    assert [article["madde_kodu"] for article in articles] == ["MADDE 1", "GEÇİCİ MADDE 2"]
    assert articles[0]["kanun_no"] == "4458"
    assert "beyan usulü" in articles[0]["madde_metni"]


def test_non_customs_document_is_rejected():
    assert not is_customs_related("Bir üniversitenin fakülte kuruluna ilişkin yönetmelik")
    assert extract_customs_articles("<p>MADDE 1 – Fakülte kurulu toplanır.</p>") == []


def test_official_btb_list_and_detail_parser():
    list_html = """
    <table id="ctl00_ContentPlaceHolder1_GridView1">
      <tr><th>DETAY</th><th>GTIP</th><th>EŞYANIN TANIMI</th><th>TARİH</th></tr>
      <tr><td><a href="javascript:__doPostBack('ctl00$ContentPlaceHolder1$GridView1$ctl02$btn','')">TR060000260016</a></td>
          <td>851610800012</td><td>Su kaynatma kabı</td><td>07/09/2026</td></tr>
    </table>
    """
    rows = _page_rows(BeautifulSoup(list_html, "html.parser"))
    assert rows[0]["btb_no"] == "TR060000260016"
    assert rows[0]["gtip_code"] == "851610800012"

    detail_html = """
    <span id="ctl00_ContentPlaceHolder1_lblBtbNo">TR060000260016</span>
    <span id="ctl00_ContentPlaceHolder1_lblGtip">851610800012</span>
    <span id="ctl00_ContentPlaceHolder1_lblGbastar">07/09/2026</span>
    <span id="ctl00_ContentPlaceHolder1_lblSinger">GİR 1 ve 6 ile sınıflandırılmıştır.</span>
    <span id="ctl00_ContentPlaceHolder1_lblEstanim">Elektrikli su kaynatma kabı</span>
    """
    detail = parse_btb_detail(BeautifulSoup(detail_html, "html.parser"))
    assert detail["legal_justification"].startswith("GİR 1")
    assert detail["product_description"] == "Elektrikli su kaynatma kabı"
