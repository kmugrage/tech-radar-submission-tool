# Tech Radar Blip Submission Tool

An LLM-powered conversational tool that helps Thoughtworkers submit high-quality blips for the [Thoughtworks Technology Radar](https://www.thoughtworks.com/radar). The tool coaches submitters through the process, extracts structured data from the conversation, checks for duplicates against historical radar editions, and scores submission quality in real time.

## Quick Start

### Prerequisites

- Python 3.9+
- An [Anthropic API key](https://console.anthropic.com/) (or use dev mode without one)

### Setup

```bash
# Clone the repo and enter the directory
git clone <repo-url>
cd tech-radar

# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
```

### Run

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open [http://localhost:8000](http://localhost:8000) in your browser.

### Run Without an API Key (Dev Mode)

Set `DEV_MODE=true` in your `.env` file. The app will use mock responses that simulate the coaching conversation without calling the Claude API.

```bash
# .env
DEV_MODE=true
```

## How It Works

The tool runs a WebSocket-based conversation between the submitter and Claude. As the user describes the technology they want to submit, Claude:

1. **Checks for duplicates** against 33 volumes of historical radar data
2. **Extracts structured fields** incrementally from the conversation (name, ring, quadrant, description, client references, etc.)
3. **Coaches for evidence** tailored to the proposed ring — Adopt requires the most evidence, Assess the least
4. **Scores quality** in real time, shown in the sidebar

The submitter can click "Submit Blip" at any time to finalize.

## Architecture

```
┌──────────────┐  WebSocket   ┌──────────────────────┐   Claude API
│   Browser     │◄────────────►│  FastAPI (main.py)    │◄──────────────►  Anthropic
│   (app.js)    │              │                        │
│               │              │  ┌─ conversation.py    │   Tool calls:
│  ┌──────────┐ │              │  ├─ claude_client.py   │   - extract_blip_data
│  │ Chat     │ │              │  ├─ prompts.py         │   - check_radar_history
│  │ Sidebar  │ │              │  ├─ quality.py         │
│  └──────────┘ │              │  ├─ radar_history.py   │
└──────────────┘              │  └─ storage.py         │
                               └──────────────────────┘
                                        │
                                        ▼
                               data/submissions.json
                               data/radar_history/*.csv
```

### Key Components

| File | Purpose |
|------|---------|
| `app/main.py` | FastAPI app, WebSocket endpoint, session management |
| `app/claude_client.py` | Claude API calls with tool-use loop |
| `app/mock_client.py` | Mock responses for dev mode (no API key needed) |
| `app/prompts.py` | System prompt with coaching instructions |
| `app/models.py` | Pydantic models: `BlipSubmission`, `Ring`, `Quadrant` |
| `app/quality.py` | Completeness and quality scoring logic |
| `app/radar_history.py` | Loads and searches historical radar CSV data |
| `app/conversation.py` | Per-session conversation state |
| `app/storage.py` | Saves submissions to JSON |
| `static/` | Frontend: single-page app (HTML, JS, CSS) |

### Data Model

Submissions collect these fields:

| Field | Weight | Notes |
|-------|--------|-------|
| `description` | 25 | Most important — contextualize the technology |
| `why_now` | 15 | What changed to make this timely |
| `client_references` | 10 | Specific engagements (critical for Adopt/Trial) |
| `alternatives_considered` | 10 | Competing technologies evaluated |
| `name` | 10 | Technology or technique name |
| `quadrant` | 5 | Techniques, Tools, Platforms, or Languages & Frameworks |
| `ring` | 5 | Adopt, Trial, Assess, or Hold |
| `submitter_name` | 5 | Who is submitting |
| `submitter_contact` | 5 | Email or Slack handle |
| `strengths` | 5 | Key advantages |
| `weaknesses` | 5 | Known drawbacks |

### Quality Scoring

**Completeness** is the weighted percentage of filled fields (weights above, summing to 100).

**Quality** adds ring-specific bonuses on top of completeness:

| Ring | Bonus criteria |
|------|---------------|
| **Adopt** | 2+ client references (+20), description ≥ 200 chars (+15), weaknesses filled (+10) |
| **Trial** | 1+ client reference (+15), description ≥ 150 chars (+15), alternatives filled (+10) |
| **Assess** | Description ≥ 100 chars (+15), why_now filled (+15) |
| **Hold** | Description ≥ 100 chars (+15), weaknesses filled (+15), alternatives filled (+10) |

## Configuration

All configuration is via environment variables (or `.env` file):

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | *(required)* | Your Anthropic API key |
| `MODEL_NAME` | `claude-sonnet-4-20250514` | Claude model to use |
| `DEV_MODE` | `false` | Use mock responses without an API key |

## Radar History

Historical radar data comes from the [`setchy/thoughtworks-tech-radar-volumes`](https://github.com/setchy/thoughtworks-tech-radar-volumes) repository. CSV files are cached locally in `data/radar_history/`. The data is loaded on startup and used for duplicate detection when a submitter names a technology.

## Testing

```bash
# Run all 27 tests
pytest

# Verbose output
pytest -v

# Specific test file
pytest tests/test_quality.py -v

# Run by keyword
pytest -k "quality" -v
```

Tests cover models, quality scoring, radar history parsing, JSON storage, conversation sessions, prompt formatting, the mock client, and the WebSocket endpoint.

## Project Structure

```
.
├── app/
│   ├── __init__.py
│   ├── claude_client.py
│   ├── config.py
│   ├── conversation.py
│   ├── main.py
│   ├── mock_client.py
│   ├── models.py
│   ├── prompts.py
│   ├── quality.py
│   ├── radar_history.py
│   └── storage.py
├── data/
│   ├── radar_history/          # 33 historical radar CSV files
│   └── submissions.json        # Saved submissions (gitignored)
├── static/
│   ├── app.js
│   ├── index.html
│   └── style.css
├── tests/
│   ├── conftest.py
│   ├── test_claude_client.py
│   ├── test_conversation.py
│   ├── test_main.py
│   ├── test_mock_client.py
│   ├── test_models.py
│   ├── test_prompts.py
│   ├── test_quality.py
│   ├── test_radar_history.py
│   └── test_storage.py
├── .env.example
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── Makefile
├── requirements.txt
└── README.md
```

## Docker

```bash
# Build and run
docker compose up --build

# Or just build the image
docker build -t tech-radar .
docker run -p 8000:8000 --env-file .env tech-radar
```

## Make Targets

```bash
make help        # Show all available targets
make setup       # Create venv and install dependencies
make run         # Start the app (port 8000)
make dev         # Start with hot reload
make test        # Run test suite
make dev-mode    # Start in dev mode (no API key needed)
make docker      # Build and run with Docker
make clean       # Remove venv, caches, and generated files
```

## License

MIT License. See [LICENSE](LICENSE) for details.
