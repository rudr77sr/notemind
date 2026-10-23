from fastapi import FastAPI, UploadFile, File, Depends, HTTPException
from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field, create_engine, Session, select
from dotenv import load_dotenv
from pgvector.sqlalchemy import Vector
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer
from passlib.context import CryptContext
from jose import jwt, JWTError
from datetime import timedelta
from fastapi.security import OAuth2PasswordBearer,OAuth2PasswordRequestForm
from sqlalchemy import text

import os
import io
import google.generativeai as genai

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
pwd_context = CryptContext(schemes=['bcrypt'], deprecated = 'auto')

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY is None:
    raise RuntimeError("GEMINI_API_KEY is not set")

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL is None:
    raise RuntimeError("DATABASE_URL is not set, check your .env file")

SECRET_KEY = os.getenv("SECRET_KEY")
if SECRET_KEY is None:
    raise RuntimeError("SECRET_KEY is not set")


engine = create_engine(DATABASE_URL, echo=True)

genai.configure(api_key=GEMINI_API_KEY) # type: ignore
gemini_model = genai.GenerativeModel('models/gemini-flash-latest') # type: ignore
embedding_model = SentenceTransformer('all-MiniLM-L6-v2')

class Document(SQLModel, table=True):
    file_id: Optional[int] = Field(default=None, primary_key=True)
    file_name: str
    created_at: datetime = Field(default_factory=datetime.now)
    raw_file_text: str
    user_id: Optional[int] =  Field(default=None, foreign_key="user.user_id")
    description: Optional[str] = None

class Chunk(SQLModel, table=True):
    chunk_number: Optional[int] = Field(default=None, primary_key=True)
    document_id: Optional[int] = Field(default=None ,foreign_key="document.file_id")
    chunk_index: int
    chunk_text: str
    embedding: list[float] = Field(sa_type=Vector(384)) # type: ignore

class AskRequest(SQLModel):
    question: str

class User(SQLModel, table=True):
    user_id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(unique=True)
    hashed_password: str

class UserCreate(SQLModel):
    username: str
    password: str


app = FastAPI(root_path = "/api/v1")

def get_session():
    with Session(engine) as session:
        yield session

@app.on_event('startup') #type: ignore
def on_startup():
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    SQLModel.metadata.create_all(engine)

def chunk_text(text: str, chunk_size: int = 500, overlap: int = 100) -> list[str]:  
    chunks = []
    position = 0
    while position < len(text):
        current_chunk = text[position: position + chunk_size]
        chunks.append(current_chunk) # type: ignore
        position += chunk_size - overlap

    return chunks # type: ignore

def create_access_token(username: str):
    expire = datetime.now() + timedelta(minutes=30)
    to_encode = {"sub": username, "exp": expire}
    return jwt.encode(to_encode, SECRET_KEY, algorithm="HS256")

def get_current_user(token: str = Depends(oauth2_scheme), session: Session = Depends(get_session)) -> User:
    credentials_exception = HTTPException(status_code=401, detail="Could not validate username")

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        username = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    statement = select(User).where(User.username == username)
    results = session.exec(statement)
    found = results.first()
    if found is None:
        raise credentials_exception
    return found



@app.post("/ask")
async def ask_question(body: AskRequest, session: Session = Depends(get_session), current_user: User = Depends(get_current_user)): # type: ignore
    question_embedding = embedding_model.encode(body.question) # type: ignore # type: ignore
    statement = (
    select(Chunk)
    .join(Document, Chunk.document_id == Document.file_id)
    .where(Document.user_id == current_user.user_id)
    .order_by(Chunk.embedding.cosine_distance(question_embedding))
    .limit(3)
)
    results = session.exec(statement)
    top_chunks = results.all()

    context = "\n\n".join([chunk.chunk_text for chunk in top_chunks])

    prompt = f"""Answer the question using only the following context. If the answer isn't in the context, say you don't know.

    Context:
    {context}
    Question: {body.question}"""

    response = gemini_model.generate_content(prompt) # type: ignore
    answer = response.text

    return {"question": body.question, "answer": answer, "sources": [chunk.chunk_text for chunk in top_chunks]} # type: ignore


@app.post("/documents")
async def upload_document(file: UploadFile = File(...), session: Session = Depends(get_session), current_user: User = Depends(get_current_user)):  # type: ignore
    contents = await file.read()
    reader = PdfReader(io.BytesIO(contents))
    text = ""
    for page in reader.pages:
        text += page.extract_text()

    new_doc = Document(file_name = file.filename, raw_file_text=text, user_id=current_user.user_id) # type: ignore
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

@app.post("/register")
async def register(body: UserCreate, session: Session = Depends(get_session)):
    existing = session.exec(select(User).where(User.username == body.username)).first()
    if existing is not None:
        raise HTTPException(status_code=400, detail="Username already taken")

    hashed = pwd_context.hash(body.password)
    new_body = User(username=body.username, hashed_password=hashed)
    session.add(new_body)
    session.commit()
    session.refresh(new_body)

    return{"user_id": new_body.user_id, "username": new_body.username} # type: ignore

@app.post("/login")
async def login(body: UserCreate, session: Session = Depends(get_session)):
    statement = select(User).where(User.username == body.username)
    results = session.exec(statement)
    found = results.first()

    if found is None or not pwd_context.verify(body.password, found.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    return {"access_token": create_access_token(found.username)}

@app.post("/token")
async def login_for_swagger(form_data: OAuth2PasswordRequestForm = Depends(), session: Session = Depends(get_session)):
    statement = select(User).where(User.username == form_data.username)
    found = session.exec(statement).first()
    if found is None or not pwd_context.verify(form_data.password, found.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    return {"access_token": create_access_token(found.username), "token_type": "bearer"}                            