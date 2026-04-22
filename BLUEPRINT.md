# Tauke.AI — System Blueprint (MVP)
**Domain 2: Economic Empowerment | UM Hackathon**
**Stack: FastAPI · PostgreSQL · React Native (Expo) · Z.AI GLM**

---

## Context

Malaysian F&B micro-SMEs (especially mamak stalls) operate on thin margins, paper-based receipts, and intuition-driven ordering. They lose money to spoilage, stockouts during demand surges (Hari Raya, exam period), and missed pricing opportunities during peak weather/event windows. Tauke.AI ("Boss AI" in Malay/Hokkien) gives these owners a Decision Intelligence layer: receipts are photographed → stock is tracked → the AI explains *why* it recommends a price change or re-order, not just *what* to do.

---

## 1. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                   MOBILE (React Native / Expo)                  │
│  [Camera] → [Upload Screen] → [Dashboard] → [Alerts/Recs UI]   │
└───────────────────────┬───────────────────┬─────────────────────┘
                        │ HTTPS POST        │ Expo Push Token
                        ▼                   ▼
┌──────────────── FastAPI Backend ────────────────────────────────┐
│                                                                  │
│  /api/invoices/upload  ──► [1] Store raw image (disk/S3)        │
│                         ──► [2] Build GLM multimodal request    │
│                         ──► [3] Call Z.AI GLM-4V (OCR)         │
│                         ──► [4] Validate + parse JSON response  │
│                         ──► [5] Write Invoice + LineItems → PG  │
│                         ──► [6] Update inventory_items          │
│                         ──► [7] Trigger BackgroundTask:         │
│                               ReasoningEngine.run(shop_id)      │
│                                                                  │
│  ReasoningEngine ───────────────────────────────────────────    │
│    ├─ Query inventory_items (current stock, spoilage dates)     │
│    ├─ Query sales history (30-day rolling)                      │
│    ├─ Fetch ExternalContext: weather + UM calendar + holidays   │
│    ├─ Run DemandAdjustment (multipliers)                        │
│    ├─ Run OrderQuantityOptimizer (safety stock formula)         │
│    ├─ Run PricingOptimizer (elasticity + event premium)         │
│    ├─ Run ConfidenceScorer (entropy + data volume)              │
│    ├─ Run TradeoffReasoner (ROI vs EG)                          │
│    ├─ Build GLM reasoning prompt → call Z.AI GLM-4 (text)      │
│    └─ Write AI_Recommendations → PG                             │
│                         ──► [8] Send Expo Push Notification     │
│                                                                  │
│  /api/recommendations  ──► Return rec list with reasoning_trace │
│  /api/inventory        ──► CRUD + spoilage warnings             │
│  /api/context/preview  ──► Show what external signals are active│
└──────────────────────────────────────────────────────────────────┘
                        │
                        ▼
┌──────────── PostgreSQL ─────────────────────────────────────────┐
│  users · shops · products · invoices · invoice_line_items       │
│  inventory_items · ai_recommendations · external_context_cache  │
│  recommendation_feedback                                         │
└──────────────────────────────────────────────────────────────────┘
                        │
              ┌─────────┴──────────┐
              ▼                    ▼
     Z.AI GLM-4V             External APIs
   (multimodal OCR       OpenWeatherMap (KL)
    + text reasoning)    UM Academic Calendar
                         Malaysia Public Holidays API
                         (data.gov.my or static JSON)
```

**Key design decisions:**
- BackgroundTask (FastAPI's `BackgroundTasks`) keeps the upload endpoint fast (<3s perceived latency)
- GLM is called twice per flow: once for OCR (multimodal), once for reasoning text (optional — engine can run in pure-math mode for MVP speed)
- External context is cached per `(shop_id, date)` with a 6-hour TTL to avoid rate limits

---

## 2. Database Schema

```sql
-- ============================================================
-- USERS & SHOPS
-- ============================================================
CREATE TABLE users (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email       TEXT UNIQUE NOT NULL,
    name        TEXT NOT NULL,
    phone       TEXT,
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE shops (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id        UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,                      -- e.g. "Warung Pak Lah"
    shop_type       TEXT DEFAULT 'mamak',               -- mamak | kopitiam | hawker | cafe
    location_lat    NUMERIC(9,6),
    location_lng    NUMERIC(9,6),
    city            TEXT DEFAULT 'Kuala Lumpur',
    is_halal        BOOLEAN DEFAULT TRUE,
    operating_hours JSONB,                              -- {"mon":"00:00-23:59","fri":"00:00-23:59"}
    expo_push_token TEXT,                               -- for push notifications
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- PRODUCT CATALOG (normalised master list per shop)
-- ============================================================
CREATE TABLE products (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shop_id             UUID NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
    name                TEXT NOT NULL,                  -- "Teh Tarik", "Roti Canai"
    sku                 TEXT,                           -- optional supplier SKU
    category            TEXT,                           -- beverage | bread | protein | veg | dry_goods
    unit                TEXT DEFAULT 'unit',            -- kg | litre | unit | pack
    avg_cost_price      NUMERIC(10,2),                  -- MYR, rolling avg
    avg_selling_price   NUMERIC(10,2),                  -- MYR
    spoilage_days       INTEGER DEFAULT 3,              -- shelf life in days (0 = non-perishable)
    min_stock_threshold NUMERIC(10,2) DEFAULT 0,        -- trigger alert below this
    reorder_quantity    NUMERIC(10,2),                  -- suggested order size
    demand_elasticity   NUMERIC(4,2) DEFAULT -1.2,      -- price elasticity (negative)
    created_at          TIMESTAMPTZ DEFAULT now(),
    updated_at          TIMESTAMPTZ DEFAULT now(),
    UNIQUE (shop_id, name)
);

-- ============================================================
-- INVOICES (scanned supplier receipts)
-- ============================================================
CREATE TABLE invoices (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shop_id             UUID NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
    supplier_name       TEXT,                           -- extracted by GLM
    invoice_number      TEXT,
    invoice_date        DATE,
    total_amount        NUMERIC(10,2),
    currency            CHAR(3) DEFAULT 'MYR',
    raw_image_url       TEXT NOT NULL,                  -- stored image path
    ocr_confidence      NUMERIC(4,3),                  -- 0.000–1.000
    ocr_raw_json        JSONB,                          -- full GLM extraction payload
    processing_status   TEXT DEFAULT 'pending',         -- pending | processing | done | failed | needs_review
    failure_reason      TEXT,
    created_at          TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- INVOICE LINE ITEMS
-- ============================================================
CREATE TABLE invoice_line_items (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_id          UUID NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    product_name_raw    TEXT NOT NULL,                  -- raw OCR text, e.g. "Teh 1kg"
    matched_product_id  UUID REFERENCES products(id),  -- NULL if unmatched
    quantity            NUMERIC(10,3) NOT NULL,
    unit_raw            TEXT,                           -- raw unit from receipt
    unit_price          NUMERIC(10,2),
    total_price         NUMERIC(10,2),
    ocr_confidence      NUMERIC(4,3),                  -- per-line confidence
    created_at          TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- INVENTORY (current live stock)
-- ============================================================
CREATE TABLE inventory_items (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shop_id         UUID NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
    product_id      UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    batch_ref       TEXT,                               -- links to invoice
    current_qty     NUMERIC(10,3) NOT NULL DEFAULT 0,
    unit            TEXT NOT NULL,
    cost_price      NUMERIC(10,2),                      -- this batch's cost
    purchase_date   DATE,
    expiry_date     DATE,                               -- purchase_date + spoilage_days
    is_depleted     BOOLEAN DEFAULT FALSE,
    last_updated    TIMESTAMPTZ DEFAULT now(),
    UNIQUE (shop_id, product_id, batch_ref)
);

-- ============================================================
-- EXTERNAL CONTEXT CACHE
-- ============================================================
CREATE TABLE external_context_cache (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shop_id         UUID NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
    context_type    TEXT NOT NULL,                      -- weather | public_holiday | um_calendar | event
    context_date    DATE NOT NULL,
    data_json       JSONB NOT NULL,
    fetched_at      TIMESTAMPTZ DEFAULT now(),
    expires_at      TIMESTAMPTZ,
    UNIQUE (shop_id, context_type, context_date)
);

-- ============================================================
-- AI RECOMMENDATIONS
-- ============================================================
CREATE TABLE ai_recommendations (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shop_id             UUID NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
    product_id          UUID REFERENCES products(id),
    recommendation_type TEXT NOT NULL,                  -- price_increase | price_decrease | reorder | stockout_warning | spoilage_warning
    status              TEXT DEFAULT 'active',          -- active | dismissed | acted_on | expired
    -- Computed values
    recommended_action  TEXT NOT NULL,                  -- human-readable, Malay/English
    target_quantity     NUMERIC(10,2),                  -- for reorder recs
    target_price        NUMERIC(10,2),                  -- for pricing recs
    confidence_score    NUMERIC(4,3) NOT NULL,          -- 0.000–1.000
    risk_of_inaction    NUMERIC(10,2),                  -- MYR estimated loss if ignored
    expected_gain       NUMERIC(10,2),                  -- MYR estimated gain if acted on
    -- Explainability (Decision Intelligence requirement)
    reasoning_trace     JSONB NOT NULL,                 -- step-by-step math + logic
    external_factors    JSONB,                          -- which context signals fired
    glm_explanation     TEXT,                           -- GLM's narrative explanation (Malay/English)
    -- Metadata
    feedback_rating     INTEGER CHECK (feedback_rating BETWEEN 1 AND 5),
    feedback_note       TEXT,
    created_at          TIMESTAMPTZ DEFAULT now(),
    expires_at          TIMESTAMPTZ
);

-- ============================================================
-- INDEXES
-- ============================================================
CREATE INDEX idx_inventory_shop_product ON inventory_items(shop_id, product_id);
CREATE INDEX idx_invoices_shop_date ON invoices(shop_id, invoice_date);
CREATE INDEX idx_recs_shop_status ON ai_recommendations(shop_id, status, created_at DESC);
CREATE INDEX idx_context_cache_lookup ON external_context_cache(shop_id, context_type, context_date);
```

---

## 3. The Reasoning Engine — Mathematical & Logic Flow

The engine runs as a Python module `backend/engine/reasoning.py`. It is deterministic and testable independently of the GLM.

### 3.1 Demand Adjustment

```
base_demand_daily = avg(invoice_consumption_last_30_days) / 30

adjusted_demand = base_demand_daily
                × weather_multiplier(product.category, weather.condition)
                × event_multiplier(product.category, active_events)
                × dow_multiplier(product.category, today.weekday())
```

**Malaysian Weather Multipliers (OpenWeatherMap, KL grid):**

| Condition      | Beverage (hot) | Beverage (cold) | Food (comfort) | Dry goods |
|---------------|---------------|----------------|---------------|-----------|
| Heavy rain    | 1.40          | 0.70           | 1.25          | 1.00      |
| Hot/sunny     | 0.85          | 1.55           | 0.90          | 1.00      |
| Normal        | 1.00          | 1.00           | 1.00          | 1.00      |

**Malaysian Event Multipliers:**

| Event                      | Overall demand | Notes                                     |
|---------------------------|---------------|-------------------------------------------|
| UM Exam Week              | 0.65          | Students leave Petaling Jaya/Bangsar area  |
| UM Orientation Week       | 1.40          | New intake, peak mamak traffic            |
| Hari Raya Eve / Day 1–2   | 0.20 (dapur)  | Mamaks closed OR at home; dry goods +2.0  |
| Hari Raya Day 3–14        | 1.60          | Post-celebration dining surge             |
| Chinese New Year Day 1–2  | 0.30          | Many closures                             |
| Public holiday (generic)  | 1.35          | Mamak stays open, captures overflow       |
| Weekday (Mon–Thu)         | 1.00          | Baseline                                  |
| Friday/Saturday           | 1.25          | Weekend surge                             |

### 3.2 Target Order Quantity

```
demand_during_lead_time = adjusted_demand × lead_time_days

σ_demand = stdev(daily_consumption_last_30_days)  # default 0.15 × base if <7 data points

safety_stock = Z_SCORE × σ_demand × sqrt(lead_time_days)
  # Z_SCORE = 1.65 (95% service level) for perishables
  # Z_SCORE = 1.28 (90%)               for dry goods

current_stock = sum(inventory_items.current_qty WHERE product_id = X AND NOT is_depleted)
spoilage_at_lead_time = qty_expiring_within(lead_time_days)
usable_stock = current_stock - spoilage_at_lead_time

target_order_qty = max(0,
    demand_during_lead_time + safety_stock - usable_stock
)
```

### 3.3 Confidence Score

```
confidence = geometric_mean([
    data_recency_score,
    data_volume_score,
    ocr_quality_score,
    context_availability_score
])
```

Where:
- `data_recency_score` = exp(-λ × days_since_last_invoice), λ=0.05 → 1.0 if today, 0.5 if 14 days ago
- `data_volume_score` = min(1.0, log(1 + n_data_points) / log(1 + 30))  # saturates at 30 days
- `ocr_quality_score` = mean(invoice_line_items.ocr_confidence) over last 5 invoices; 1.0 if manual entry
- `context_availability_score` = fraction of context signals successfully fetched (weather, calendar)

**Entropy penalty:** If demand coefficient_of_variation (σ/μ) > 0.5, multiply confidence × 0.85 (high variance = uncertain)

**Confidence thresholds:**
- ≥ 0.80 → High confidence → auto-push notification
- 0.60–0.79 → Medium → show in dashboard, no push
- < 0.60 → Low → flag for owner review, add disclaimer

### 3.4 Financial Trade-off Reasoning

**Risk of Inaction (ROI) — stockout scenario:**
```
p_stockout = 1 - Φ((usable_stock - adjusted_demand × days_to_next_restock) / σ_demand)
  # Φ = standard normal CDF

lost_revenue_per_day = adjusted_demand × product.avg_selling_price
customer_churn_penalty = lost_revenue_per_day × 0.15  # 15% churn premium for mamak loyalty

risk_of_inaction = p_stockout × (lost_revenue_per_day × days_to_next_restock + customer_churn_penalty)
```

**Expected Gain (EG) — pricing opportunity:**
```
# Demand elasticity model (arc elasticity)
demand_at_new_price = base_demand × (1 + elasticity × (Δprice / base_price))
  # where Δprice = target_price - current_price, elasticity < 0

revenue_at_new_price = demand_at_new_price × target_price
revenue_at_old_price = base_demand × current_price

expected_gain = revenue_at_new_price - revenue_at_old_price
              - ordering_cost_amortised   # fixed_order_cost / batch_size
              - holding_cost_increase     # order_qty × unit_cost × 0.02 × lead_time_days
```

**Net recommendation trigger:**
```
recommend = True  IF (expected_gain > MYR_MIN_THRESHOLD OR risk_of_inaction > MYR_MIN_THRESHOLD)
                 AND confidence >= 0.60
# MYR_MIN_THRESHOLD = 5.00 for MVP (avoids noise below RM5 impact)
```

**Reasoning trace payload (stored in `reasoning_trace` JSONB):**
```json
{
  "base_demand_daily": 12.5,
  "adjusted_demand_daily": 17.5,
  "multipliers_applied": {"weather": 1.40, "event": 1.00, "dow": 1.25},
  "safety_stock": 8.2,
  "usable_stock": 5.0,
  "target_order_qty": 30.7,
  "confidence_components": {
    "data_recency": 0.92, "data_volume": 0.78,
    "ocr_quality": 0.85, "context_availability": 1.0
  },
  "confidence_final": 0.86,
  "risk_of_inaction_myr": 47.50,
  "expected_gain_myr": 62.00,
  "decision": "REORDER",
  "context_signals_active": ["heavy_rain", "friday"]
}
```

---

## 4. GLM Prompt Strategy

### 4.1 System Prompt — Smart Ingestion (Multimodal, GLM-4V)

```
SYSTEM:
You are a Malaysian receipt digitisation specialist for small F&B businesses.
Your task is to extract structured data from photos of supplier invoices or
purchase receipts. Receipts may be:
  - Handwritten in Malay, English, Chinese, or a mix of all three
  - Poorly lit, slightly blurry, or crumpled
  - Using common Malaysian abbreviations: "kg", "pkt", "btl", "ktn", "dos"
  - Missing total lines or dates (fill with null, do not guess)

Return ONLY valid JSON matching this exact schema:
{
  "supplier_name": string | null,
  "invoice_number": string | null,
  "invoice_date": "YYYY-MM-DD" | null,
  "currency": "MYR",
  "total_amount": number | null,
  "line_items": [
    {
      "product_name_raw": string,   // exact text as written
      "quantity": number,
      "unit": string,               // standardise to: kg | litre | unit | pack | bottle | carton
      "unit_price": number | null,
      "total_price": number | null,
      "confidence": number          // 0.0–1.0, your confidence for this line
    }
  ],
  "overall_confidence": number,     // 0.0–1.0 for entire extraction
  "warnings": [string]              // list any ambiguities
}

CRITICAL RULES:
1. Never hallucinate numbers. If a value is unclear, set it to null and add a warning.
2. Do not correct or "fix" product names — preserve the raw OCR text exactly.
3. If overall_confidence < 0.5, set the first warning to "LOW_CONFIDENCE_NEEDS_REVIEW".
4. Validate: sum(line_items.total_price) should approximately equal total_amount (±5%).
   If discrepancy > 5%, add warning "TOTAL_MISMATCH".
```

### 4.2 System Prompt — Dynamic Pricing & Order Optimizer (Text, GLM-4)

```
SYSTEM:
You are Tauke.AI, a trusted business advisor for Malaysian F&B micro-SMEs.
You speak like a knowledgeable friend — mix Malay and English naturally (Manglish is fine).
Your job is to EXPLAIN a pre-computed recommendation in plain language that a mamak
stall owner can understand WITHOUT a finance degree.

You will receive a JSON object with the recommendation's mathematical trace.
Your explanation must:
1. State what to do in ONE clear sentence (the "headline")
2. Explain WHY in 2–3 sentences using the context signals (weather, events, stock level)
3. Show the money impact: "If you do nothing, you risk losing ~RMXX. If you act, you could gain ~RMXX."
4. Give a confidence statement: "Saya yakin XX% sebab..." (I am XX% confident because...)
5. End with a concrete next step: "Recommended: Order XX unit dari supplier sebelum hari Jumaat."

TONE RULES:
- Never be alarmist. Frame as opportunity, not threat.
- If confidence < 0.65, add: "Nota: Data terhad, semak semula sebelum buat keputusan."
- Keep total explanation under 120 words.
- Use MYR for all currency references.

OUTPUT FORMAT: { "headline", "explanation", "money_impact", "confidence_statement", "next_step" }
```

---

## 5. API Endpoint Map

| Method | Path                                    | Purpose                                           |
|--------|-----------------------------------------|---------------------------------------------------|
| POST   | `/api/invoices/upload`                  | Upload image → trigger OCR + Reasoning Engine     |
| GET    | `/api/invoices/{id}`                    | Get invoice with line items and OCR status        |
| GET    | `/api/inventory`                        | List all inventory items with spoilage warnings   |
| PATCH  | `/api/inventory/{id}`                   | Manual stock adjustment                           |
| GET    | `/api/recommendations`                  | Active recs with full reasoning trace             |
| PATCH  | `/api/recommendations/{id}/feedback`    | Owner rates recommendation (1–5 stars)            |
| GET    | `/api/context/preview`                  | Show today's active external signals              |
| POST   | `/api/shops`                            | Register shop                                     |
| GET    | `/api/products`                         | Product catalog for shop                          |

---

## 6. QA & Testing Boundaries

### 6.1 GLM Hallucination Guards

| Guard                | Implementation                                                                   |
|---------------------|----------------------------------------------------------------------------------|
| Numeric validation  | Python: assert `abs(sum(line totals) - invoice_total) / invoice_total < 0.05`   |
| Confidence floor    | `ocr_confidence < 0.5` → `needs_review` status, no inventory update             |
| Low-res detection   | Check image resolution; warn if < 300px on shortest dimension                    |
| Schema validation   | Pydantic `OCRResponse` validates every field before DB write                     |
| Math-first          | Reasoning Engine computes all numbers in Python; GLM only writes explanation     |
| GLM timeout         | 10s timeout on reasoning call; fallback to template explanation                  |

### 6.2 Key Test Cases

**Ingestion:** clear receipt ≥0.90 confidence · blurry → `needs_review` · handwritten Malay · bilingual Chinese/English · total mismatch → warning

**Engine:** <7 days data → confidence ≤0.65 · heavy rain Friday → multiplier 1.75 · exam week 0.65 · zero stock → `p_stockout=1.0` · near-expiry batch reduces usable stock

**API:** valid upload → 202 + rec within 5s · non-image → 422 · no-data shop → empty list

---

## 7. Project Directory Structure

```
tauke-ai/
├── backend/
│   ├── main.py
│   ├── database.py
│   ├── models/          (user, shop, product, invoice, inventory, recommendation, context_cache)
│   ├── schemas/         (invoice OCRResponse, inventory, recommendation with reasoning_trace)
│   ├── routers/         (invoices, inventory, recommendations, context)
│   ├── engine/
│   │   ├── reasoning.py         # Core math
│   │   ├── context_fetcher.py   # Weather + calendar
│   │   └── multipliers.py       # Malaysian multiplier tables
│   ├── services/
│   │   ├── glm_client.py
│   │   ├── ocr_service.py
│   │   ├── inventory_service.py
│   │   └── notification.py
│   ├── alembic/
│   └── tests/           (test_ocr, test_engine, test_api)
├── mobile/
│   ├── app/(tabs)/      (index dashboard, scan camera, recommendations)
│   ├── components/      (RecommendationCard, InventoryBadge)
│   └── services/api.ts
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

---

## 8. Implementation Sequence

| Step | Area                | Deliverable                                        |
|------|---------------------|----------------------------------------------------|
| 1    | Database            | Alembic migrations for all 8 tables                |
| 2    | GLM Ingestion       | `ocr_service.py` + Pydantic validation             |
| 3    | Invoice API         | `POST /api/invoices/upload` end-to-end             |
| 4    | Reasoning Engine    | Pure-math module + full test suite                 |
| 5    | GLM Narration       | Manglish explanation overlay                       |
| 6    | Context Fetcher     | Weather + UM calendar + holidays                   |
| 7    | Recommendations API | `GET /api/recommendations` with trace              |
| 8    | Mobile App          | Camera → Dashboard → Rec cards                    |
| 9    | Push Notifications  | Expo push for high-confidence recs                 |
| 10   | Demo Polish         | Seed data, demo shop, presentation screenshots     |

---

## 9. Branch Ownership

| Branch              | Scope                                                       |
|--------------------|-------------------------------------------------------------|
| `feature/backend`  | Steps 1–3, 5–7: FastAPI, DB, GLM services, Reasoning API   |
| `feature/engine`   | Step 4: `backend/engine/` math module + all tests          |
| `feature/frontend` | Steps 8–9: React Native Expo app + push notifications      |

---

## 10. Verification Checklist

- [ ] Photo mamak receipt → JSON ≥ 0.75 confidence
- [ ] OCR triggers `inventory_items` row in PG
- [ ] Heavy rain context → teh tarik order qty higher than sunny baseline
- [ ] UM Exam Week → lower order qty recommendation
- [ ] `reasoning_trace` JSON has all 10 fields (§3.4)
- [ ] GLM explanation in Manglish, < 120 words, cites active signals
- [ ] Blurry image → `needs_review`, no inventory side-effects
- [ ] Confidence < 0.60 → disclaimer in GLM explanation
- [ ] Star rating feedback persists to DB
- [ ] Expo push notification received on device for high-confidence rec
