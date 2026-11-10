# Ictus — trading dashboard

Local dashboard for the Kalshi trading bot in `../model`. Start everything with
`../ictus.sh` (or `../ictus.sh live <dollars>`) from the repository root; see the root
README.

The page talks to the bot through `src/app/api/bot/[action]/route.ts`, which
runs on the local Next.js server, reads `ICTUS_TRADING_TOKEN` from
`../model/.env`, and forwards only same-origin requests from a loopback host.
The token never reaches the browser. The dev server binds to 127.0.0.1.

```bash
npm install
npm run dev     # http://localhost:3000 (the bot must be running on 127.0.0.1:8002)
```
