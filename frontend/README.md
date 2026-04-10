# Hero Voice AI Frontend

Production-grade React + Tailwind dashboard for real-time monitoring, analytics, learning, uploads, and hybrid-rule administration.

## Run

```bash
cd frontend
npm install
npm run dev
```

## API Integration Points

- `GET /api/stats` -> KPI cards and conversion metrics
- `GET /api/leads` -> Sales table + customer intelligence cards
- `GET /api/active-calls` -> Live active calls widget
- `GET /api/intelligence/summary` -> objections and competitor intelligence
- `GET /api/learning/status` -> learning health panel
- `POST /api/documents/upload` -> RAG document ingestion
- `POST /api/offers/upload` -> offer upload
- `POST /api/call/make` -> outbound call trigger
- `GET /api/hybrid/rules` + `PUT /api/hybrid/rules/:id` -> hybrid model control
- `WS /call/stream` -> live transcript stream
