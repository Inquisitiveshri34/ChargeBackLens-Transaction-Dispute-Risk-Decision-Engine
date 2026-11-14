# ChargebackLens web front end

Next.js (App Router, TypeScript, Tailwind). It renders four routes (`/`, `/score`, `/queue`, `/economics`) and gets every number from the FastAPI service in `../api`.

```bash
npm install
npm run dev          # http://localhost:3000, expects the API on http://127.0.0.1:8000
npm run test:e2e     # Playwright checks; starts the API and this app if they are not running
```

Set `API_URL` to point at a different API. See the repository README for the full run and deploy steps.

- `app/` — routes, global styles and design tokens (`globals.css`).
- `components/` — one file per screen, plus form fields and the hand-built SVG chart.
- `lib/api.ts` — typed API client. `lib/format.ts` — rupee, percentage and threshold formatting.
- `e2e/` — the acceptance, responsive and accessibility checks.
