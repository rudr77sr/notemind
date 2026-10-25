# notemind

A tool to chat with your own documents. Upload a PDF, and it's automatically parsed, split into chunks, and embedded into a vector database, ready to be searched and used to answer questions grounded in the actual document content.

The full pipeline works end to end: upload a PDF, and it gets parsed, chunked, and embedded into a vector database; ask a question, and it retrieves the most relevant chunks by semantic similarity and generates a grounded answer using an LLM, citing the source passages it used. Documents and questions are scoped to the authenticated user, so each user only ever sees their own uploads.

**Live demo:** https://notemind-k3aj.onrender.com (opens the interactive API docs)

> The demo runs on a free instance that sleeps when idle, so the first request can take around a minute to wake it up.

## What it does

- Accepts a PDF upload via a REST API
- Extracts the raw text from the PDF
- Splits the text into overlapping chunks, so context isn't lost at chunk boundaries
- Generates a vector embedding for each chunk using a local sentence-transformer model
- Stores each chunk and its embedding in PostgreSQL, using `pgvector`, linked back to its source document
- Accepts a natural-language question, embeds it, and runs a vector similarity search to find the most relevant chunks, regardless of exact keyword overlap
- Passes the retrieved chunks to an LLM (Gemini) with an instruction to answer only from that context, to limit unsupported answers
- Returns the generated answer along with the source chunks it was based on
- User accounts with hashed passwords, JWT-based authentication, and per-user data ownership: documents and answers are scoped to whoever is logged in, enforced with a database-level join rather than trusted from client input

## Why chunking and embeddings, specifically

A whole document can't be embedded as a single vector without losing precision, unrelated sections average out into a vague, imprecise representation. Splitting the document into small, overlapping chunks means each chunk's embedding represents a focused piece of meaning. At query time, a question is matched against the closest chunks by meaning, not exact keyword overlap, so it finds the right part of a document even when the question is phrased differently from the source text. Retrieved chunks are then handed to an LLM with an explicit instruction to answer only from that context, which is what keeps answers grounded in the actual document instead of the model's general knowledge.

## Tech Stack

- Python
- FastAPI
- SQLModel (SQLAlchemy + Pydantic)
- PostgreSQL + pgvector
- sentence-transformers (`all-MiniLM-L6-v2`, 384-dimension embeddings, runs locally)
- Gemini API (answer generation)
- pypdf (PDF text extraction)
- JWT authentication (python-jose) with bcrypt password hashing
- Docker and Docker Compose
- Alembic (schema migrations)
- Uvicorn (ASGI server)
- Hosting: Render (Docker) with a Neon Postgres database

## Project Structure

```
main.py              # FastAPI app, models, and endpoints
Dockerfile           # builds the API image
docker-compose.yml   # API + Postgres (pgvector) for local development
alembic/             # database migration scripts
alembic.ini
requirements.txt
.dockerignore
.gitignore
.env                 # not committed, holds GEMINI_API_KEY, SECRET_KEY (and DATABASE_URL when running without Docker)
```

## Run with Docker (recommended)

1. Clone the repository
```bash
git clone https://github.com/rudr77sr/notemind.git
cd notemind
```

2. Create a `.env` file in the project root
```
GEMINI_API_KEY=your_gemini_api_key
SECRET_KEY=your_long_random_secret_string
```
`DATABASE_URL` is set by `docker-compose.yml`, which points the API at the database container by its service name.

3. Build and start everything
```bash
docker compose up --build
```

4. Open the interactive docs
```
http://localhost:8000/docs
```

Notes:
- The first build takes a while because it downloads PyTorch. The image uses the CPU-only build to keep its size down.
- The embedding model is downloaded while the image is built, so containers start without needing to fetch it.
- On startup the app enables the `vector` extension and creates the tables, so a brand-new database works with no manual steps.
- Database data is kept in a named Docker volume. `docker compose down -v` deletes it.

## Run without Docker

1. Create and activate a virtual environment
```bash
python -m venv .venv
source .venv/bin/activate
```

2. Install dependencies
```bash
pip install -r requirements.txt
```

3. Set up PostgreSQL with pgvector

Install the pgvector extension at the system level (package name depends on your Postgres version, e.g. `postgresql-16-pgvector` on Ubuntu), then:

```sql
CREATE DATABASE notemind;
CREATE USER notemind_user WITH PASSWORD 'devpassword';
GRANT ALL PRIVILEGES ON DATABASE notemind TO notemind_user;
GRANT ALL ON SCHEMA public TO notemind_user;
```

Create a `.env` file in the project root:
```
DATABASE_URL=postgresql://notemind_user:devpassword@localhost:5432/notemind
GEMINI_API_KEY=your_gemini_api_key
SECRET_KEY=your_long_random_secret_string
```

4. Run the server
```bash
fastapi dev main.py
```

Tables are created automatically on startup. The embedding model downloads automatically on first run (a few hundred MB, cached afterward).

## Using the API

Open `/docs`, register a user via `/register`, then click **Authorize** (top right) and log in with your username and password there directly, no manual token copying needed. Once authorized, `/documents` and `/ask` can be used straight from the docs UI.

## API Endpoints

| Method | Endpoint | Auth required | Description |
|--------|----------|:---:|--------------|
| GET | / | No | Redirects to the interactive docs |
| POST | /register | No | Create a new user account |
| POST | /login | No | Log in, returns a JWT access token (JSON) |
| POST | /token | No | Log in, returns a JWT access token (form-encoded, used by the Swagger UI Authorize button) |
| POST | /documents | Yes | Upload a PDF. Extracts text, chunks it, generates embeddings, and stores everything under the current user |
| POST | /ask | Yes | Ask a question. Retrieves relevant chunks from the current user's own documents and returns a grounded, cited answer |

## Data Model

```python
class Document(SQLModel, table=True):
    file_id: Optional[int] = Field(default=None, primary_key=True)
    file_name: str
    created_at: datetime = Field(default_factory=datetime.now)
    raw_file_text: str
    user_id: Optional[int] = Field(default=None, foreign_key="user.user_id")
    description: Optional[str] = None

class Chunk(SQLModel, table=True):
    chunk_number: Optional[int] = Field(default=None, primary_key=True)
    document_id: Optional[int] = Field(default=None, foreign_key="document.file_id")
    chunk_index: int
    chunk_text: str
    embedding: list[float] = Field(sa_type=Vector(384))

class User(SQLModel, table=True):
    user_id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(unique=True)
    hashed_password: str
```

Chunking uses a fixed-size sliding window (500 characters per chunk, 100 character overlap) so sentences split across a chunk boundary still appear whole in at least one chunk.

Retrieval joins `Chunk` to `Document` and filters by the logged-in user's `user_id` before ranking by similarity, so a user can only ever retrieve chunks from documents they uploaded, enforced by the database query itself rather than trusted from client input.

## Deployment

The live demo runs as a Docker service on Render's free tier, with a Neon Postgres database (pgvector enabled). Secrets (`GEMINI_API_KEY`, `SECRET_KEY`, `DATABASE_URL`) are set as environment variables in the host's dashboard and never committed to the repository.

## What I'm practicing

- File upload handling in FastAPI (`UploadFile`, multipart form data)
- PDF text extraction
- Writing chunking logic from scratch (fixed-size windows with overlap)
- Generating and storing vector embeddings with `pgvector`
- Vector similarity search (`cosine_distance`, ordering by closeness rather than exact match)
- Prompt construction for grounded, context-restricted LLM answers
- JWT authentication: password hashing, token issuance and verification, a reusable dependency to identify the current user
- SQL joins across related tables to enforce per-user data ownership at the query level
- Supporting both a JSON login endpoint (for real clients) and a form-encoded OAuth2 endpoint (for Swagger UI / standard tooling) against the same underlying auth logic
- Reasoning about why chunk size, overlap, and retrieval count affect answer quality
- Containerizing the app with Docker: ordering Dockerfile steps for build caching, installing CPU-only PyTorch to keep the image small, and baking the embedding model into the image so cold starts don't download it
- Docker Compose with a pgvector Postgres service, a healthcheck, and a named volume, and connecting to the database by service name instead of `localhost`
- Enabling the `pgvector` extension from the app at startup so a fresh database works without manual steps
- Schema migrations with Alembic, including debugging a foreign key migration that failed on orphaned rows
- Deploying a FastAPI + PostgreSQL app, first to Railway and then to Render with Neon, including debugging a missing requirements.txt, a build step that skipped dependency installation, a missing environment variable reference, and a database URL pointing at `localhost` inside a container

## Next steps

- Automated tests (pytest) for authentication and per-user data isolation
- Continuous integration with GitHub Actions
- A retrieval evaluation: a small set of test questions with known answers, measuring how often the right chunk is retrieved, and comparing chunk sizes and overlaps
- Better source citations (page numbers, more precise highlighting of the exact answer span)
- Moving from the deprecated `google.generativeai` package to `google.genai`