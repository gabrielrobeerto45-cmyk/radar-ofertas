"""Fonte de teste: gera ofertas falsas com preços oscilando, para testar o
fluxo completo (banco, detector, Telegram) sem credenciais de loja.
De vez em quando derruba o preço de um item para disparar uma "oferta"."""
import random

from ..models import Offer

PRODUCTS = [
    ("Fone Bluetooth TWS com cancelamento de ruído", 189.9),
    ("Air Fryer 4L Digital", 399.0),
    ("SSD NVMe 1TB", 459.0),
    ("Smartwatch tela AMOLED", 299.0),
    ("Cafeteira expresso 15 bar", 549.0),
    ("Teclado mecânico RGB", 229.0),
    ("Mouse sem fio silencioso", 79.9),
    ("Power bank 20000mAh", 139.0),
]


class FakeSource:
    name = "fake"

    def __init__(self, seed: int | None = None):
        self.rng = random.Random(seed)

    def search(self, search: dict) -> list[Offer]:
        out = []
        for i, (title, base) in enumerate(PRODUCTS):
            factor = self.rng.uniform(0.95, 1.05)
            if self.rng.random() < 0.08:
                factor = self.rng.uniform(0.55, 0.75)   # "erro de preço"
            price = round(base * factor, 2)
            out.append(Offer(
                source="fake", item_id=f"fake-{i}", title=title, price=price,
                original_price=round(base * 1.3, 2),
                image_url=f"https://picsum.photos/seed/radar{i}/600/600",
                url=f"https://example.com/produto/{i}?aff=TESTE",
                rating=4.8, sales=500, shop="Loja Teste",
            ))
        return out
