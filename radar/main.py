import logging
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from . import config
from .db import DB
from .detector import DetectorConfig, evaluate
from .sources.fake import FakeSource
from .sources.mercadolivre import MercadoLivreSource
from .sources.shopee import ShopeeSource
from .telegram import Telegram

log = logging.getLogger("radar")
TZ = ZoneInfo("America/Sao_Paulo")


def env(name: str, default: str | None = None) -> str:
    v = os.environ.get(name, default)
    if v is None or v == "":
        raise SystemExit(f"Variável de ambiente obrigatória ausente: {name}")
    return v


def build_sources(client: httpx.Client) -> dict:
    sources = {"fake": FakeSource()}
    if os.environ.get("SHOPEE_APP_ID"):
        sources["shopee"] = ShopeeSource(
            env("SHOPEE_APP_ID"), env("SHOPEE_SECRET"),
            env("SHOPEE_ENDPOINT", "https://open-api.affiliate.shopee.com.br/graphql"), client)
    if os.environ.get("ML_CLIENT_ID") and os.environ.get("ML_CLIENT_SECRET"):
        sources["mercadolivre"] = MercadoLivreSource(
            env("ML_CLIENT_ID"), env("ML_CLIENT_SECRET"),
            os.environ.get("ML_MATT_WORD", ""), os.environ.get("ML_MATT_TOOL", ""), client)
    return sources


def in_quiet_hours(cfg: dict) -> bool:
    q = cfg.get("quiet_hours")
    if not q:
        return False
    h = datetime.now(TZ).hour
    start, end = int(q[0]), int(q[1])
    return start <= h < end if start < end else (h >= start or h < end)


def run_cycle(cfg: dict, db: DB, sources: dict, tg: Telegram, det: DetectorConfig):
    posting = cfg.get("posting", {})
    max_per_hour = int(posting.get("max_per_hour", 6))
    footer = posting.get("footer", "")
    quiet = in_quiet_hours(posting)

    candidates = []
    for s in cfg["searches"]:
        src = sources.get(s["source"])
        if not src:
            log.warning("Fonte '%s' não configurada, pulando busca %s", s["source"], s)
            continue
        try:
            offers = src.search(s)
        except RuntimeError as e:   # falha conhecida da API (ex.: Shopee "System Error" em horário de pico)
            log.warning("Busca %r falhou, tenta no próximo ciclo: %s",
                        s.get("keyword") or s.get("category"), str(e)[:120])
            continue
        except Exception:
            log.exception("Falha na busca %s", s)
            continue
        for o in offers:
            stats, last = db.stats(o), db.last_post(o)
            ok, reason = evaluate(o, stats, last, det)
            db.record(o)
            if ok:
                candidates.append((o, reason, stats.median_price))
        log.info("Busca %r: %d itens", s.get("keyword") or s.get("match_id"), len(offers))
        if s["source"] == "shopee":
            time.sleep(float(cfg.get("search_pause_s", 5)))  # a Shopee erra se chamar rápido demais

    # dedup (mesmo item pode vir de duas buscas) e melhores primeiro
    seen, unique = set(), []
    def drop(c):
        o, _, typ = c
        return (1 - o.price / typ) if typ else 0.0
    for o, r, typ in sorted(candidates, key=drop, reverse=True):
        if (o.source, o.item_id) not in seen:
            seen.add((o.source, o.item_id))
            unique.append((o, r, typ))

    if quiet and unique:
        log.info("Horário silencioso: %d ofertas não postadas", len(unique))
        return
    budget = max(0, max_per_hour - db.posts_last_hour())
    for o, reason, typ in unique[:budget]:
        try:
            msg_id = tg.post(o, reason, footer, typ)
            db.save_post(o, reason, tg.chat_id, msg_id)
            log.info("Postado: %s — %s (%s)", o.title[:60], o.price, reason)
            time.sleep(3)
        except Exception:
            log.exception("Falha ao postar %s", o.item_id)
    if len(unique) > budget:
        log.info("%d ofertas seguradas pelo limite de %d/hora", len(unique) - budget, max_per_hour)


def main():
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = config.load()
    det = DetectorConfig(**cfg.get("detector", {}))
    dry = os.environ.get("DRY_RUN", "1") == "1"

    client = httpx.Client(headers={"User-Agent": "radar-bot/1.0"})
    db = DB(env("DATABASE_URL"), int(cfg.get("window_days", 30)))
    db.migrate()
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not dry and (not token or not chat_id):
        raise SystemExit("Defina TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID ou use DRY_RUN=1")
    tg = Telegram(token, chat_id or "dry-run", client, dry_run=dry)
    sources = build_sources(client)
    interval = int(cfg.get("cycle_minutes", 10)) * 60
    log.info("Radar iniciado (dry_run=%s, fontes=%s, ciclo=%ss)", dry, list(sources), interval)

    cycles = 0
    while True:
        started = time.time()
        try:
            run_cycle(cfg, db, sources, tg, det)
        except Exception:
            log.exception("Erro no ciclo")
        cycles += 1
        if cycles % 144 == 0:
            db.prune()
        time.sleep(max(30, interval - (time.time() - started)))


if __name__ == "__main__":
    main()
