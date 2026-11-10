# 📡 Radar de Ofertas

**Bot de afiliados para Telegram que só posta queda REAL de preço.**
Monitora produtos da **Shopee** e do **Mercado Livre**, guarda o histórico de preços
e publica no seu canal somente quando o preço cai de verdade, comparando com o
histórico, e não com o "de R$ 999 por R$ 299" inflado das lojas. Vem com um site
vitrine com gráfico de histórico de cada oferta.

<!-- Cole aqui o botão "Implantar na Hostinger" gerado no programa de parceiros -->
<!-- [![Implantar na Hostinger](BOTAO.svg)](LINK-COM-SEU-CODIGO) -->

---

## ✨ O que ele faz

- 🔎 **Monitora** as palavras-chave que você escolher na Shopee (API oficial de afiliados)
  e no Mercado Livre (mais vendidos por categoria, API oficial).
- 📉 **Detecta queda real**: posta quando o preço fica X% abaixo da mediana dos últimos
  30 dias ou atinge o menor preço já registrado.
- 🚫 **Ignora desconto falso**: o "de/por" da loja nunca é usado como critério.
- 📢 **Posta no Telegram** com foto, preço, preço típico riscado, nota, vendas e o
  **seu link de afiliado**.
- 🛡️ **Não faz spam**: limite de posts por hora, horário silencioso e sem repetir o
  mesmo produto em menos de 6h.
- 🌐 **Site vitrine** com filtros, busca, gráfico de histórico de preço e HTTPS automático.
- 💾 **Backup** do banco com um comando.

## 🧰 O que você precisa

| Item | Onde conseguir | Custo |
|---|---|---|
| VPS com Docker (2 GB de RAM já bastam) | Hostinger KVM 1/KVM 2 ou similar | a partir de ~R$ 30/mês |
| Bot do Telegram + canal | [@BotFather](https://t.me/BotFather) → `/newbot`. Depois adicione o bot como **admin** do canal. | grátis |
| API de afiliados da Shopee | affiliate.shopee.com.br → Open API (AppID e Secret) | grátis |
| App do Mercado Livre (opcional) | developers.mercadolivre.com.br → criar app com *Client Credentials* | grátis |

> Sem Shopee/ML configurados, o radar roda em **modo demonstração** com produtos
> falsos, para você ver tudo funcionando antes.

## 🚀 Instalação

### Opção 1: um clique na Hostinger
Use o botão no topo deste README e preencha as variáveis pedidas (tabela abaixo).

### Opção 2: manual (qualquer VPS com Docker)
```bash
git clone https://github.com/gabrielrobeerto45-cmyk/radar-ofertas.git
cd radar-ofertas
cp .env.example .env
nano .env                 # preencha senha do banco, Telegram, Shopee/ML e buscas
docker compose up -d
docker compose logs -f bot
```

Comece com `DRY_RUN=1`: o bot só **mostra no log** o que postaria. Quando estiver
satisfeito, troque para `DRY_RUN=0` e rode `docker compose up -d` de novo.

## ⚙️ Variáveis

| Variável | Obrigatória | Exemplo / padrão | O que é |
|---|---|---|---|
| `POSTGRES_PASSWORD` | ✅ | `openssl rand -hex 24` | Senha do banco (interno) |
| `TELEGRAM_BOT_TOKEN` | para postar | `123:ABC...` | Token do @BotFather |
| `TELEGRAM_CHAT_ID` | para postar | `@meucanal` | Canal onde postar |
| `CHANNEL_USERNAME` | | `meucanal` | Usado no botão do site |
| `DRY_RUN` | | `1` | `1` = teste, `0` = posta de verdade |
| `SHOPEE_APP_ID` / `SHOPEE_SECRET` | para Shopee | | Open API de afiliados |
| `ML_CLIENT_ID` / `ML_CLIENT_SECRET` | para ML | | App do Mercado Livre |
| `ML_MATT_WORD` / `ML_MATT_TOOL` | para ML | | Sua etiqueta de afiliado do ML (veja abaixo) |
| `SEARCHES` | | `shopee:fone bluetooth; ml:air fryer` | O que monitorar, separado por `;` |
| `CYCLE_MINUTES` | | `10` | Intervalo entre ciclos |
| `MAX_POSTS_PER_HOUR` | | `6` | Limite anti-spam |
| `QUIET_HOURS` | | `0-7` | Não posta nesse horário (vazio = sempre) |
| `DROP_PCT` | | `20` | Queda mínima vs. preço típico (%) |
| `MIN_HISTORY_DAYS` | | `2` | Dias de histórico antes de postar |
| `SITE_NAME` | | `Radar de Ofertas` | Nome no site |
| `SITE_ADDRESS` | | `:80` | Seu domínio, ex.: `meusite.com.br, www.meusite.com.br` (HTTPS automático) |
| `SITE_URL` | | `https://meusite.com.br` | Para SEO e prévia de compartilhamento |

**Etiqueta do Mercado Livre:** gere qualquer link no portal de afiliados do ML, abra
o link `meli.la/...` no navegador e copie os valores de `matt_word` e `matt_tool`
da URL final.

**Arquivo `config.yaml` (avançado):** se existir um `config.yaml` montado no
container, ele substitui as variáveis de busca e detector, o que permite buscas por
categoria e outros ajustes finos.

## 🧠 Como ele decide postar

1. **Filtros de qualidade:** nota ≥ 4,5, vendas ≥ 100 e preço entre R$ 20 e R$ 20 mil.
2. **Preço típico:** para cada produto, mediana do menor preço diário nos últimos 30 dias.
3. **Posta se:** preço ≥ `DROP_PCT`% abaixo do típico **ou** novo menor preço registrado.
4. **Sem histórico suficiente** (`MIN_HISTORY_DAYS`), não posta, porque o desconto
   anunciado pela loja não é confiável.
5. **Anti-repetição:** o mesmo produto só volta depois de 6h e se cair mais 5%.

No Mercado Livre, o preço mostrado é **"a partir de"**: o menor entre os vendedores
do produto, que é o mesmo valor listado em "Ver opções de compra" na página.

## 🛠️ Comandos úteis

```bash
docker compose logs -f bot                    # acompanhar
docker compose up -d                          # aplicar mudanças no .env
./backup.sh                                   # backup do banco em ./backups
docker compose run --rm --no-deps bot python -m pytest -q   # testes
```

## ⚠️ Avisos

- **Divulgue que os links são de afiliado.** O rodapé de cada post já faz isso; mantenha.
- Respeite os termos dos programas de afiliados. Este projeto usa **apenas APIs
  oficiais**, sem raspagem de sites.
- Preços mudam rápido. Por isso o bot reconfere a cada ciclo e avisa no post.

## 📄 Licença

MIT: use, modifique e distribua à vontade.

---

Feito por quem roda o canal **[PromoHub Brasil](https://promohubbrasil.com.br)**:
o radar completo, com alertas de preço, programa de indicação e mais lojas, está
funcionando lá. 😉
