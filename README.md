# Tauke.AI 🧠🍜

> **"Boss AI"** — A Decision Intelligence platform for Malaysian F&B micro-SMEs

Built for **UM Hackathon Domain 2: Economic Empowerment**

---

## What is Tauke.AI?

Malaysian mamak stalls and F&B micro-SMEs operate on thin margins, paper receipts, and gut instinct. They lose money to spoilage, stockouts during demand surges, and missed pricing opportunities.

**Tauke.AI** gives these owners a smart AI advisor in their pocket:
- 📸 **Photograph a supplier receipt** → AI extracts and digitises it automatically
- 📦 **Stock is tracked in real-time** → spoilage warnings included
- 🧠 **AI explains *why* it recommends** a price change or reorder — not just *what* to do
- 📲 **Push notifications** for high-confidence recommendations

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI (Python) |
| Database | PostgreSQL + Alembic |
| Mobile | React Native (Expo) |
| AI / OCR | Z.AI GLM-4V (multimodal) + GLM-4 (text reasoning) |
| External APIs | OpenWeatherMap, UM Academic Calendar, Malaysia Public Holidays |
| Infrastructure | Docker Compose |

---

## Key Features

### 🔍 Smart Receipt Ingestion
- Photographs of supplier invoices (handwritten Malay, English, Chinese, or mixed) are processed by GLM-4V
- Extracts line items, quantities, prices, and supplier details
- Flags low-confidence extractions for manual review instead of silently writing bad data

### 📊 Reasoning Engine
A fully deterministic Python engine that computes recommendations using:
- **Demand adjustment** — weather multipliers, Malaysian event calendar (Hari Raya, UM exam week, public holidays), day-of-week patterns
- **Safety stock formula** — statistical reorder quantities with service-level targets
- **Price elasticity model** — arc elasticity pricing with event premiums
- **Confidence scoring** — geometric mean of data recency, volume, OCR quality, and context availability

### 🗣️ Manglish Explanations
GLM-4 narrates each recommendation in natural Manglish (Malay + English mix) that a mamak owner can understand without a finance degree — citing the exact context signals that triggered it.

### 💡 Full Explainability
Every recommendation stores a `reasoning_trace` JSON with all intermediate math — demand multipliers applied, safety stock calculation, confidence components, expected gain vs risk of inaction in MYR.

---

## Project Structure

```
tauke-ai/
├── backend/
│   ├── engine/          # Core reasoning math (deterministic, testable)
│   ├── routers/         # FastAPI endpoints
│   ├── services/        # GLM client, OCR, inventory, notifications
│   └── models/          # SQLAlchemy models (8 tables)
├── mobile/
│   ├── app/(tabs)/      # Dashboard, camera scan, recommendations
│   └── components/      # RecommendationCard, InventoryBadge
└── docker-compose.yml
```

---

## API Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/invoices/upload` | Upload receipt → triggers OCR + AI reasoning |
| GET | `/api/recommendations` | Get active recommendations with reasoning trace |
| GET | `/api/inventory` | Live stock with spoilage warnings |
| GET | `/api/context/preview` | Today's active external signals (weather, events) |
| PATCH | `/api/recommendations/{id}/feedback` | Owner rates recommendation 1–5 stars |

---

## Malaysian Context Intelligence

The reasoning engine is calibrated for Malaysian F&B realities:

- **Heavy rain** → hot beverage demand +40%, cold beverage -30%
- **UM Exam Week** → overall demand -35% (students leave area)
- **Hari Raya Day 3–14** → demand surge +60%
- **Friday/Saturday** → baseline +25%

---

## Built By

[Ooi Yong Zhe](https://github.com/oyz13085) — Year 1 CS (AI), Universiti Malaya
