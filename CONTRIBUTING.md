# Contributing

Thanks for your interest in contributing!

## Getting Started

1. Fork the repo
2. Clone your fork
3. Copy `.env.example` to `.env` and add your API keys
4. Run `docker compose up`

## Development

**Backend:**
```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload
uv run python worker.py  # separate terminal
```

**Frontend:**
```bash
cd frontend
pnpm install
pnpm dev
```

## Before Submitting

- Run tests: `cd backend && uv run pytest`
- Check linting: `cd backend && uv run ruff check .`
- Format code: `cd backend && uv run ruff format .`

## Guidelines

- Keep changes focused and minimal
- Follow existing code style
- Update docs if you change behavior
- Add tests for new features

## Questions?

Open an issue to discuss before starting large changes.

