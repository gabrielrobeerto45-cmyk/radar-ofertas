import psycopg

from .models import LastPost, Offer, PriceStats

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    source     text NOT NULL,
    item_id    text NOT NULL,
    title      text,
    image_url  text,
    url        text,
    shop       text,
    first_seen timestamptz NOT NULL DEFAULT now(),
    last_seen  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source, item_id)
);
CREATE TABLE IF NOT EXISTS prices (
    id       bigserial PRIMARY KEY,
    source   text NOT NULL,
    item_id  text NOT NULL,
    price    numeric(12,2) NOT NULL,
    seen_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS prices_item_time ON prices (source, item_id, seen_at);
CREATE TABLE IF NOT EXISTS posts (
    id         bigserial PRIMARY KEY,
    source     text NOT NULL,
    item_id    text NOT NULL,
    price      numeric(12,2) NOT NULL,
    reason     text,
    chat_id    text,
    message_id bigint,
    posted_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS posts_item_time ON posts (source, item_id, posted_at);
ALTER TABLE posts ADD COLUMN IF NOT EXISTS url text;
"""


class DB:
    def __init__(self, url: str, window_days: int = 30):
        self.conn = psycopg.connect(url, autocommit=True)
        self.conn.execute("SET TIME ZONE 'America/Sao_Paulo'")
        self.window_days = window_days

    def migrate(self):
        self.conn.execute(SCHEMA)

    def stats(self, o: Offer) -> PriceStats:
        row = self.conn.execute("""
            WITH d AS (
              SELECT date_trunc('day', seen_at) AS day, min(price) AS p
              FROM prices
              WHERE source = %s AND item_id = %s
                AND seen_at > now() - make_interval(days => %s)
                AND seen_at < date_trunc('day', now())
              GROUP BY 1)
            SELECT count(*), min(p),
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY p)
            FROM d""", (o.source, o.item_id, self.window_days)).fetchone()
        n, mn, med = row
        return PriceStats(n=n, min_price=float(mn) if mn is not None else None,
                          median_price=float(med) if med is not None else None)

    def last_post(self, o: Offer) -> LastPost | None:
        row = self.conn.execute("""
            SELECT price, extract(epoch FROM now() - posted_at) / 3600
            FROM posts WHERE source = %s AND item_id = %s
            ORDER BY posted_at DESC LIMIT 1""", (o.source, o.item_id)).fetchone()
        return LastPost(price=float(row[0]), hours_ago=float(row[1])) if row else None

    def record(self, o: Offer):
        with self.conn.transaction():
            self.conn.execute("""
                INSERT INTO products (source, item_id, title, image_url, url, shop)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (source, item_id) DO UPDATE SET
                  title = EXCLUDED.title, image_url = EXCLUDED.image_url,
                  url = EXCLUDED.url, shop = EXCLUDED.shop, last_seen = now()""",
                (o.source, o.item_id, o.title, o.image_url, o.url, o.shop))
            self.conn.execute(
                "INSERT INTO prices (source, item_id, price) VALUES (%s, %s, %s)",
                (o.source, o.item_id, o.price))

    def save_post(self, o: Offer, reason: str, chat_id: str, message_id: int | None):
        self.conn.execute("""
            INSERT INTO posts (source, item_id, price, reason, chat_id, message_id, url)
            VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (o.source, o.item_id, o.price, reason, chat_id, message_id, o.url))

    def posts_last_hour(self) -> int:
        return self.conn.execute(
            "SELECT count(*) FROM posts WHERE posted_at > now() - interval '1 hour'"
        ).fetchone()[0]

    def prune(self, keep_days: int = 120):
        self.conn.execute("DELETE FROM prices WHERE seen_at < now() - make_interval(days => %s)",
                          (keep_days,))
