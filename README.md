# InterroX (AI Interview Simulator) - Phase 0

Phase 0 bootstrap with FastAPI backend, Redis cache, health checks, and dev verification endpoints.

## Prerequisites

- Python 3.11+
- Docker & Docker Compose (or local Redis instance)

## Getting Started

### 1. Start Redis Cache

Start Redis in the background with Docker Compose (configured without disk persistence):

```bash
docker compose up -d redis
```

### 2. Set Up Virtual Environment

From the project root:

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# Windows (cmd):
.\venv\Scripts\activate.bat
# Linux/macOS:
source venv/bin/activate
```

### 3. Install Dependencies

Install pinned Python dependencies:

```bash
pip install -r backend/requirements.txt
```

### 4. Configure Environment

Copy the example environment configuration:

```bash
cp backend/.env.example backend/.env
```

### 5. Run the Backend Server

Run uvicorn from the `backend/` directory:

```bash
cd backend
uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`.

## Testing

Run tests with pytest:

```bash
pytest
```
