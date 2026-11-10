"""Decide se uma oferta é boa o bastante para ser postada.

Regras (configuráveis em config.yaml -> detector):
  1. Filtros de qualidade: nota mínima, vendas mínimas, faixa de preço.
  2. Anti-repetição: não reposta o mesmo item dentro de `repost_hours`,
     a menos que o preço tenha caído mais `repost_extra_drop_pct`.
  3a. Com histórico suficiente (>= min_history dias com preço registrado;
      cada dia conta pelo menor preço daquele dia, sem contar hoje):
      - preço X% abaixo da mediana da janela, OU
      - menor preço já visto na janela.
  3b. Sem histórico (item novo): só posta se o desconto anunciado
      for muito alto (`cold_start_discount_pct`). Desconto anunciado
      é menos confiável, por isso a régua é mais alta.
"""
from dataclasses import dataclass

from .models import LastPost, Offer, PriceStats


@dataclass
class DetectorConfig:
    min_rating: float = 4.5
    min_sales: int = 50
    min_price: float = 20.0
    max_price: float = 20000.0
    min_history: int = 3          # dias
    drop_vs_median_pct: float = 20.0
    new_low_margin_pct: float = 3.0
    cold_start_discount_pct: float = 50.0
    repost_hours: float = 72.0
    repost_extra_drop_pct: float = 5.0
    repost_min_gap_hours: float = 6.0   # nunca reposta o mesmo item em menos que isso


def evaluate(offer: Offer, stats: PriceStats, last: LastPost | None,
             cfg: DetectorConfig) -> tuple[bool, str]:
    if offer.price < cfg.min_price or offer.price > cfg.max_price:
        return False, "fora da faixa de preço"
    if offer.rating is not None and offer.rating < cfg.min_rating:
        return False, f"nota {offer.rating} < {cfg.min_rating}"
    if offer.sales is not None and offer.sales < cfg.min_sales:
        return False, f"vendas {offer.sales} < {cfg.min_sales}"

    if last and last.hours_ago < cfg.repost_min_gap_hours:
        return False, "postado há poucas horas"
    if last and last.hours_ago < cfg.repost_hours:
        if offer.price > last.price * (1 - cfg.repost_extra_drop_pct / 100):
            return False, "já postado recentemente"

    if stats.n >= cfg.min_history and stats.median_price:
        drop = (1 - offer.price / stats.median_price) * 100
        if drop >= cfg.drop_vs_median_pct:
            return True, f"{drop:.0f}% abaixo do preço típico"
        if stats.min_price and offer.price <= stats.min_price * (1 - cfg.new_low_margin_pct / 100):
            return True, "menor preço já registrado"
        return False, f"queda de {drop:.0f}% (insuficiente)"

    if offer.discount_pct >= cfg.cold_start_discount_pct:
        return True, f"{offer.discount_pct:.0f}% de desconto"
    return False, "sem histórico e desconto baixo"
