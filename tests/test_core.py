import hashlib
from datetime import datetime, timedelta, timezone

from radar.config import from_env, parse_searches
from radar.detector import DetectorConfig, evaluate
from radar.models import LastPost, Offer, PriceStats
from radar.site import render, sparkline, store_of
from radar.sources.mercadolivre import MercadoLivreSource
from radar.sources.shopee import build_query, parse_node, sign
from radar.telegram import brl, caption

CFG = DetectorConfig()


def offer(price=100.0, original=None, rating=4.8, sales=500, source="t"):
    return Offer(source, "1", "Produto <teste>", price, original, None,
                 "https://x.com/?a=1&b=2", rating, sales, "Loja")


def stats(n=5, mn=110.0, med=130.0):
    return PriceStats(n, mn, med)


def test_drop_vs_median_posts():
    ok, why = evaluate(offer(100), stats(med=130), None, CFG)
    assert ok and "abaixo" in why


def test_small_drop_skips():
    assert not evaluate(offer(120), stats(mn=115, med=130), None, CFG)[0]


def test_new_low_posts():
    assert evaluate(offer(105), stats(mn=110, med=120), None, CFG)[0]


def test_quality_filters():
    assert not evaluate(offer(rating=3.9), stats(), None, CFG)[0]
    assert not evaluate(offer(sales=3), stats(), None, CFG)[0]


def test_repost_rules():
    assert not evaluate(offer(99), stats(), LastPost(100, 10), CFG)[0]
    assert evaluate(offer(90), stats(), LastPost(100, 10), CFG)[0]
    assert not evaluate(offer(80), stats(), LastPost(100, 0.5), CFG)[0]


def test_shopee_sign_and_query():
    h = sign("123", "sec", 1700000000, '{"query":"x"}')
    expected = hashlib.sha256(b'1231700000000{"query":"x"}sec').hexdigest()
    assert h == f"SHA256 Credential=123, Timestamp=1700000000, Signature={expected}"
    assert 'keyword: "fone \\"pro\\""' in build_query('fone "pro"', 2, 1, 50)


def test_shopee_parse_node():
    o = parse_node({"itemId": 42, "productName": " Fone ", "priceMin": "80.00", "priceDiscountRate": 20,
                    "ratingStar": "4.9", "sales": 1200, "offerLink": "https://s.shopee.com.br/abc"})
    assert o.item_id == "42" and o.price == 80.0 and o.original_price == 100.0


def test_ml_affiliate_link():
    s = MercadoLivreSource("id", "sec", "minhaetiqueta", "123", None)
    assert s.link("MLB1").endswith("/p/MLB1?matt_word=minhaetiqueta&matt_tool=123")


def test_caption():
    c = caption(offer(1234.5, 9999), "teste", "rodapé", typical=1500)
    assert "R$ 1.234,50" in c and "&lt;teste&gt;" in c and "<s>R$ 1.500,00</s>" in c and "9.999" not in c
    m = caption(offer(417.93, source="mercadolivre"), "x", "")
    assert "a partir de <b>R$ 417,93</b>" in m
    assert brl(0.5) == "R$ 0,50"


def test_config_from_env(monkeypatch):
    monkeypatch.setenv("SEARCHES", "shopee:fone bluetooth; ml:air fryer; xyz:ignorado")
    monkeypatch.setenv("QUIET_HOURS", "")
    cfg = from_env()
    assert [s["source"] for s in cfg["searches"]] == ["shopee", "mercadolivre"]
    assert cfg["posting"]["quiet_hours"] is None and cfg["detector"]["cold_start_discount_pct"] == 101
    monkeypatch.delenv("SEARCHES")
    demo = from_env()
    assert demo["searches"] == [{"source": "fake"}] and demo["detector"]["cold_start_discount_pct"] == 50
    assert parse_searches("ML: smartwatch")[0]["keyword"] == "smartwatch"


def test_site_render(monkeypatch):
    monkeypatch.delenv("SITE_TG_LINK", raising=False)
    now = datetime(2026, 11, 10, 12, tzinfo=timezone.utc)
    rows = [{"source": "shopee", "shop": "Loja", "item_id": "a", "price": 99.9, "typical": 130.0,
             "reason": "23% abaixo", "posted_at": now - timedelta(hours=2), "url": "https://x.com/?a=1&b=2",
             "title": "Fone <X>", "image_url": None, "series": [130, 128, 99.9]}]
    h = render(rows, {"monitored": 3700, "stores": 2, "posts24": 1}, "Radar de Ofertas", "@Canal", "",
               "", now)
    assert "Fone &lt;X&gt;" in h and "R$ 99,90" in h and "-23%" in h and "https://t.me/Canal" in h
    assert "<polyline" in sparkline([3, 2, 1]) and store_of("mercadolivre", None)[1] == "Mercado Livre"
