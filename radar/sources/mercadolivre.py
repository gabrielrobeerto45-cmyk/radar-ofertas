"""Fonte: Mercado Livre (API oficial, token de aplicativo via client_credentials).

A busca comum (/sites/MLB/search) é bloqueada pelo ML mesmo com token, então
usamos o ranking de MAIS VENDIDOS por categoria (/highlights) e o preço de cada
produto de catálogo vem da lista de vendedores (/products/{id}/items).

Config de busca (config.yaml):
  - { source: mercadolivre, keyword: "air fryer" }   # descobre a categoria sozinho
  - { source: mercadolivre, category: "MLB1051" }    # ou categoria direta

Link de afiliado: o ML não tem API para gerar meli.la, então acrescentamos os
parâmetros do seu link (matt_word / matt_tool) à página do produto.
"""
import logging
import time
from urllib.parse import urlencode

import httpx

from ..models import Offer

log = logging.getLogger(__name__)
API = "https://api.mercadolibre.com"


class MercadoLivreSource:
    name = "mercadolivre"

    def __init__(self, client_id: str, client_secret: str, matt_word: str, matt_tool: str,
                 client: httpx.Client, pause: float = 0.25):
        self.client_id, self.client_secret = client_id, client_secret
        self.matt = {"matt_word": matt_word, "matt_tool": matt_tool} if matt_word else {}
        self.http, self.pause = client, pause
        self._token, self._token_exp = None, 0.0
        self._category_cache: dict[str, str] = {}
        self._details: dict[str, tuple[float, str, str | None]] = {}  # id -> (ts, nome, foto)

    # ---------- infraestrutura ----------
    def _auth(self) -> str:
        if self._token and time.time() < self._token_exp - 300:
            return self._token
        r = self.http.post(f"{API}/oauth/token", data={
            "grant_type": "client_credentials",
            "client_id": self.client_id, "client_secret": self.client_secret}, timeout=30)
        r.raise_for_status()
        d = r.json()
        self._token, self._token_exp = d["access_token"], time.time() + int(d.get("expires_in", 21600))
        log.info("Token do Mercado Livre renovado")
        return self._token

    def _get(self, path: str, params: dict | None = None):
        for attempt in range(3):
            time.sleep(self.pause if not attempt else 3 * attempt)
            r = self.http.get(f"{API}{path}", params=params, timeout=30,
                              headers={"Authorization": f"Bearer {self._auth()}"})
            if r.status_code == 401:
                self._token = None
                continue
            if r.status_code in (429, 500, 502, 503, 504):
                log.warning("ML %s em %s, tentando de novo", r.status_code, path)
                continue
            r.raise_for_status()
            return r.json()
        r.raise_for_status()
        raise RuntimeError(f"ML: falhou em {path}")

    # ---------- passos ----------
    def category_for(self, keyword: str) -> str:
        if keyword not in self._category_cache:
            res = self._get("/sites/MLB/domain_discovery/search", {"q": keyword, "limit": 1})
            if not res:
                raise RuntimeError(f"ML: nenhuma categoria para '{keyword}'")
            self._category_cache[keyword] = res[0]["category_id"]
            log.info("ML: '%s' -> categoria %s (%s)", keyword, res[0]["category_id"],
                     res[0].get("category_name"))
        return self._category_cache[keyword]

    def details(self, product_id: str) -> tuple[str, str | None]:
        cached = self._details.get(product_id)
        if cached and time.time() - cached[0] < 86400:
            return cached[1], cached[2]
        p = self._get(f"/products/{product_id}")
        pics = p.get("pictures") or []
        name, pic = p.get("name") or product_id, (pics[0].get("url") if pics else None)
        self._details[product_id] = (time.time(), name, pic)
        return name, pic

    def best_price(self, product_id: str) -> tuple[float, float | None, bool] | None:
        """MENOR preço entre os vendedores de produto novo: (preço, preço_original, frete_grátis).

        A página /p/ destaca um vendedor escolhido pelo ML (prazo, reputação...) que a API
        não informa, então o post mostra "a partir de R$ X" e o link leva à página, onde
        "Ver opções de compra" lista esse menor preço. Forçar um vendedor específico no link
        não é confiável: se o anúncio sai do ar, a página abre sem preço."""
        res = self._get(f"/products/{product_id}/items", {"limit": 20}).get("results", [])
        new = [i for i in res if i.get("condition") == "new" and i.get("price")]
        if not new:
            return None
        best = min(new, key=lambda i: i["price"])
        orig = best.get("original_price")
        return float(best["price"]), (float(orig) if orig else None), \
            bool((best.get("shipping") or {}).get("free_shipping"))

    def link(self, product_id: str) -> str:
        url = f"https://www.mercadolivre.com.br/p/{product_id}"
        return f"{url}?{urlencode(self.matt)}" if self.matt else url

    def search(self, search: dict) -> list[Offer]:
        cat = search.get("category") or self.category_for(search["keyword"])
        hl = self._get(f"/highlights/MLB/category/{cat}")
        ids = [c["id"] for c in hl.get("content", []) if c.get("type") == "PRODUCT"]
        ids = ids[: int(search.get("limit", 20))]
        offers = []
        for pid in ids:
            try:
                price = self.best_price(pid)
                if not price:
                    continue
                name, pic = self.details(pid)
                offers.append(Offer(
                    source="mercadolivre", item_id=pid, title=name, price=price[0],
                    original_price=price[1], image_url=pic, url=self.link(pid),
                    shop="Frete grátis" if price[2] else None))
            except httpx.HTTPStatusError as e:
                log.warning("ML: produto %s ignorado (%s)", pid, e.response.status_code)
        return offers
