# Voice Wellness Scan Backend (Python FastAPI)

Python FastAPI backend for Vocera voice wellness analysis.

## Deploy to Render

1. Push the `voice-fastapi-app/` folder to its own GitHub repo (or push the whole monorepo and set `rootDir: voice-fastapi-app` — already configured in `render.yaml`).
2. In Render, click **New → Blueprint** and point to the repo. Render will read `render.yaml` and provision the service.
   - Or **New → Web Service** manually:
     - Runtime: Python 3.11
     - Build: `pip install -r requirements.txt`
     - Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`
     - Health check: `/healthz`
3. (Optional) Set `ALLOWED_ORIGINS` to your Lovable domain (comma-separated) instead of `*` for tighter CORS.
4. Copy the resulting URL (e.g. `https://vocera-voice-api.onrender.com`) and set it as `VITE_API_BASE_URL` in Lovable.

## Endpoints

- `GET /healthz` — health check
- `POST /api/analyze-voice` — main v3 analysis endpoint (raw WAV body)
- `POST /api/analyze` — legacy v2 blended endpoint

## Environment variables

| Var | Default | Purpose |
|-----|---------|---------|
| `PORT` | `8000` | Bound by Render automatically |
| `ALLOWED_ORIGINS` | `*` | Comma-separated origins for CORS |
| `DEBUG` | `False` | Enables verbose logging when `True` |

## Notes on Render free tier

- Free instances sleep after 15 min idle → first request after sleep takes ~30 s.
- In-memory baselines reset on every restart/sleep. For production use a Starter plan or persist baselines to a database.

## Prerequisites

- Python 3.9 or higher
- `pip`

## Installation

1. Navigate to the `backend` directory:
   ```bash
   cd backend
   ```

2. Create a virtual environment (optional but recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Running the Server

Start the FastAPI server:
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

The API will be available at `http://localhost:8000/api/analyze`.

## Integration with Frontend

Since the frontend uses relative paths (e.g., `fetch("/api/analyze")`), you have two options to use this Python backend:

### Option 1: Proxy in Vite (Recommended for Development)

Update your `vite.config.ts` (if your config allows it) or your environment to proxy requests from port 5173 to 8000.

### Option 2: Absolute URL in Frontend

If you are allowed to make a minor change to the frontend, update the `fetch` call in `src/routes/scan.tsx`:

```typescript
// From:
const res = await fetch("/api/analyze", { ... });

// To:
const res = await fetch("http://localhost:8000/api/analyze", { ... });
```

*Note: The FastAPI backend already includes CORS support to allow requests from any origin.*

## Parity Notes

- **F0 Tracking**: Uses the same autocorrelation-based approach with identical voicing thresholds (0.3) and frequency bounds (70Hz - 400Hz).
- **Spectral Centroid**: Uses the same DFT-based calculation (skipping the DC component) with a Hann window.
- **Speech Rate**: Replicates the energy envelope smoothing and peak-picking logic exactly.
- **Scoring**: Replicates the `lerp`, `clamp`, and scoring formulas to ensure identical wellness outputs.
