# notemind

A tool to chat with your own documents. Upload a PDF, and it's automatically parsed, split into chunks, and embedded into a vector database, ready to be searched and used to answer questions grounded in the actual document content.

This project is in progress. The ingestion pipeline (upload, text extraction, chunking, embeddings) is complete and working. The retrieval and question-answering side is being built next.

## What it does right now

- Accepts a PDF upload via a REST API
- Extracts the raw text from the PDF
- Splits the text into overlapping chunks, so context isn't lost at chunk boundaries
- Generates a vector embedding for each chunk using a local sentence-transformer model
- Stores each chunk and its embedding in PostgreSQL, using `pgvector`, linked back to its source document

## Why chunking and embeddings, specifically

A whole document can't be embedded as a single vector without losing precision, unrelated sections average out into a vague, imprecise representation. Splitting the document into small, overlapping chunks means each chunk's embedding represents a focused piece of meaning. At query time, a question can be matched against the closest chunk by meaning, not exact keyword overlap. This is what will let the eventual question-answering feature find the right part of a document even when the question is phrased differently from the source text.

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
.env          # not committed, holds DATABASE_URL
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

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|--------------|
| POST | /documents | Upload a PDF. Extracts text, chunks it, generates embeddings, and stores everything. |

More endpoints (asking questions, retrieving answers with citations) are in progress.

## Data Model

```python
class Document(SQLModel, table=True):
    file_id: Optional[int] = Field(default=None, primary_key=True)
    file_name: str
    created_at: datetime = Field(default_factory=datetime.now)
    raw_file_text: str

class Chunk(SQLModel, table=True):
    chunk_number: Optional[int] = Field(default=None, primary_key=True)
    document_id: Optional[int] = Field(default=None, foreign_key="document.file_id")
    chunk_index: int
    chunk_text: str
    embedding: list[float] = Field(sa_type=Vector(384))
```

Chunking uses a fixed-size sliding window (500 characters per chunk, 100 character overlap) so sentences split across a chunk boundary still appear whole in at least one chunk.

## What I'm practicing

- File upload handling in FastAPI (`UploadFile`, multipart form data)
- PDF text extraction
- Writing chunking logic from scratch (fixed-size windows with overlap)
- Generating and storing vector embeddings with `pgvector`
- Reasoning about why chunk size and overlap matter for retrieval quality

## Next steps

- Question-answering endpoint: embed a user's question, run a vector similarity search against stored chunks, pass the top matches to an LLM, and return an answer with citations back to the source chunk
- Authentication (JWT), reusing the pattern from my other project, so documents belong to specific users
- Deployment