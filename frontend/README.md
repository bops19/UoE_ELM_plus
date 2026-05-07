# ELM+ Frontend

Angular 21 frontend for the ELM+ AI Chat application. Built with standalone components, signals, and Angular's HTTP client. Served by the Flask backend at `/app`.

---

## Requirements

- Node.js 22 (LTS)
- npm 10+

---

## Setup

```bash
cd frontend
npm install
```

---

## Development

```bash
# Dev server at http://localhost:4200 (proxies API calls to Flask on :9595)
npm start

# Type-check without emitting
npm run type-check

# Lint
npm run lint
```

> The Angular dev server proxies `/api` requests to the Flask backend. Make sure `python run.py` is running before starting the dev server.

---

## Build

```bash
# Production build → output to ../static/ng/
npm run build
```

The Flask app serves the build output from `static/ng/browser`.

---

## Tests

```bash
# Unit tests (Vitest)
npm run test

# Unit tests with coverage report
npm run test:coverage

# End-to-end tests (Playwright)
npm run e2e

# Accessibility audit (axe-core via Playwright)
npm run e2e:a11y
```

---

## Key Directories

```
src/
├── app/
│   ├── core/               # API client (BackendApiService), interceptors
│   ├── pages/
│   │   └── shell-page/     # Main chat shell + sub-components
│   └── shared/             # Shared components and utilities
├── environments/           # Environment configs (dev / prod)
└── styles.css              # Global styles
```

---

## Environment Config

| File | Used when |
|---|---|
| `src/environments/environment.ts` | `ng serve` (development) |
| `src/environments/environment.production.ts` | `npm run build` (production) |

The API base URL and Sentry DSN are configured per environment.
