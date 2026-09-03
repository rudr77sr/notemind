from fastapi import FastAPI, UploadFile, File, Depends
from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field, create_engine, Session
from dotenv import load_dotenv
from pgvector.sqlalchemy import Vector
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer
import os
import io

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL is None:
    raise RuntimeError("DATABASE_URL is not set, check your .env file")

engine = create_engine(DATABASE_URL, echo=True)

embedding_model = SentenceTransformer('all-MiniLM-L6-v2')

class Document(SQLModel, table=True):
    file_id: Optional[int] = Field(default=None, primary_key=True)
    file_name: str
    created_at: datetime = Field(default_factory=datetime.now)
    raw_file_text: str

class Chunk(SQLModel, table=True):
    chunk_number: Optional[int] = Field(default=None, primary_key=True)
    document_id: Optional[int] = Field(default=None ,foreign_key="document.file_id")
    chunk_index: int
    chunk_text: str
    embedding: list[float] = Field(sa_type=Vector(384)) # type: ignore

app = FastAPI(root_path = "/api/v1")

def get_session():
    with Session(engine) as session:
        yield session

@app.on_event('startup') #type: ignore

def on_startup():
    SQLModel.metadata.create_all(engine)

def chunk_text(text: str, chunk_size: int = 500, overlap: int = 100) -> list[str]:
    chunks = []
    position = 0
    while position < len(text):
        current_chunk = text[position: position + chunk_size]
        chunks.append(current_chunk) # type: ignore
        position += chunk_size - overlap

    return chunks # type: ignore


@app.post("/documents")
async def upload_document(file: UploadFile = File(...), session: Session = Depends(get_session)):  # type: ignore
    contents = await file.read()
    reader = PdfReader(io.BytesIO(contents))
    text = ""
    for page in reader.pages:
        text += page.extract_text()
    # return {"text": text}

    new_doc = Document(file_name = file.filename, raw_file_text=text) # type: ignore
    session.add(new_doc)
    session.commit()
    session.refresh(new_doc)
    chunks = chunk_text(text)
    for index, chunk in enumerate(chunks): # type: ignore
        embedding = embedding_model.encode(chunk) # type: ignore
        new_chunk = Chunk(document_id=new_doc.file_id, chunk_index=index, chunk_text=chunk, embedding=embedding) # type: ignore
        session.add(new_chunk)
        session.commit()
        return {"file_id": new_doc.file_id, "file_name": new_doc.file_name, "chunks_created": len(chunks)} # type: ignore

    return {"file_id": new_doc.file_id, "file_name": new_doc.file_name} # type: ignore