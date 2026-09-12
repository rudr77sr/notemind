# notemind

A tool to chat with your own documents. Upload a PDF, and it's automatically parsed, split into chunks, and embedded into a vector database, ready to be searched and used to answer questions grounded in the actual document content.

This project is in progress. The full pipeline works end to end: upload a PDF, and it gets parsed, chunked, and embedded into a vector database; ask a question, and it retrieves the most relevant chunks by semantic similarity and generates a grounded answer using an LLM, citing the source passages it used. Documents and questions are scoped to the authenticated user, so each user only ever sees their own uploads. Deployment is the next step.

## What it does right now

- Accepts a PDF upload via a REST API
- Extracts the raw text from the PDF
- Splits the text into overlapping chunks, so context isn't lost at chunk boundaries
- Generates a vector embedding for each chunk using a local sentence-transformer model
- Stores each chunk and its embedding in PostgreSQL, using `pgvector`, linked back to its source document
- Accepts a natural-language question, embeds it, and runs a vector similarity search to find the most relevant chunks, regardless of exact keyword overlap
- Passes the retrieved chunks to an LLM (Gemini) with an instruction to answer only from that context, reducing hallucinated answers
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
- pypdf (PDF text extraction)
- Uvicorn (ASGI server)

## Project Structure

```
main.py
requirements.txt
.gitignore
.env          # not committed, holds DATABASE_URL, GEMINI_API_KEY, SECRET_KEY
```

## Setup

1. Clone the repository
```bash
git clone https://github.com/yourusername/notemind.git
cd notemind
```

2. Create and activate a virtual environment
```bash
python -m venv .venv
source .venv/bin/activate
```

3. Install dependencies
```bash
pip install -r requirements.txt
```

4. Set up PostgreSQL with pgvector

Install the pgvector extension at the system level (package name depends on your Postgres version, e.g. `postgresql-16-pgvector` on Ubuntu), then:

```sql
CREATE DATABASE notemind;
CREATE USER notemind_user WITH PASSWORD 'devpassword';
GRANT ALL PRIVILEGES ON DATABASE notemind TO notemind_user;
GRANT ALL ON SCHEMA public TO notemind_user;
```

Connect to the `notemind` database specifically, then enable the extension:
```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

Create a `.env` file in the project root:
```
DATABASE_URL=postgresql://notemind_user:devpassword@localhost:5432/notemind
GEMINI_API_KEY=your_gemini_api_key
SECRET_KEY=your_long_random_secret_string
```

5. Run the server
```bash
fastapi dev main.py
```

Tables are created automatically on startup. The embedding model downloads automatically on first run (a few hundred MB, cached afterward).

6. Open the interactive docs in your browser
```
http://127.0.0.1:8000/docs
```

7. Register and log in

Register a user via `/register`, then click **Authorize** (top right of `/docs`) and log in with your username and password there directly, no manual token copying needed. Once authorized, `/documents` and `/ask` can be used straight from the docs UI.

## API Endpoints

| Method | Endpoint | Auth required | Description |
|--------|----------|:---:|--------------|
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

## Next steps

- Deployment
- Better source citations (page numbers, more precise highlighting of the exact answer span)