# OMapMaker — monorepo

Sloučené z `omapmaker-backend` a `omapmaker-frontend`, historie commitů obou repozitářů zachována.

## Struktura
- `backend/` — FastAPI backend (nasazeno na Railway)
- `frontend/` — React frontend (nasazeno na Vercel)

## Nasazení po přechodu na monorepo
V Railway i Vercel je potřeba nastavit **Root Directory**:
- Railway → Project Settings → Root Directory → `backend`
- Vercel → Project Settings → General → Root Directory → `frontend`

Obě platformy pak dál sledují stejný GitHub repozitář, jen jinou podsložku.
