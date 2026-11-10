from dataclasses import dataclass


@dataclass
class Offer:
    source: str            # "shopee", "fake", ...
    item_id: str
    title: str
    price: float           # preço atual (R$)
    original_price: float | None
    image_url: str | None
    url: str               # link JÁ com afiliado
    rating: float | None = None
    sales: int | None = None
    shop: str | None = None
    commission_rate: float | None = None  # 0.08 = 8%

    @property
    def discount_pct(self) -> float:
        if not self.original_price or self.original_price <= self.price:
            return 0.0
        return round((1 - self.price / self.original_price) * 100, 1)


@dataclass
class PriceStats:
    n: int                  # nº de dias com preço na janela (sem contar hoje)
    min_price: float | None
    median_price: float | None


@dataclass
class LastPost:
    price: float
    hours_ago: float
