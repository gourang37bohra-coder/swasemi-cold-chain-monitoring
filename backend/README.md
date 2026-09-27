# Cold-Chain Monitoring Platform — Backend Foundation

## Project Purpose
The **Cold-Chain Monitoring Platform** is a multi-tenant IoT monitoring solution designed to track refrigerated shipments across multiple client organizations. The system will provide live telemetry monitoring (temperature, humidity, door status, GPS location, battery levels), automated temperature breach alerts with grace periods, interactive live maps, historical shipment data with CSV export, and role-based access control (Super Admin and Organization-scoped Users).

---

## Current Status: Phase 2 (Database Domain Models + Multi-Tenant Foundation)
> **Notice:** The project has completed **Phase 1 (Backend Foundation)** and **Phase 2 (Database Domain Models + Multi-Tenant Foundation)**.  
> All core SQLAlchemy models (`Organization`, `User`, `Tracker`, `Shipment`, `Telemetry`, `Alert`) and the initial Alembic migration have been defined and verified.  
> Authentication, login, MQTT ingestion, Redis/WebSocket pipelines, and frontend dashboards have NOT been implemented yet.

---

## Technology Stack (Phase 1)
- **Language:** Python 3.11+ (running Python 3.13)
- **API Framework:** FastAPI 0.141+
- **Data Validation & Settings:** Pydantic v2 & Pydantic-Settings
- **ORM & Data Layer:** SQLAlchemy 2.0+
- **PostgreSQL Driver:** Psycopg 3 (`psycopg[binary]`)
- **Database Migrations:** Alembic 1.20+
- **ASGI Server:** Uvicorn

---

## Directory Structure
```text
backend/
├── alembic/                  # Alembic migration environment and version files
│   ├── versions/
│   ├── env.py
│   └── script.py.mako
├── app/
│   ├── __init__.py
│   ├── main.py               # FastAPI application entry point (/health, /health/db)
│   ├── api/                  # API endpoints and route controllers (reserved)
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py         # Pydantic Settings configuration from environment
│   │   ├── database.py       # SQLAlchemy engine, sessionmaker, and Base
│   │   └── dependencies.py   # FastAPI dependency injection (get_db)
│   ├── models/               # SQLAlchemy ORM models (reserved for Phase 2+)
│   ├── mqtt/                 # MQTT client and packet processors (reserved)
│   ├── realtime/             # Real-time WebSocket and fanout managers (reserved)
│   ├── schemas/              # Pydantic data validation schemas (reserved)
│   ├── services/             # Domain business logic services (reserved)
│   └── utils/                # Utility helpers
├── tests/
│   ├── __init__.py
│   └── test_health.py        # Health and database connectivity test suite
├── .env.example              # Environment variables template
├── .gitignore                # Git ignore configuration
├── alembic.ini               # Alembic configuration file
├── requirements.txt          # Pinned Python package dependencies
└── README.md                 # Backend documentation
```

---

## PostgreSQL Database Setup

### 1. Create the Database
Open PostgreSQL CLI (`psql`) or pgAdmin on your machine:

```bash
# Connect using psql with your postgres user:
psql -U postgres
```

Run the following SQL commands to create the database:
```sql
CREATE DATABASE coldchain_db;
```

*(Optional: If you want to use a dedicated database user)*
```sql
CREATE USER coldchain_user WITH ENCRYPTED PASSWORD 'your_secure_password';
GRANT ALL PRIVILEGES ON DATABASE coldchain_db TO coldchain_user;
ALTER DATABASE coldchain_db OWNER TO coldchain_user;
```

---

## Backend Setup & Execution Guide

### 2. Environment Configuration
Create a `.env` file inside the `backend/` directory by copying `.env.example`:

```bash
# On Windows PowerShell:
Copy-Item .env.example .env
```

Edit `backend/.env` with your PostgreSQL credentials:
```env
APP_NAME="Cold-Chain Monitoring Platform"
APP_ENV=development
DEBUG=true
PORT=8000
HOST=0.0.0.0

# Update with your username, password, host, port, and database name:
DATABASE_URL=postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5432/coldchain_db
```

### 3. Activate the Virtual Environment
The virtual environment is located at `backend/.venv`.

```bash
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1

# Windows Command Prompt (cmd):
.\.venv\Scripts\activate.bat

# Linux / WSL / macOS:
source .venv/bin/activate
```

### 4. Install Dependencies
If installing or updating dependencies into `.venv`:
```bash
pip install -r requirements.txt
```

### 5. Running Database Migrations (Alembic)
Check current migration status:
```bash
alembic current
```
When future models and migration versions are added:
```bash
alembic upgrade head
```

### 6. Start the FastAPI Application
From inside the `backend/` folder:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
Interactive OpenAPI documentation will be accessible at:  
`http://localhost:8000/docs`

---

## Testing Endpoints

### 7. Test `/health`
```bash
# Using curl:
curl http://localhost:8000/health

# Using PowerShell:
Invoke-RestMethod -Uri "http://localhost:8000/health"
```
**Expected Response:**
```json
{
  "status": "ok"
}
```

### 8. Test `/health/db`
```bash
# Using curl:
curl http://localhost:8000/health/db

# Using PowerShell:
Invoke-RestMethod -Uri "http://localhost:8000/health/db"
```

- When PostgreSQL is running and credentials in `.env` are valid:
  ```json
  HTTP 200 OK
  {
    "status": "ok",
    "database": "connected"
  }
  ```
- When PostgreSQL is unreachable or credentials are not yet configured:
  ```json
  HTTP 503 Service Unavailable
  {
    "status": "error",
    "database": "unavailable"
  }
  ```
*(Note: Sensitive connection details and credentials are never exposed to the client).*

---

## Running Automated Tests
Run pytest from within the `backend/` directory:
```bash
pytest tests/
```

---

## What Has NOT Been Implemented Yet (Upcoming Phases)
- Multi-tenancy & Organization models
- User authentication & JWT bearer tokens
- Device simulator & MQTT subscriber (`broker.emqx.io`)
- Redis fan-out & WebSocket streaming
- Shipments, Trackers, Telemetry readings, and Alert models/logic
- Email alerting integration (SMTP / SES)
- React frontend dashboard & Map views
