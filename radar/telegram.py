import html
import logging
import time

import httpx

from .models import Offer

log = logging.getLogger(__name__)


def brl(v: float) -> str:
    s = f"{v:,.2f}"
    return "R$ " + s.replace(",", "X").replace(".", ",").replace("X", ".")


def price_prefix(source: str) -> str:
    """No Mercado Livre o preço é o menor entre vários vendedores do mesmo produto."""
    return "a partir de " if source == "mercadolivre" else ""


def price_note(source: str, shop: str | None = None) -> str | None:
    if source == "mercadolivre":
        return "menor preço entre os vendedores"
    return None


def fmt_sales(n: int) -> str:
    return f"{n / 1000:.1f}k".replace(".0k", "k").replace(".", ",") if n >= 1000 else str(n)


def _typical_ok(o: Offer, typical: float | None) -> bool:
    return bool(typical) and typical > o.price * 1.05


def caption(o: Offer, reason: str, footer: str, typical: float | None = None) -> str:
    """`typical` = preço típico pelo histórico do próprio radar. O preço "de" da loja
    não é usado porque costuma ser inflado (ex.: "de R$ 971 por R$ 135")."""
    e = html.escape
    lines = [f"🔥 <b>{e(o.title[:180])}</b>", ""]
    note = price_note(o.source, o.shop)
    price = f"💰 {price_prefix(o.source)}<b>{brl(o.price)}</b>" + (f" <i>({e(note)})</i>" if note else "")
    if _typical_ok(o, typical):
        price += f"  <s>{brl(typical)}</s>  (-{(1 - o.price / typical) * 100:.0f}%)"
    lines.append(price)
    lines.append(f"📉 {e(reason)}")
    meta = []
    if o.rating:
        meta.append(f"⭐ {o.rating:.1f}")
    if o.sales:
        meta.append(f"{fmt_sales(o.sales)} vendidos")
    if o.shop:
        meta.append(e(o.shop))
    if meta:
        lines.append(" · ".join(meta))
    lines += ["", f'👉 <a href="{e(o.url, quote=True)}">Ver oferta</a>']
    if footer:
        lines += ["", f"<i>{e(footer)}</i>"]
    return "\n".join(lines)


class Telegram:
    def __init__(self, token: str, chat_id: str, client: httpx.Client, dry_run: bool = False):
        self.base = f"https://api.telegram.org/bot{token}"
        self.chat_id, self.http, self.dry_run = chat_id, client, dry_run

    def _call(self, method: str, data: dict) -> dict:
        for _ in range(3):
            r = self.http.post(f"{self.base}/{method}", data=data, timeout=30)
            body = r.json()
            if body.get("ok"):
                return body["result"]
            retry = body.get("parameters", {}).get("retry_after")
            if r.status_code == 429 and retry:
                log.warning("Telegram rate limit, aguardando %ss", retry)
                time.sleep(retry + 1)
                continue
            raise RuntimeError(f"Telegram {method}: {body.get('description')}")
        raise RuntimeError("Telegram: muitas tentativas")

    def post(self, o: Offer, reason: str, footer: str, typical: float | None = None) -> int | None:
        text = caption(o, reason, footer, typical)
        if self.dry_run:
            log.info("[DRY_RUN] postaria:\n%s", text)
            return None
        if o.image_url and len(text) <= 1024:
            try:
                return self._call("sendPhoto", {"chat_id": self.chat_id, "photo": o.image_url,
                                                "caption": text, "parse_mode": "HTML"})["message_id"]
            except RuntimeError as e:
                log.warning("sendPhoto falhou (%s), enviando só texto", e)
        return self._call("sendMessage", {"chat_id": self.chat_id, "text": text, "parse_mode": "HTML",
                                          "disable_web_page_preview": "true"})["message_id"]
