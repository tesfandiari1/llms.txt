# LLM.txt Generator Backend

FastAPI backend that generates [llms.txt](https://llmstxt.org) documentation files by crawling websites, extracting content, and summarizing with Claude.

## Architecture

```
Frontend → FastAPI → PostgreSQL
                        ↓
                    Worker (pgqueuer)
                        ↓
           Firecrawl + Anthropic Claude
```

**Stack**: FastAPI, PostgreSQL 17, pgqueuer (job queue), Firecrawl (scraping), Anthropic Claude (LLM)

## Setup

```bash
# Install dependencies
uv sync

# Copy env file and fill in keys
cp .env.example .env
```

**Required environment variables:**

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `FIRECRAWL_API_KEY` | [Firecrawl](https://firecrawl.dev) API key |
| `ANTHROPIC_API_KEY` | [Anthropic](https://anthropic.com) API key |

## Running

```bash
# Start API server (port 8000)
uv run uvicorn app.main:app --reload

# Start worker (separate terminal)
uv run python worker.py
```

Or with Docker:

```bash
docker compose up
```

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/jobs` | Create job |
| `GET` | `/api/jobs/{id}` | Get job status |
| `GET` | `/api/jobs/{id}/pages` | List discovered pages |
| `PATCH` | `/api/jobs/{id}/pages` | Update page selection |
| `POST` | `/api/jobs/{id}/generate` | Trigger generation |
| `GET` | `/api/jobs/{id}/download` | Download llms.txt |

## Job Pipeline

1. **Discover** → Firecrawl `/map` finds all pages on the site
2. **Extract** → Firecrawl `/scrape` converts each page to markdown
3. **Summarize** → Claude generates one-line summaries per page
4. **Generate** → Assemble final llms.txt and llms-ctx.txt files

## Project Structure

```
backend/
├── app/
│   ├── main.py         # FastAPI routes
│   ├── config.py       # Environment settings
│   ├── database.py     # SQLAlchemy setup
│   ├── storage.py      # File storage (local/S3)
│   ├── jobs/           # Job processing domain
│   │   ├── models.py   # Job, Page models
│   │   ├── tasks.py    # pgqueuer tasks
│   │   ├── firecrawl.py
│   │   └── generator.py
│   └── llm/
│       └── summarizer.py
├── worker.py           # pgqueuer worker entry
└── tests/
```

## Testing

```bash
uv run pytest
```

