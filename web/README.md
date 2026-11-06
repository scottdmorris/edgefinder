# Ball Knowledge web app

The React front end for Ball Knowledge (Vite, React, TypeScript, Tailwind). Every number on it
comes from the FastAPI service in `src/edgefinder/api`; this side only shows it.

```powershell
npm install
npm run dev      # hot reload at http://localhost:5173, /api passed through to port 8000
npm run build    # type-check, then build to dist/ (the API server serves it at "/")
npm run lint
```

Run the API first, from the repository root:

```powershell
.venv\Scripts\uvicorn edgefinder.api.app:app --app-dir src --port 8000
```

- `src/lib`: the typed API client, the slip (kept in this browser), polling, line ladders
- `src/components`: shared pieces (pills, the slip panel, the court, the game center)
- `src/screens`: Parlay, Live, Players, Picks, Record
