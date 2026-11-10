"""Gera o site estático (vitrine) com as ofertas postadas no canal.

Roda em loop, reescrevendo /site/index.html a cada SITE_REFRESH_S segundos e
copiando os arquivos de radar/static (logo, favicon, imagem de compartilhamento).

Variáveis: SITE_NAME, SITE_URL, CHANNEL_USERNAME, SITE_META (tags <meta> de
verificação, ex.: Lomadee — inseridas como estão no <head>).
"""
import html
import json
import logging
import os
import re
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .db import DB
from .main import env
from .telegram import brl, price_note, price_prefix

log = logging.getLogger("radar.site")
e = html.escape
TZ = ZoneInfo("America/Sao_Paulo")
STATIC = Path(__file__).parent / "static"
STALE_HOURS = 48

# loja -> (rótulo, cor de fundo, cor do texto)
KNOWN = {
    "shopee": ("Shopee", "#EE4D2D", "#FFFFFF"),
    "ml": ("Mercado Livre", "#FFE600", "#2D3277"),
    "amazon": ("Amazon", "#232F3E", "#FF9900"),
    "kabum": ("KaBuM!", "#0060B1", "#FFFFFF"),
}


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "loja"


def store_of(source: str, shop: str | None) -> tuple[str, str, str, str]:
    """(chave, rótulo, fundo, texto) da loja de uma oferta."""
    if source == "shopee":
        key = "shopee"
    elif source == "mercadolivre":
        key = "ml"
    elif source == "amazon":
        key = "amazon"
    elif shop and "kabum" in shop.lower():
        key = "kabum"
    else:
        name = (shop or source).strip()
        name = re.sub(r"\s*-\s*BR$", "", name)
        if name.lower() in ("frete grátis", ""):
            name = source.title()
        return slug(name), name, "#EEF0F3", "#1F2430"
    label, bg, fg = KNOWN[key]
    return key, label, bg, fg


def sparkline(series: list[float] | None, w: int = 120, h: int = 32) -> str:
    """Mini gráfico SVG do menor preço diário (antigo -> recente)."""
    pts = [float(x) for x in (series or []) if x is not None]
    if len(pts) < 2:
        return ""
    lo, hi = min(pts), max(pts)
    span = (hi - lo) or 1.0
    step = (w - 4) / (len(pts) - 1)
    xy = [(2 + i * step, 3 + (h - 6) * (1 - (p - lo) / span)) for i, p in enumerate(pts)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in xy)
    area = f"2,{h} " + line + f" {xy[-1][0]:.1f},{h}"
    lx, ly = xy[-1]
    label = f"Menor preço por dia nos últimos {len(pts)} dias: de {brl(hi)} a {brl(lo)}"
    return (f'<svg class="spark" viewBox="0 0 {w} {h}" role="img" aria-label="{e(label)}">'
            f'<polygon points="{area}" class="spark-area"/>'
            f'<polyline points="{line}" class="spark-line"/>'
            f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="3" class="spark-dot"/></svg>')


def card(r: dict, now: datetime) -> str:
    key, label, bg, fg = store_of(r["source"], r["shop"])
    price, typical = float(r["price"]), r.get("typical")
    drop = round((1 - price / typical) * 100) if typical and typical > price * 1.05 else 0
    posted = r["posted_at"]
    stale = (now - posted) > timedelta(hours=STALE_HOURS)
    url = e(r["url"] or "#", quote=True)
    title = e(r["title"] or "")
    img = (f'<img src="{e(r["image_url"], quote=True)}" alt="" loading="lazy" decoding="async">'
           if r.get("image_url") else '<span class="noimg" aria-hidden="true">🛍️</span>')
    badge = f'<span class="drop">-{drop}%</span>' if drop >= 10 else ""
    was = f'<s class="was" title="Preço típico (mediana dos últimos 30 dias)">{brl(typical)}</s>' if drop else ""
    spark = sparkline(r.get("series"))
    hist = (f'<div class="hist">{spark}<span>histórico de preço</span></div>' if spark else "")
    stale_note = '<span class="stale-note">pode ter acabado</span>' if stale else ""
    return (
        f'<article class="card{" is-stale" if stale else ""}" data-store="{key}" data-price="{price:.2f}" '
        f'data-drop="{drop}" data-ts="{posted.isoformat()}" data-q="{e((r["title"] or "").lower(), quote=True)}">'
        f'<a class="media" href="{url}" rel="sponsored nofollow noopener" target="_blank" tabindex="-1">{img}{badge}</a>'
        f'<div class="body">'
        f'<span class="store" style="--sbg:{bg};--sfg:{fg}">{e(label)}</span>'
        f'<h3 class="title"><a href="{url}" rel="sponsored nofollow noopener" target="_blank">{title}</a></h3>'
        f'<div class="prices">{"<span class=from>a partir de</span>" if price_prefix(r["source"]) else ""}'
        f'<span class="now">{brl(price)}</span>{was}</div>'
        + (f'<div class="paynote">{e(note)}</div>' if (note := price_note(r["source"], r["shop"])) else "") +
        f'{hist}'
        f'<p class="reason">{e(r["reason"] or "")}</p>'
        f'<div class="meta"><time datetime="{posted.isoformat()}">{posted:%d/%m %H:%M}</time>{stale_note}</div>'
        f'<a class="cta" href="{url}" rel="sponsored nofollow noopener" target="_blank">Ver na loja'
        f'<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M5 3h8v8M13 3 4 12"/></svg></a>'
        f'</div></article>')


CSS = """
:root{--bg:#F6F7F9;--surface:#FFFFFF;--text:#14171F;--muted:#5B6271;--line:#E3E6EB;--soft:#EEF0F3;
--brand:#FF5A1F;--brand2:#E8285C;--good:#0E8A4B;--good-bg:#E6F6EE;--shadow:0 1px 2px rgba(16,24,40,.06),0 1px 3px rgba(16,24,40,.08);
--radius:14px}
@media (prefers-color-scheme:dark){:root{--bg:#0E1014;--surface:#171A20;--text:#ECEEF2;--muted:#9AA2B1;--line:#262B33;--soft:#20242C;
--good:#3CCF86;--good-bg:#12291D;--shadow:none}}
*{box-sizing:border-box}[hidden]{display:none!important}html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 Inter,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;-webkit-font-smoothing:antialiased}
a{color:inherit}img{display:block;max-width:100%}
.wrap{max-width:1180px;margin:0 auto;padding:0 16px}
/* topo */
.top{position:sticky;top:0;z-index:20;background:color-mix(in srgb,var(--bg) 88%,transparent);backdrop-filter:saturate(1.4) blur(10px);border-bottom:1px solid var(--line)}
.top .wrap{display:flex;align-items:center;gap:16px;height:60px}
.brand{display:flex;align-items:center;gap:10px;text-decoration:none;font-weight:800;letter-spacing:-.01em;font-size:17px}
.brand img{width:34px;height:34px;border-radius:50%}
.brand small{display:block;font-weight:600;font-size:10px;letter-spacing:.18em;color:var(--muted);margin-top:-3px}
.nav{margin-left:auto;display:flex;align-items:center;gap:6px}
.nav a{text-decoration:none;color:var(--muted);font-weight:600;font-size:14px;padding:8px 10px;border-radius:8px}
.nav a:hover{color:var(--text);background:var(--soft)}
.btn{display:inline-flex;align-items:center;gap:8px;text-decoration:none;font-weight:700;border-radius:10px;padding:10px 16px;font-size:14px;border:0;cursor:pointer}
.btn-tg{background:#229ED9;color:#fff}.btn-tg:hover{filter:brightness(1.06)}
.btn-tg svg{width:18px;height:18px;fill:currentColor}
.nav .btn-tg{color:#fff;padding:8px 14px}.nav .btn-tg:hover{background:#229ED9}
@media (max-width:640px){.nav a:not(.btn){display:none}.nav .btn span{display:none}}
/* hero */
.hero{padding:36px 0 18px}
.hero h1{font-size:clamp(26px,4vw,40px);line-height:1.12;letter-spacing:-.02em;margin:0 0 10px;max-width:760px}
.hero h1 em{font-style:normal;background:linear-gradient(90deg,var(--brand),var(--brand2));-webkit-background-clip:text;background-clip:text;color:transparent}
.hero p{color:var(--muted);font-size:16px;max-width:640px;margin:0}
.stats{display:flex;flex-wrap:wrap;gap:10px;margin-top:20px}
.stat{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:10px 14px;min-width:150px;box-shadow:var(--shadow)}
.stat b{display:block;font-size:20px;letter-spacing:-.01em}.stat span{color:var(--muted);font-size:13px}
/* barra de filtros */
.toolbar{background:var(--bg);padding:12px 0;border-bottom:1px solid var(--line)}
@media (min-width:768px){.toolbar{position:sticky;top:60px;z-index:10}}
.toolbar .wrap{display:flex;flex-wrap:wrap;gap:10px;align-items:center}
.search{flex:1 1 0;min-width:0;position:relative}
.search input{width:100%;height:42px;border:1px solid var(--line);background:var(--surface);color:var(--text);border-radius:10px;padding:0 12px 0 38px;font:inherit}
.search input:focus,.sort select:focus,.chip:focus-visible,.cta:focus-visible{outline:2px solid var(--brand);outline-offset:1px}
.search svg{position:absolute;left:12px;top:12px;width:18px;height:18px;stroke:var(--muted);fill:none;stroke-width:2}
.chips{display:flex;gap:6px;overflow-x:auto;scrollbar-width:none;flex:1 1 100%;order:3}
.chips::-webkit-scrollbar{display:none}
.chip{flex:none;height:34px;padding:0 12px;border-radius:999px;border:1px solid var(--line);background:var(--surface);color:var(--text);font:600 13px Inter,system-ui,sans-serif;cursor:pointer;white-space:nowrap}
.chip[aria-pressed=true]{background:var(--text);color:var(--bg);border-color:var(--text)}
.chip .n{opacity:.6;font-weight:500;margin-left:4px}
.sort select{height:42px;max-width:150px;border:1px solid var(--line);background:var(--surface);color:var(--text);border-radius:10px;padding:0 10px;font:inherit}
.count{color:var(--muted);font-size:13px;margin:16px 0 4px}
/* grade de ofertas */
.grid{display:grid;gap:14px;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));padding-bottom:28px}
@media (max-width:520px){.grid{grid-template-columns:1fr 1fr;gap:10px}}
.card{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);overflow:hidden;display:flex;flex-direction:column;box-shadow:var(--shadow);transition:transform .15s,box-shadow .15s}
.card:hover{transform:translateY(-2px);box-shadow:0 8px 24px rgba(16,24,40,.10)}
.card.is-stale{opacity:.62}
.media{position:relative;display:block;aspect-ratio:1;background:#fff;border-bottom:1px solid var(--line)}
.media img{width:100%;height:100%;object-fit:contain;padding:10px}
.noimg{display:grid;place-items:center;height:100%;font-size:42px;background:var(--soft)}
.drop{position:absolute;top:10px;left:10px;background:var(--good);color:#fff;font-weight:800;font-size:13px;padding:3px 8px;border-radius:8px}
.body{padding:12px;display:flex;flex-direction:column;gap:6px;flex:1}
.store{align-self:flex-start;background:var(--sbg);color:var(--sfg);font-size:11px;font-weight:700;padding:2px 8px;border-radius:6px;letter-spacing:.02em}
.title{margin:0;font-size:14px;font-weight:600;line-height:1.35;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;min-height:2.7em}
.title a{text-decoration:none}.title a:hover{text-decoration:underline}
.prices{display:flex;align-items:baseline;gap:8px;flex-wrap:wrap}
.now{font-size:21px;font-weight:800;letter-spacing:-.01em}
.was{color:var(--muted);font-size:13px}
.paynote{color:var(--muted);font-size:11.5px;margin-top:-4px}
.from{display:block;width:100%;color:var(--muted);font-size:11.5px;margin-bottom:-6px}
.hist{display:flex;align-items:center;gap:8px;color:var(--muted);font-size:11px}
@media (max-width:520px){.hist span{display:none}.spark{width:100%}.hero p{font-size:15px}}
.spark{width:96px;height:26px;flex:none}
.spark-line{fill:none;stroke:var(--good);stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
.spark-area{fill:var(--good-bg);stroke:none}.spark-dot{fill:var(--good)}
.reason{margin:0;font-size:12.5px;font-weight:600;color:var(--good);background:var(--good-bg);align-self:flex-start;padding:2px 8px;border-radius:6px}
.meta{display:flex;gap:8px;align-items:center;color:var(--muted);font-size:12px}
.stale-note{color:#B54708;font-weight:600}
.cta{margin-top:auto;display:flex;align-items:center;justify-content:center;gap:6px;height:40px;border-radius:10px;text-decoration:none;font-weight:700;font-size:14px;color:#fff;background:linear-gradient(90deg,var(--brand),var(--brand2))}
.cta:hover{filter:brightness(1.05)}
.cta svg{width:14px;height:14px;fill:none;stroke:currentColor;stroke-width:2}
.empty{grid-column:1/-1;text-align:center;color:var(--muted);padding:48px 16px;border:1px dashed var(--line);border-radius:var(--radius)}
/* como funciona */
.how{padding:36px 0;border-top:1px solid var(--line)}
.how h2,.band h2{font-size:24px;letter-spacing:-.01em;margin:0 0 18px}
.steps{display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(240px,1fr))}
.step{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);padding:18px}
.step i{display:grid;place-items:center;width:34px;height:34px;border-radius:10px;font-style:normal;font-weight:800;color:#fff;background:linear-gradient(135deg,var(--brand),var(--brand2));margin-bottom:10px}
.step h3{margin:0 0 6px;font-size:16px}.step p{margin:0;color:var(--muted);font-size:14px}
.band{margin:8px 0 36px;padding:26px;border-radius:18px;color:#fff;background:linear-gradient(120deg,#FF7A1A,#E8285C);display:flex;flex-wrap:wrap;gap:16px;align-items:center;justify-content:space-between}
.band h2{margin:0 0 4px}.band p{margin:0;opacity:.92}
.band .btn{background:#fff;color:#14171F}
footer{border-top:1px solid var(--line);padding:22px 0 34px;color:var(--muted);font-size:13px}
footer .wrap{display:flex;flex-wrap:wrap;gap:12px 28px;justify-content:space-between}
footer p{margin:0;max-width:720px}
@media (max-width:640px){.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.stat{min-width:0;padding:8px 10px}.stat b{font-size:17px}.stat span{font-size:11.5px;line-height:1.25;display:block}}
"""

JS = """
(()=>{const g=document.getElementById('grid');if(!g)return;
const cards=[...g.querySelectorAll('.card')],q=document.getElementById('q'),s=document.getElementById('sort'),
chips=[...document.querySelectorAll('.chip')],cnt=document.getElementById('count'),empty=document.getElementById('empty');
let store='all';
const rel=t=>{const m=(Date.now()-new Date(t))/6e4;if(m<60)return'há '+Math.max(1,Math.round(m))+' min';
const h=m/60;if(h<24)return'há '+Math.round(h)+' h';const d=Math.round(h/24);return'há '+d+(d>1?' dias':' dia')};
cards.forEach(c=>{const t=c.querySelector('time');t.textContent=rel(c.dataset.ts)});
const norm=x=>x.normalize('NFD').replace(/[\\u0300-\\u036f]/g,'').toLowerCase();
function apply(){const term=norm(q.value.trim());let n=0;
const t2=term.replace(/\\s+/g,'');cards.forEach(c=>{const d=norm(c.dataset.q);const ok=(store==='all'||c.dataset.store===store)&&(!term||d.includes(term)||d.replace(/\\s+/g,'').includes(t2));c.hidden=!ok;if(ok)n++});
const k=s.value,by={recent:(a,b)=>b.dataset.ts.localeCompare(a.dataset.ts),drop:(a,b)=>b.dataset.drop-a.dataset.drop||b.dataset.ts.localeCompare(a.dataset.ts),price:(a,b)=>a.dataset.price-b.dataset.price}[k];
cards.sort(by).forEach(c=>g.appendChild(c));
cnt.textContent=n+(n===1?' oferta':' ofertas');empty.hidden=n>0}
chips.forEach(b=>b.addEventListener('click',()=>{store=b.dataset.store;chips.forEach(x=>x.setAttribute('aria-pressed',x===b));apply()}));
q.addEventListener('input',apply);s.addEventListener('change',apply);apply()})();
"""

TG_ICON = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21.9 4.3 18.6 19.8c-.2 1.1-.9 1.4-1.8.9'
           'l-5-3.7-2.4 2.3c-.3.3-.5.5-1 .5l.4-5.1 9.2-8.3c.4-.4-.1-.6-.6-.2L6 13.4l-4.9-1.5c-1.1-.3-1.1-1.1.2'
           '-1.6L20.5 2.9c.9-.3 1.7.2 1.4 1.4z"/></svg>')


def render(rows: list[dict], stats: dict, name: str, channel: str, meta: str,
           site_url: str, now: datetime) -> str:
    ch = channel.lstrip("@")
    tg = os.environ.get("SITE_TG_LINK") or (f"https://t.me/{ch}" if ch else "")   # link rastreado da campanha "site"
    tg_btn = (f'<a class="btn btn-tg" href="{e(tg, quote=True)}" target="_blank" rel="noopener">{TG_ICON}'
              f'<span>Entrar no canal</span></a>') if tg else ""

    stores: dict[str, list] = {}
    for r in rows:
        key, label, _, _ = store_of(r["source"], r["shop"])
        stores.setdefault(key, [label, 0])[1] += 1
    chips = [f'<button class="chip" data-store="all" aria-pressed="true">Todas<span class="n">{len(rows)}</span></button>']
    for key, (label, n) in sorted(stores.items(), key=lambda kv: -kv[1][1]):
        chips.append(f'<button class="chip" data-store="{e(key, quote=True)}" aria-pressed="false">'
                     f'{e(label)}<span class="n">{n}</span></button>')

    cards = "".join(card(r, now) for r in rows)
    canonical = f'<link rel="canonical" href="{e(site_url, quote=True)}">' if site_url else ""
    og_img = f"{site_url.rstrip('/')}/og.png" if site_url else "og.png"
    desc = (f"{name} monitora milhares de produtos em lojas online e mostra só quedas reais de preço, "
            "comparadas ao histórico de cada produto.")
    ld = json.dumps({"@context": "https://schema.org", "@type": "WebSite", "name": name,
                     "url": site_url or None, "description": desc}, ensure_ascii=False).replace("</", "<\\/")
    fmt = lambda n: f"{n:,}".replace(",", ".")
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{e(name)} · Ofertas com queda real de preço</title>
<meta name="description" content="{e(desc)}">
{canonical}
<meta name="theme-color" content="#FF5A1F">
<meta property="og:type" content="website"><meta property="og:title" content="{e(name)} · Ofertas com queda real de preço">
<meta property="og:description" content="{e(desc)}"><meta property="og:image" content="{e(og_img, quote=True)}">
<meta property="og:locale" content="pt_BR"><meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="favicon.png" type="image/png"><link rel="apple-touch-icon" href="logo-192.png">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
{meta}
<script type="application/ld+json">{ld}</script>
<style>{CSS}</style></head><body>
<header class="top"><div class="wrap">
<a class="brand" href="./"><img src="logo-192.png" alt="" width="34" height="34"><span>{e(name.split()[0])}<small>{e(" ".join(name.split()[1:]).upper())}</small></span></a>
<nav class="nav" aria-label="Principal"><a href="#ofertas">Ofertas</a><a href="#como-funciona">Como funciona</a>{tg_btn}</nav>
</div></header>
<main>
<section class="hero"><div class="wrap">
<h1>Só <em>queda real</em> de preço. Nada de desconto inflado.</h1>
<p>Acompanhamos o preço de cada produto todos os dias e só mostramos a oferta quando ele fica abaixo do
valor típico ou chega ao menor preço já registrado.</p>
<div class="stats">
<div class="stat"><b>{fmt(stats["monitored"])}</b><span>produtos monitorados</span></div>
<div class="stat"><b>{fmt(stats["stores"])}</b><span>lojas acompanhadas</span></div>
<div class="stat"><b>{fmt(stats["posts24"])}</b><span>ofertas nas últimas 24h</span></div>
</div></div></section>
<div class="toolbar" id="ofertas"><div class="wrap">
<label class="search"><span class="sr" hidden>Buscar</span>
<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
<input id="q" type="search" placeholder="Buscar produto (ex.: air fryer, SSD, fone)" autocomplete="off" aria-label="Buscar produto"></label>
<label class="sort"><select id="sort" aria-label="Ordenar">
<option value="recent">Mais recentes</option><option value="drop">Maior queda</option><option value="price">Menor preço</option>
</select></label>
<div class="chips" role="group" aria-label="Filtrar por loja">{''.join(chips)}</div>
</div></div>
<div class="wrap">
<p class="count" id="count" aria-live="polite">{len(rows)} ofertas</p>
<div class="grid" id="grid">{cards}</div>
<p class="empty" id="empty" {"hidden" if rows else ""}>{"Nenhuma oferta encontrada com esses filtros." if rows else "As primeiras ofertas aparecem aqui em breve."}</p>
</div>
<section class="how" id="como-funciona"><div class="wrap">
<h2>Como funciona</h2>
<div class="steps">
<div class="step"><i>1</i><h3>Monitoramos os preços</h3><p>Produtos da Shopee e do Mercado Livre têm o preço registrado várias vezes por dia.</p></div>
<div class="step"><i>2</i><h3>Comparamos com o histórico</h3><p>O desconto "de/por" das lojas costuma ser inflado. Por isso usamos o preço típico de cada produto nos últimos 30 dias.</p></div>
<div class="step"><i>3</i><h3>Avisamos só o que vale</h3><p>A oferta só aparece quando o preço cai de verdade ou atinge o menor valor registrado.</p></div>
</div>
<div class="band"><div><h2>Receba as ofertas na hora</h2><p>As quedas de preço chegam primeiro no nosso canal do Telegram.</p></div>{tg_btn}</div>
</div></section>
</main>
<footer><div class="wrap">
<p>Atualizado em {now:%d/%m/%Y às %H:%M}. Os links são de afiliado: podemos receber uma comissão pelas compras,
sem custo extra para você. Preços e estoque mudam a qualquer momento; confira o valor na loja antes de comprar.</p>
<p>© {now:%Y} {e(name)} · feito com <a href="https://github.com/{e(os.environ.get("REPO", "gabrielrobeerto45-cmyk/radar-ofertas"), quote=True)}">Radar de Ofertas</a></p>
</div></footer>
<script>{JS}</script>
</body></html>"""


def fetch(db: DB, limit: int = 80) -> list[dict]:
    cur = db.conn.execute("""
        WITH last AS (
          SELECT DISTINCT ON (p.source, p.item_id)
                 p.source, p.item_id, p.price, p.reason, p.posted_at,
                 COALESCE(p.url, pr.url) AS url, pr.title, pr.image_url, pr.shop
          FROM posts p JOIN products pr ON pr.source = p.source AND pr.item_id = p.item_id
          WHERE p.message_id IS NOT NULL AND p.posted_at > now() - interval '7 days'
          ORDER BY p.source, p.item_id, p.posted_at DESC)
        SELECT l.*, t.typical, s.series
        FROM last l
        LEFT JOIN LATERAL (
          SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY d.p) AS typical
          FROM (SELECT min(x.price) AS p FROM prices x
                WHERE x.source = l.source AND x.item_id = l.item_id
                  AND x.seen_at < date_trunc('day', l.posted_at)
                  AND x.seen_at > l.posted_at - interval '30 days'
                GROUP BY date_trunc('day', x.seen_at)) d) t ON true
        LEFT JOIN LATERAL (
          SELECT array_agg(q.p ORDER BY q.day) AS series
          FROM (SELECT date_trunc('day', x.seen_at) AS day, min(x.price) AS p FROM prices x
                WHERE x.source = l.source AND x.item_id = l.item_id
                  AND x.seen_at > now() - interval '30 days'
                GROUP BY 1) q) s ON true
        ORDER BY l.posted_at DESC LIMIT %s""", (limit,))
    cols = [c.name for c in cur.description]
    out = []
    for row in cur.fetchall():
        r = dict(zip(cols, row))
        r["typical"] = float(r["typical"]) if r["typical"] is not None else None
        out.append(r)
    return out


def fetch_stats(db: DB) -> dict:
    q = db.conn.execute
    monitored = q("SELECT count(*) FROM products WHERE last_seen > now() - interval '2 days'").fetchone()[0]
    shops = q("SELECT DISTINCT source, shop FROM products WHERE last_seen > now() - interval '2 days'").fetchall()
    stores = len({store_of(s, sh)[0] for s, sh in shops})
    posts24 = q("SELECT count(*) FROM posts WHERE message_id IS NOT NULL "
                "AND posted_at > now() - interval '24 hours'").fetchone()[0]
    return {"monitored": monitored, "stores": stores, "posts24": posts24}


def copy_static(out: Path):
    if STATIC.is_dir():
        for f in STATIC.iterdir():
            if f.is_file():
                shutil.copyfile(f, out / f.name)


def build(db: DB, out: Path) -> int:
    rows = fetch(db)
    page = render(rows, fetch_stats(db), os.environ.get("SITE_NAME", "Radar de Ofertas"),
                  os.environ.get("CHANNEL_USERNAME", ""), os.environ.get("SITE_META", ""),
                  os.environ.get("SITE_URL", ""), datetime.now(TZ))
    tmp = out / "index.html.tmp"
    tmp.write_text(page, encoding="utf-8")
    tmp.replace(out / "index.html")
    return len(rows)


def main():
    logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    db = DB(env("DATABASE_URL"))
    out = Path(os.environ.get("SITE_DIR", "/site"))
    out.mkdir(parents=True, exist_ok=True)
    copy_static(out)
    every = int(os.environ.get("SITE_REFRESH_S", "300"))
    while True:
        try:
            n = build(db, out)
            log.info("Site gerado: %d ofertas", n)
        except Exception:
            log.exception("Falha ao gerar site")
        time.sleep(every)


if __name__ == "__main__":
    main()
