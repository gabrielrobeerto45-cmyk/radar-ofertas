"""Configuração: arquivo config.yaml (se existir) ou variáveis de ambiente.

Variáveis de ambiente permitem instalar com um clique (sem editar arquivos):

  SEARCHES            "shopee:fone bluetooth; shopee:air fryer; ml:smartwatch"
  CYCLE_MINUTES       10
  MAX_POSTS_PER_HOUR  6
  QUIET_HOURS         "0-7"   (vazio = posta a qualquer hora)
  DROP_PCT            20      (queda mínima vs. preço típico)
  MIN_HISTORY_DAYS    2
  MIN_RATING          4.5
  MIN_SALES           100
  FOOTER              "Link de afiliado. Preço e estoque podem mudar."
"""
import os
from pathlib import Path

import yaml

DEFAULT_FOOTER = "Link de afiliado. Preço e estoque podem mudar a qualquer momento."


def _f(name: str, default: float) -> float:
    v = os.environ.get(name, "").strip()
    return float(v) if v else default


def parse_searches(spec: str) -> list[dict]:
    """'shopee:fone bluetooth; ml:smartwatch' -> lista de buscas."""
    out = []
    for part in spec.replace("\n", ";").split(";"):
        part = part.strip()
        if not part:
            continue
        src, _, kw = part.partition(":")
        src, kw = src.strip().lower(), kw.strip()
        if src in ("ml", "mercadolivre", "mercado livre") and kw:
            out.append({"source": "mercadolivre", "keyword": kw, "limit": 20})
        elif src == "shopee" and kw:
            out.append({"source": "shopee", "keyword": kw, "sort_type": 2, "pages": 2, "limit": 50})
        elif src == "fake":
            out.append({"source": "fake"})
    return out


def from_env() -> dict:
    searches = parse_searches(os.environ.get("SEARCHES", ""))
    demo = not searches
    if demo:
        searches = [{"source": "fake"}]          # sem buscas: modo demonstração
    quiet = os.environ.get("QUIET_HOURS", "0-7").strip()
    q = [int(x) for x in quiet.split("-")] if "-" in quiet else None
    return {
        "cycle_minutes": _f("CYCLE_MINUTES", 10),
        "window_days": 30,
        "searches": searches,
        "detector": {
            "min_rating": _f("MIN_RATING", 4.5),
            "min_sales": int(_f("MIN_SALES", 100)),
            "min_history": int(_f("MIN_HISTORY_DAYS", 2)),
            "drop_vs_median_pct": _f("DROP_PCT", 20),
            # nunca confia no "de/por" das lojas reais; na demonstração (produtos falsos)
            # posta já no 1º ciclo, para quem está testando ver o fluxo funcionando
            "cold_start_discount_pct": 50 if demo else 101,
        },
        "posting": {
            "max_per_hour": int(_f("MAX_POSTS_PER_HOUR", 6)),
            "quiet_hours": q,
            "footer": os.environ.get("FOOTER", DEFAULT_FOOTER),
        },
    }


def load() -> dict:
    path = Path(os.environ.get("CONFIG", "config.yaml"))
    if path.is_file():
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)
    return from_env()
