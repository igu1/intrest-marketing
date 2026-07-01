# SamShar Project — ShopPulse

ShopPulse is a Django ecommerce platform that fuses a customer-facing storefront with a real-time intent-scoring engine and a Telegram-driven marketing dashboard. Every interaction a visitor makes on the storefront — clicks, CTA taps, scroll depth, dwell time, gallery views, section visibility — is captured, weighted, decayed, and aggregated into a per-visitor, per-product score. Identified visitors (those arriving via a Telegram link carrying `?ref=<chat_id>`) can then be re-engaged from the dashboard with personalized product cards or bulk campaigns.

The repository is a single Django project, `shoppulse`, containing two apps:

- `ecommerce` — public storefront, session cart, visitor tracking, scoring engine.
- `dashboard` — internal analytics, bulk Telegram campaigns, single-product outreach.

The project ships with both a Docker Compose setup (PostgreSQL) and a SQLite fallback for local hacking.

## Table of contents

1. [Architecture](#architecture)
2. [Quick start](#quick-start)
3. [Configuration](#configuration)
4. [Data model](#data-model)
5. [The scoring engine](#the-scoring-engine)
6. [Tracking pipeline (frontend → backend)](#tracking-pipeline-frontend--backend)
7. [Visitor identification loop](#visitor-identification-loop)
8. [Session cart](#session-cart)
9. [The dashboard](#the-dashboard)
10. [Telegram integration](#telegram-integration)
11. [URL reference](#url-reference)
12. [Template inventory](#template-inventory)
13. [Operational notes](#operational-notes)
14. [Security checklist](#security-checklist)

## Architecture

```
                    ┌─────────────────────────────────────────────────────────┐
                    │                       Browser                           │
                    │                                                         │
                    │  base.html (header / cart-count / category nav)        │
                    │  ├─ IntersectionObserver  →  POST /api/track/  section  │
                    │  ├─ scroll listener       →  POST /api/track/  depth    │
                    │  ├─ setInterval(20s)      →  POST /api/dwell/           │
                    │  └─ click handlers        →  POST /api/track/  cta/...  │
                    │                                                         │
                    │  PDP / cart / home JS    →  POST /api/cart/{add,…}      │
                    └────────────┬────────────────────────────────────────────┘
                                 │ JSON, X-CSRFToken
                                 ▼
   ┌────────────────────────────────────────────────────────────────────────┐
   │                       Django (shoppulse)                               │
   │                                                                        │
   │   ecommerce.views  ──►  scoring.record_event  ──►  TrackingEvent       │
   │                              │                       (append-only)      │
   │                              └─►  scoring._update_score  ──► ProductScore│
   │                                       (base × multiplier × decay)     │
   │                                                                        │
   │   ecommerce.context_processors  →  cart_count, categories (every page)│
   │                                                                        │
   │   dashboard.views  ──►  TelegramService  ──►  api.telegram.org          │
   │   dashboard.views  ──►  inject_ref_param  →  rewrites outbound URLs    │
   └────────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
              ┌──────────────────────────────┐
              │   SQLite (dev) / Postgres    │
              │   (Docker)                    │
              └──────────────────────────────┘
```

### Apps and routing

| Path prefix    | App         | Purpose                                                |
|----------------|-------------|--------------------------------------------------------|
| `/`            | `ecommerce` | Storefront, product pages, cart, per-visitor analytics |
| `/dashboard/`  | `dashboard` | Internal admin-style views, campaigns, aggregate analytics |
| `/admin/`      | Django      | Built-in admin                                         |
| `/media/`, `/static/` | —   | Served only when `DEBUG=True`                          |

### File layout

```
.
├── manage.py
├── requirements.txt          # Django 4.2, python-telegram-bot, openpyxl, …
├── Dockerfile                # gunicorn entrypoint
├── docker-compose.yml        # web (runserver) + db (postgres 15)
├── .env                      # secrets — never commit
├── shoppulse/                # project package
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py / asgi.py
│   └── …
├── ecommerce/                # storefront + scoring
│   ├── models.py
│   ├── scoring.py            # the core engine
│   ├── views.py
│   ├── urls.py
│   ├── admin.py
│   ├── context_processors.py # cart_count + categories
│   ├── management/commands/seed_data.py
│   ├── migrations/
│   └── templates/ecommerce/
│       ├── base.html         # global layout + tracking JS
│       ├── home.html
│       ├── product_list.html
│       ├── product_detail.html
│       ├── cart.html
│       └── analytics.html    # public per-visitor analytics
└── dashboard/                # internal
    ├── models.py
    ├── views.py
    ├── services.py           # TelegramService
    ├── urls.py
    ├── admin.py
    └── templates/dashboard/
        ├── base.html
        ├── index.html
        ├── bulk_message.html
        └── analytics.html    # global analytics
```

## Quick start

### Option A — local venv with SQLite

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env .env.local  # then edit .env.local with your real values
python manage.py migrate
python manage.py seed_data
python manage.py runserver
```

### Option B — Docker Compose with PostgreSQL

```bash
docker compose up --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py seed_data
```

Visit:

- Storefront: <http://localhost:8000/>
- Per-visitor analytics: <http://localhost:8000/analytics/>
- Internal dashboard: <http://localhost:8000/dashboard/>
- Django admin: <http://localhost:8000/admin/>

## Configuration

All runtime config flows through environment variables (loaded by `python-dotenv` in `shoppulse/settings.py`).

| Variable             | Required | Default                          | Notes                                                              |
|----------------------|----------|----------------------------------|--------------------------------------------------------------------|
| `SECRET_KEY`         | yes (prod) | insecure dev fallback           | Rotate before deploying.                                           |
| `DEBUG`              | no       | `True`                           | Set to `False` in production.                                      |
| `ALLOWED_HOSTS`      | no       | `localhost,127.0.0.1`            | Comma-separated.                                                   |
| `TELEGRAM_BOT_TOKEN` | yes for messaging | empty string             | Get one from [@BotFather](https://t.me/BotFather).                 |
| `DB_NAME`            | no       | `shoppulse`                      | Used only when the DB switch activates (see below).                |
| `DB_USER`            | no       | `postgres`                       |                                                                    |
| `DB_PASSWORD`        | no       | `postgres`                       |                                                                    |
| `DB_HOST`            | no       | unset                            | See DB switch note.                                               |
| `DB_PORT`            | no       | `5432`                           |                                                                    |

### Database switch (a subtle gotcha)

`shoppulse/settings.py` defaults to SQLite. It only switches to PostgreSQL when `DB_HOST` is set to something other than the empty string or the literal `"db"`:

```python
if os.getenv("DB_HOST") and os.getenv("DB_HOST") not in ("db", ""):
    DATABASES["default"] = { "ENGINE": "django.db.backends.postgresql", … }
```

In `docker-compose.yml` the `web` service sets `DB_HOST=db` via `.env`, which matches the exception and *keeps SQLite active* — Compose's Postgres container ends up unused. If you want Postgres locally, set `DB_HOST=localhost` in `.env` (and make sure the Postgres port is published).

## Data model

Defined in `ecommerce/models.py` and `dashboard/models.py`. Cardinalities:

```
Category 1───* Product 1───* TrackingEvent *───1 Visitor
                          ╲
                           *───1 PageView
                          ╱
Product *───* ProductScore *───1 Visitor
```

### `ecommerce.Category`

| Field | Type | Notes |
|-------|------|-------|
| `name` | `CharField(100)` | Display name. |
| `slug` | `SlugField(unique=True)` | URL key. |
| `icon` | `CharField(50, blank=True)` | Free-form icon hint, e.g. `"laptop"`. |

`ordering = ["name"]`, `verbose_name_plural = "categories"`.

### `ecommerce.Product`

| Field | Type | Notes |
|-------|------|-------|
| `name` | `CharField(255)` | |
| `slug` | `SlugField(unique=True)` | |
| `category` | `FK(Category, CASCADE)` | `related_name="products"` |
| `description` | `TextField` | Truncated to 300 chars in Telegram captions. |
| `price` | `DecimalField(10, 2)` | |
| `original_price` | `DecimalField(10, 2, null)` | Drives `discount_percent`. |
| `image` | `ImageField(upload_to="products/", blank=True)` | |
| `gallery` | `JSONField(default=list, blank=True)` | Additional image refs. |
| `is_featured` | `BooleanField(default=False)` | |
| `cta_text` | `CharField(50, default="Shop Now")` | |
| `created_at` | `DateTimeField(auto_now_add=True)` | |

`discount_percent` is a derived `@property`:

```python
@property
def discount_percent(self):
    if self.original_price and self.original_price > self.price:
        return int((1 - self.price / self.original_price) * 100)
    return 0
```

### `ecommerce.Visitor`

One row per browser session, keyed by `session_id` (a UUID v4 minted in `_get_visitor` if absent). Holds `chat_id` and `username` once the visitor is identified through `?ref=<chat_id>` or a Telegram campaign.

| Field | Type | Notes |
|-------|------|-------|
| `session_id` | `CharField(100, unique=True)` | |
| `chat_id` | `CharField(255, blank=True)` | Populated by `_capture_ref` and `_get_visitor`. |
| `username` | `CharField(255, blank=True)` | Mirrored from `dashboard.IdentifiedUser`. |
| `ip_address` | `GenericIPAddressField(null=True)` | Currently not populated. |
| `user_agent` | `TextField(blank=True)` | Currently not populated. |
| `first_seen`, `last_seen` | `DateTimeField` | |

### `ecommerce.PageView`

| Field | Type | Notes |
|-------|------|-------|
| `visitor` | `FK(Visitor, CASCADE, related_name="page_views")` | |
| `product` | `FK(Product, CASCADE, null=True, related_name="page_views")` | Null for non-product pages. |
| `url` | `CharField(500)` | `request.get_full_path()`. |
| `entered_at` | `DateTimeField(auto_now_add=True)` | |
| `dwell_time` | `PositiveIntegerField(default=0)` | Updated by `/api/dwell/`. |

### `ecommerce.TrackingEvent`

Append-only event log. Event types are enumerated in `EVENT_TYPES`:

| `event_type`        | Default `EVENT_SCORES` weight | Triggered by                                                |
|---------------------|------------------------------:|-------------------------------------------------------------|
| `cta_click`         | 7                             | `addToCart`, `toggleWishlist`, etc.                         |
| `product_click`     | 5                             | PDP visit (`product_detail` view).                          |
| `dwell_time`        | 4                             | Frontend `setInterval` (every 20 s if tab is active).       |
| `section_view`      | 2                             | `IntersectionObserver` on `[data-section]` elements.       |
| `gallery_interaction` | 1                           | `changeImage()` thumbnail click on PDP.                     |
| `scroll_depth`      | 1 per threshold               | `scroll` listener hitting 25/50/75/100% (each, once).       |
| `negative_signal`   | -1                            | Not currently emitted by templates, but reservable.         |

Other fields: `product` (nullable FK), `value` (`FloatField`), `metadata` (`JSONField`).

### `ecommerce.ProductScore`

The single most important table for recommendations and lead temperature.

| Field | Type | Notes |
|-------|------|-------|
| `product` | `FK(Product, CASCADE, related_name="scores")` | |
| `visitor` | `FK(Visitor, CASCADE, related_name="product_scores")` | |
| `base_score` | `FloatField(default=0)` | Sum of weighted events for this pair. |
| `multiplier` | `FloatField(default=1.0)` | `min(1.0 + (visit_count-1) * 0.1, 1.5)`. |
| `final_score` | `FloatField(default=0)` | `base_score * multiplier`, decayed. |
| `visit_count` | `PositiveIntegerField(default=0)` | Number of recorded events for the pair. |
| `last_interaction` | `DateTimeField(auto_now=True)` | Used by `_apply_decay`. |

`unique_together = ("product", "visitor")` and `ordering = ["-final_score"]`.

### `dashboard.IdentifiedUser`

A Telegram user known to the system, keyed by `chat_id`. Created automatically when a recipient appears in a bulk-send sheet or when a visitor arrives with `?ref=`.

### `dashboard.BulkCampaign` and `dashboard.MessageRecipient`

A `BulkCampaign` is created once per `send-bulk` call. It has a name, message text, optional image, and a status (`draft` → `sending` → `completed` or `failed`). `total_sent` and `total_failed` are aggregate counters.

Each recipient becomes a `MessageRecipient` row, with its own `status` (`pending` / `sent` / `failed`) and an `error_message` blob (truncated to 500 chars).

## The scoring engine

`ecommerce/scoring.py` is a self-contained module — no Django model migrations, just pure Python over the existing tables.

### Event weights

```python
EVENT_SCORES = {
    "cta_click":           7,
    "product_click":       5,
    "dwell_time":          4,
    "section_view":        2,
    "gallery_interaction": 1,
    "negative_signal":    -1,
}
```

### `record_event(visitor, event_type, product=None, value=0, metadata=None)`

1. Persists a `TrackingEvent` row.
2. If a product is associated, calls `_update_score(visitor, product, event_type, value)`.

### `_update_score(visitor, product, event_type, value=0)`

1. `get_or_create` the matching `ProductScore` row.
2. Look up `points = EVENT_SCORES.get(event_type, 0)`.
3. For `scroll_depth`, look at all prior `scroll_depth` events for this `(visitor, product)` pair and only award `SCROLL_SCORE_PER_THRESHOLD = 1` point if this threshold hasn't been crossed before.
4. `score_obj.base_score += points`
5. `score_obj.visit_count += 1`
6. `score_obj.multiplier = min(1.0 + (visit_count - 1) * 0.1, MULTIPLIER_CAP=1.5)`
7. `score_obj.final_score = base_score * multiplier`
8. `_apply_decay(score_obj)` then save.

### `_apply_decay(score_obj)`

```python
def _apply_decay(score_obj):
    now = timezone.now()
    hours_since = (now - score_obj.last_interaction).total_seconds() / 3600
    days_old = hours_since / 24
    if days_old > 0:
        score_obj.final_score = score_obj.final_score * (DECAY_RATE ** days_old)
```

With `DECAY_RATE = 0.9`, a day-old score is multiplied by `0.9`, two days by `0.81`, etc. The decay is applied to whatever `final_score` was *before* the save, using `last_interaction` from the previous save. This means repeated interactions within the same day see no decay; a single day of inactivity starts trimming the score.

### Lead temperature bands

```python
def get_lead_temperature(score):
    if score >= 40: return "Ready to Buy", "#10b981"
    if score >= 26: return "Hot",            "#f59e0b"
    if score >= 11: return "Warm",           "#3b82f6"
    return            "Cold",              "#94a3b8"
```

These labels and colors are reused on the public analytics page, on the PDP (`lead-badge`), and in the dashboard per-user summary.

### `get_dashboard_analytics()`

A single big aggregator that powers the dashboard. It returns a dict with:

- **Totals**: `total_visitors`, `identified_visitors`, `total_events`, `total_page_views`, `cta_clicks`, `product_clicks`, `total_dwell_seconds`, `avg_dwell_seconds`, `scroll_events`, `gallery_events`.
- **Top-10 leaderboards**:
  - `top_clicked` — most `product_click` events per product.
  - `top_cta` — most `cta_click` events per product.
  - `top_dwell` — products with the largest `SUM(value)` of `dwell_time`, with `avg_seconds` and `sessions`.
  - `top_scrolled` — products with the highest `MAX(value)` of `scroll_depth`, plus event counts.
  - `top_scored` — products with the largest `SUM(final_score)` across visitors, plus unique-visitor count.
- **`user_engagement`** — top-50 rows of `(visitor, product)` for identified visitors (those with a non-empty `chat_id`), joined with username/chat_id/score/visits.
- **`per_user_summary`** — per identified visitor: event count, CTA clicks, product clicks, total dwell, top score and temperature. Sorted by `top_score` desc.
- **`event_breakdown`** — counts per event type, formatted for bar charts.

The dashboard view enriches `per_user_summary` further with the top-scoring product for each user (id, slug, name, price, image URL, category) so the operator sees "what this person is most interested in" inline with their temperature.

## Tracking pipeline (frontend → backend)

The whole tracking surface is driven by a single `<script>` block in `ecommerce/templates/ecommerce/base.html` (lines 758–871). All endpoints are called with `fetch()` and the `csrftoken` cookie.

### `trackEvent(eventType, productId, value, metadata)`

`POST /api/track/`

```json
{
  "event_type": "cta_click",
  "product_id": 12,        // or null
  "value": 0,
  "metadata": { "cta": "add_to_cart" }
}
```

Response (when a `product_id` is present):

```json
{
  "ok": true,
  "event_id": 4711,
  "score": {
    "base": 12.0,
    "multiplier": 1.1,
    "final": 13.2,
    "visits": 3,
    "temperature": "Warm"
  }
}
```

### Dwell updates

`POST /api/dwell/` every 20 s while the tab is visible:

```json
{ "product_id": 12, "seconds": 42 }
```

Server side, a `dwell_time` event is only recorded if `seconds >= 20`. The most recent `PageView` for the `(visitor, product)` pair gets its `dwell_time` field overwritten with the latest figure. The `setInterval` is gated on `document.visibilityState` (the script resets `dwellStartTime` whenever the tab becomes visible again).

### Scroll depth

The scroll handler computes `scrollPercent = Math.round(scrollTop / (scrollHeight - innerHeight) * 100)`. For each threshold in `[25, 50, 75, 100]`, it emits a `scroll_depth` event the first time it's crossed. A local `Set` (`awardedScrolls`) prevents duplicate posts, and the server side also de-dupes via `_scroll_points_already_awarded`.

### Section view

`IntersectionObserver` watches every `[data-section]` element. When 30% of one enters the viewport, a `section_view` event fires with `{ section: <data-section value> }` and the observer unhooks that element. The home page uses this for `data-section="recommendations"`, `data-section="featured"`, `data-section="categories"`.

### Product-context binding

Product page templates set `<body data-product-id="…">`. The JS reads `document.body.dataset.productId` and attaches it to every event payload, so a single template file can drive both global (`section_view`, `scroll_depth`) and product-specific (`gallery_interaction`, `cta_click`) events.

## Visitor identification loop

This is the only piece of glue between the storefront and Telegram, and it's the reason the dashboard can answer "what is this Telegram user looking at right now?":

1. `dashboard.services.inject_ref_param(text, chat_id)` scans outgoing Telegram text for `http(s)://…` URLs and rewrites each to include `?ref=<chat_id>`.
2. The recipient clicks the link and lands on `/products/<slug>/?ref=123456789`.
3. `ecommerce.views._capture_ref` reads `ref` from the query string, stores it in `request.session["chat_id"]`, and `get_or_create`s an `IdentifiedUser` with that chat id.
4. `_get_visitor` (called by every storefront view) reads the session, mints a UUID `visitor_id` if absent, calls `get_or_create_visitor`, and propagates `chat_id` + `username` from `IdentifiedUser` onto the `Visitor` row.
5. From this point on, every `TrackingEvent` and `ProductScore` is associated with an identified `Visitor.chat_id`, which `get_dashboard_analytics` can join to `IdentifiedUser.username`.

Because step 3 happens at the very first view, the identification is immediate — the user doesn't need to fill out a form or run a specific command. The tradeoff is that anyone who shares a Telegram-referred link to a friend will attribute that friend's browsing to the original recipient.

## Session cart

`request.session["cart"]` holds a JSON-friendly dict:

```python
{
    "12": { "quantity": 2 },
    "37": { "quantity": 1 }
}
```

There is **no `auth.User` involved** — the cart is bound to the Django session cookie. Adding, updating, and removing all mark `request.session.modified = True` so the cookie refreshes.

`ecommerce.context_processors.global_context` exposes `cart_count` and `categories` to every template, so the header cart badge updates on any page.

## The dashboard

### `/dashboard/` (index)

Campaigns list and aggregate counters (`total_campaigns`, `total_sent`, `total_failed`).

### `/dashboard/bulk-message/`

Form for composing a message, attaching an optional image, and uploading a `.xlsx`/`.xls` sheet with at minimum these three columns (row 1 is the header):

| name        | chat_id        | message (optional override)         |
|-------------|----------------|--------------------------------------|
| Jane Doe    | 123456789      | Custom text — `{name}` is replaced.  |
| John Roe    | 987654321      |                                      |

`POST /dashboard/send-bulk/` parses the sheet with `openpyxl`, creates a `BulkCampaign` and a `MessageRecipient` per row, upserts `IdentifiedUser`s, and dispatches via `TelegramService`. The default message body is used unless a per-recipient override is provided; in both cases `{name}` is replaced with the recipient's name.

Side panel "Quick Test" form posts to `POST /dashboard/test-message/` to send one-off messages.

### `/dashboard/analytics/`

A multi-section page built on `get_dashboard_analytics()`:

1. Six "mini-stat" cards (total visitors, identified visitors, total events, total page views, CTA clicks, product clicks).
2. Two side-by-side panels: "Top Clicked Products" and "Top CTA-Engaged Products" (horizontal bar charts, scaled against the leader).
3. Two more: "Top Dwelled Products" (total seconds, gradient bars) and "Top Scrolled Products" (% scale).
4. "Top Scored Products" — a table with total score and unique visitor count, plus a teal bar.
5. "Per-User Summary" — one card per identified visitor, with their lead temperature, top-scoring product, and a "Send Image" button that hits `POST /dashboard/send-product-image/` to dispatch a rich product card to a chosen `chat_id`.
6. "User Engagement" — top-50 `(user, product)` rows with score and visits.

### `POST /dashboard/send-product-image/`

A targeted re-engagement action. The server builds a caption from the chosen product (name, category, price, original price + discount, truncated description) and a link `http://127.0.0.1:8000/products/<slug>/?ref=<chat_id>` — note this is hard-coded to `127.0.0.1:8000`; for production you should derive the base URL from `request.build_absolute_uri()` or a settings variable.

If the product has an image, the server uses `send_photo`; otherwise it falls back to `send_message`. Both go through `TelegramService`, so every link in the caption is also rewritten with `?ref=`.

## Telegram integration

`dashboard/services.py` is a thin wrapper around the Bot HTTP API. The only requirement outside Django is `requests` (already in `requirements.txt`).

### `TelegramService(token=None)`

If `token` is omitted, the service falls back to `settings.TELEGRAM_BOT_TOKEN`, which itself reads `os.getenv("TELEGRAM_BOT_TOKEN")`. There is no built-in polling/webhook hook — the bot is used purely as an outbound messaging channel.

### `inject_ref_param(text, chat_id)`

This is the linchpin of the attribution loop. It runs as the first step of `send_message`, `send_photo`, and `send_message_with_image`. The regex `r'(https?://[^\s<>"\']+)'` matches every URL in the body, and each one is parsed with `urlparse`/`parse_qs`. A `ref` query parameter is added (or overwritten) with the chat id, then re-encoded and spliced back. Schemes other than `http`/`https` are passed through unchanged.

### Methods

- **`send_message(chat_id, text, parse_mode="HTML")`** — `POST /bot{token}/sendMessage` with `chat_id`, `text`, `parse_mode`. Returns `{"ok": True, "result": …}` or `{"ok": False, "error": <string>}`.
- **`send_photo(chat_id, photo, caption="", parse_mode="HTML")`** — `POST /bot{token}/sendPhoto`. If `photo` is a file-like object, it's uploaded as `multipart/form-data` with `image/jpeg` content type; if it's a string, it's sent as a `photo` field. The Telegram API can return HTTP 200 with `{"ok": false, "description": "…"}` — the wrapper detects this and returns `{"ok": False, "error": <description>}`.
- **`send_message_with_image(chat_id, text, image_url=None, image_file=None)`** — sugar: dispatches to `send_photo` if either image argument is present, else `send_message`.
- **`send_bulk_messages(recipients, text, image_url=None, image_file=None)`** — iterates a list of `{"name", "chat_id"}` dicts, applies `{name}` substitution, and dispatches. Returns a result dict with `sent`, `failed`, and `errors`. The dashboard's `send_bulk_message` view doesn't use this — it has its own loop with per-recipient DB updates.

## URL reference

### Storefront (`ecommerce/urls.py`)

| URL                          | Name              | Method | Purpose                                                                    |
|------------------------------|-------------------|--------|----------------------------------------------------------------------------|
| `/`                          | `home`            | GET    | Featured products, categories, visitor-specific recommendations.           |
| `/products/`                 | `product_list`    | GET    | Catalog. Query params: `category=<slug>`, `q=<search>`, `sort=price_low|price_high|name`. |
| `/products/<slug>/`          | `product_detail`  | GET    | PDP. Records a `product_click`; renders lead temperature badge.            |
| `/api/track/`                | `track_event`     | POST   | Generic tracking intake (see above).                                       |
| `/api/dwell/`                | `update_dwell`    | POST   | Records a `dwell_time` event (≥ 20 s) and updates `PageView.dwell_time`.   |
| `/analytics/`                | `analytics`       | GET    | Per-visitor analytics: lead temperature, top product, recommendations.    |
| `/cart/`                     | `cart`            | GET    | Renders the session cart.                                                  |
| `/api/cart/add/`             | `api_cart_add`    | POST   | Adds to cart, returns new `count`. Also emits `cta_click` for the event.  |
| `/api/cart/update/`          | `api_cart_update` | POST   | Sets quantity (`0` removes).                                               |
| `/api/cart/remove/`          | `api_cart_remove` | POST   | Removes a product.                                                         |

### Dashboard (`dashboard/urls.py`, mounted at `/dashboard/`)

| URL                                  | Name                  | Method | Purpose                                                  |
|--------------------------------------|-----------------------|--------|----------------------------------------------------------|
| `/dashboard/`                        | `home`                | GET    | Campaign list and counters.                              |
| `/dashboard/bulk-message/`           | `bulk_message`        | GET    | Bulk-send form.                                          |
| `/dashboard/analytics/`              | `analytics`           | GET    | Aggregate analytics + per-user top-product.              |
| `/dashboard/send-bulk/`              | `send_bulk`           | POST   | Parse XLSX, create campaign, dispatch via Telegram.      |
| `/dashboard/test-message/`           | `test_message`        | POST   | One-off test message.                                    |
| `/dashboard/send-product-image/`     | `send_product_image`  | POST   | Send a single product card to a chat.                    |

## Template inventory

### `ecommerce/templates/ecommerce/`

| File | Purpose | Notable blocks |
|------|---------|----------------|
| `base.html` | Global layout: header (search + categories + cart badge), footer, tracking JS. | `{% block body %}`, `{% block extra_js %}` |
| `home.html` | Banner, recommended section (`data-section="recommendations"`), featured (`data-section="featured"`), categories. | inherits `base.html` |
| `product_list.html` | Search + sort dropdown, category sidebar, product grid. | inherits `base.html` |
| `product_detail.html` | Image gallery (with `changeImage()` → `gallery_interaction`), lead badge, buy box, tabs (Description / Specs / Reviews), related products. Sets `<body data-product-id="…">`. | inherits `base.html`, defines `extra_js` for `changeImage` / `switchTab` / `addToCartWithQty` |
| `cart.html` | Cart line items with inline quantity edit, JS calling `api_cart_update` and `api_cart_remove`. | inherits `base.html` |
| `analytics.html` | Lead temperature, top product card with a "Send Image" form calling `send-product-image/`, top products table, recommendations grid. | inherits `base.html` |

### `dashboard/templates/dashboard/`

| File | Purpose |
|------|---------|
| `base.html` | Internal layout: top nav (Dashboard / Bulk Message / Analytics), content area. |
| `index.html` | KPI cards (campaigns, sent, failed) and a recent campaigns table. |
| `bulk_message.html` | Compose form (message, image, sheet) and Quick Test side panel. JS posts to `send-bulk` and `test-message`. |
| `analytics.html` | Six mini-stat cards, four top-N bar charts, top-scored table, per-user summary cards, user-engagement table. |

## Operational notes

- **Bulk send is synchronous.** `send_bulk_message` runs the dispatch loop inside the HTTP request. For more than ~50 recipients you'll start hitting gunicorn's `timeout` (default 30 s) and Telegram's per-second rate limits. Move the loop to Celery, RQ, or a `threading.Thread` and return a campaign id immediately.
- **Per-recipient errors truncate to 500 chars** to keep the DB row bounded. The campaign-level counters are updated only once, at the end.
- **`send-product-image` uses a hard-coded `127.0.0.1:8000` base URL** in the caption. This is fine for local testing but must be parameterized (e.g. `request.build_absolute_uri("/")` or a `SITE_URL` env var) before production.
- **Templates reference `fas` (Font Awesome)** in many places. Make sure the FA CDN is reachable, or add it to the static files.
- **`Product.gallery` is a JSONField with no validation.** Whatever is in the database is what the template gets. If you start using it, decide on a shape (URL strings? objects?) and validate on save.
- **`/media/` is bind-mounted via a named Docker volume** (`media_volume`) so uploaded images survive container restarts. `db.sqlite3` and `staticfiles/` are *not* mounted — they live in the container filesystem and are lost on rebuild. For persistent local dev, prefer the venv path.
- **Seed data lives in `ecommerce/management/commands/seed_data.py`** and creates 5 categories + 8 products with hard-coded slugs. Re-running is idempotent for categories and products (`get_or_create` keyed on slug), but the products' `id` will keep incrementing for the same slug after a `delete`.

## Security checklist

- **`.env` must not be committed.** It's in `.gitignore` and should stay there. The repository's `.env` currently contains what look like real `TELEGRAM_BOT_TOKEN` and `SECRET_KEY` values; before pushing or sharing:
  1. Revoke the bot token with [@BotFather](https://t.me/BotFather) (`/revoke`) and re-issue a new one.
  2. Generate a fresh `SECRET_KEY` (`python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`).
  3. Add a `.env.example` with placeholder values, and make sure `.env` stays ignored.
- **`ALLOWED_HOSTS` defaults to `localhost,127.0.0.1`.** Set the real hostname in production.
- **`DEBUG=True` by default.** Must be `False` in production (the `.env` shipped with the repo sets it to `True`).
- **CSRF is enforced on all POSTs.** The frontend reads the `csrftoken` cookie and sends it as `X-CSRFToken`. If you call these endpoints from outside a browser, you need a session cookie + a CSRF token from `{% csrf_token %}`.
- **`csrf_exempt` is imported but unused.** If you add it to a view (e.g. for a public webhook), make sure you've thought through authentication.
- **No user auth.** Cart, checkout, and order history are not implemented. The "Buy Now" button is a no-op.
- **No rate limiting on `/api/track/`.** A malicious client could inflate scores. In production, put the project behind a rate limiter (nginx, Cloudflare, or a Django middleware).
- **The Telegram bot has no allowlist.** Anyone who knows your token can read or write to it. Restrict the bot's commands and treat the token as a high-privilege secret.
- **Image uploads are not validated for size or content type beyond Django's defaults.** A malicious user could upload huge images to `ImageField`s on `Product`, `BulkCampaign`, or the `image` form field. Configure `DATA_UPLOAD_MAX_MEMORY_SIZE`, `FILE_UPLOAD_MAX_MEMORY_SIZE`, and consider adding `python-magic` for content-type sniffing.

## Development tips

- `python manage.py shell` is the fastest way to inspect scoring state:
  ```python
  from ecommerce.models import Visitor, ProductScore
  Visitor.objects.exclude(chat_id="").values("chat_id", "username")
  ProductScore.objects.order_by("-final_score")[:10]
  ```
- To exercise the full loop end-to-end without Telegram:
  1. `python manage.py createsuperuser` and log into `/admin/`.
  2. Visit `/`, click a few products, scroll the page, switch gallery images.
  3. Watch the network panel — `POST /api/track/` should fire 4–5 times.
  4. Visit `/analytics/` to see your score and recommended products.
  5. Open `/dashboard/analytics/` in another tab; you should see anonymous traffic (no `chat_id`) reflected in the totals, and identified traffic after you visit `/?ref=<some_id>`.
- The score's volatility is by design: it rewards *multiple distinct signals* (clicks, scroll, dwell, sections) over a single high-weight action. To tune, adjust `EVENT_SCORES` and `MULTIPLIER_CAP` in `ecommerce/scoring.py`.
