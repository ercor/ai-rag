# AI RAG Frontend

Next.js 14+ frontend for the AI RAG document Q&A system.

## Development

```bash
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Backend API base URL |

## Production

```bash
npm run build
npm start
```

Or use Docker:

```bash
docker build -t ai-rag-frontend .
docker run -p 3000:3000 -e NEXT_PUBLIC_API_URL=http://backend:8000 ai-rag-frontend
```
