"""Fonte: API oficial de Afiliados da Shopee (GraphQL).

Credenciais: painel de afiliados Shopee -> Open API -> AppID e Secret.
Requer conta de afiliado aprovada e acesso à Open API liberado.
"""
import hashlib
import json
import logging
import time

import httpx

from ..models import Offer

log = logging.getLogger(__name__)

FIELDS = ("itemId productName priceMin priceMax priceDiscountRate commissionRate "
          "sales ratingStar imageUrl offerLink productLink shopName")


def sign(app_id: str, secret: str, timestamp: int, payload: str) -> str:
    raw = f"{app_id}{timestamp}{payload}{secret}"
    sig = hashlib.sha256(raw.encode()).hexdigest()
    return f"SHA256 Credential={app_id}, Timestamp={timestamp}, Signature={sig}"


def build_query(keyword: str | None, sort_type: int, page: int, limit: int,
                list_type: int | None = None, match_id: int | None = None,
                item_id: int | None = None, shop_id: int | None = None) -> str:
    args = [f"sortType: {sort_type}", f"page: {page}", f"limit: {limit}"]
    if item_id is not None:
        args.append(f"itemId: {int(item_id)}")
    if shop_id is not None:
        args.append(f"shopId: {int(shop_id)}")
    if keyword:
        args.append(f"keyword: {json.dumps(keyword, ensure_ascii=False)}")
    if list_type is not None:
        args.append(f"listType: {list_type}")
    if match_id is not None:
        args.append(f"matchId: {match_id}")
    return ("query { productOfferV2(" + ", ".join(args) + ") { nodes { " + FIELDS +
            " } pageInfo { page limit hasNextPage } } }")


def _f(v):
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def parse_node(n: dict) -> Offer | None:
    price = _f(n.get("priceMin"))
    if not price or not n.get("offerLink"):
        return None
    rate = n.get("priceDiscountRate") or 0
    original = round(price / (1 - rate / 100), 2) if 0 < rate < 100 else None
    sales = n.get("sales")
    return Offer(
        source="shopee",
        item_id=str(n["itemId"]),
        title=(n.get("productName") or "").strip(),
        price=price,
        original_price=original,
        image_url=n.get("imageUrl"),
        url=n["offerLink"],
        rating=_f(n.get("ratingStar")),
        sales=int(sales) if sales is not None else None,
        shop=n.get("shopName"),
        commission_rate=_f(n.get("commissionRate")),
    )


class ShopeeSource:
    name = "shopee"

    def __init__(self, app_id: str, secret: str, endpoint: str, client: httpx.Client):
        self.app_id, self.secret, self.endpoint, self.http = app_id, secret, endpoint, client

    def _request(self, query: str, retries: int = 3) -> dict:
        return self._graphql(query, retries)["productOfferV2"]

    def _graphql(self, query: str, retries: int = 3) -> dict:
        """Faz a chamada com nova assinatura a cada tentativa. A API às vezes
        devolve 'System Error' (10000) de forma intermitente; tenta de novo."""
        payload = json.dumps({"query": query}, ensure_ascii=False, separators=(",", ":"))
        last_err = None
        for attempt in range(retries):
            if attempt:
                time.sleep(6 * attempt)
            try:
                ts = int(time.time())
                r = self.http.post(self.endpoint, content=payload.encode(), headers={
                    "Content-Type": "application/json",
                    "Authorization": sign(self.app_id, self.secret, ts, payload),
                }, timeout=30)
                r.raise_for_status()
                body = r.json()
                if body.get("errors"):
                    raise RuntimeError(f"Shopee API: {body['errors']}")
                return body["data"]
            except (httpx.HTTPError, RuntimeError, KeyError, ValueError) as e:
                last_err = e
                log.warning("Shopee tentativa %d/%d falhou: %s", attempt + 1, retries, e)
        raise RuntimeError(f"Shopee: falhou após {retries} tentativas: {last_err}")

    def search(self, search: dict) -> list[Offer]:
        offers: list[Offer] = []
        pages = int(search.get("pages", 1))
        for page in range(1, pages + 1):
            q = build_query(search.get("keyword"), int(search.get("sort_type", 2)), page,
                            int(search.get("limit", 50)), search.get("list_type"),
                            search.get("match_id"))
            try:
                data = self._request(q)
            except RuntimeError:
                if offers:   # já temos páginas anteriores: usa o que deu
                    log.warning("Página %d falhou, usando %d itens já obtidos", page, len(offers))
                    break
                raise
            offers += [o for o in map(parse_node, data["nodes"]) if o]
            if not data["pageInfo"].get("hasNextPage"):
                break
            time.sleep(4)
        return offers
