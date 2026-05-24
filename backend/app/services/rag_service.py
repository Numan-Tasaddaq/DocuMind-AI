import uuid
from pathlib import Path

from app.core.config import get_settings

settings = get_settings()


def _storage_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _resolve_chroma_directory() -> str:
    configured = settings.chroma_persist_directory.strip()
    if not configured:
        configured = "storage/chroma"

    path = Path(configured)
    if not path.is_absolute():
        path = _storage_root() / configured
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def _embeddings():
    from langchain_google_genai import GoogleGenerativeAIEmbeddings

    return GoogleGenerativeAIEmbeddings(
        model=settings.gemini_embedding_model,
        google_api_key=settings.gemini_api_key,
    )


def _vector_store():
    from langchain_chroma import Chroma

    return Chroma(
        collection_name="documind_user_documents",
        embedding_function=_embeddings(),
        persist_directory=_resolve_chroma_directory(),
    )


def _build_documents_from_file(file_path: Path, extension: str, extracted_text: str):
    from langchain.schema import Document

    normalized = extension.lower().strip(".")

    if normalized == "pdf":
        from langchain_community.document_loaders import PyPDFLoader

        return PyPDFLoader(str(file_path)).load()
    if normalized == "docx":
        from langchain_community.document_loaders import Docx2txtLoader

        return Docx2txtLoader(str(file_path)).load()

    return [
        Document(
            page_content=extracted_text,
            metadata={"source": str(file_path)},
        )
    ]


def index_user_document(
    *,
    user_id: uuid.UUID,
    document_id: uuid.UUID,
    original_filename: str,
    extension: str,
    file_path: Path,
    extracted_text: str,
) -> int:
    from langchain.text_splitter import RecursiveCharacterTextSplitter

    documents = _build_documents_from_file(file_path, extension, extracted_text)
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.rag_chunk_size,
        chunk_overlap=settings.rag_chunk_overlap,
    )
    chunks = splitter.split_documents(documents)

    if not chunks:
        return 0

    user_id_str = str(user_id)
    doc_id_str = str(document_id)
    for index, chunk in enumerate(chunks):
        chunk.metadata = {
            **(chunk.metadata or {}),
            "user_id": user_id_str,
            "document_id": doc_id_str,
            "original_filename": original_filename,
            "chunk_index": index,
        }

    ids = [f"{doc_id_str}:{i}" for i in range(len(chunks))]
    store = _vector_store()
    store.add_documents(chunks, ids=ids)
    return len(chunks)


def delete_document_vectors(document_id: uuid.UUID) -> None:
    doc_id_str = str(document_id)
    store = _vector_store()
    try:
        existing = store.get(where={"document_id": doc_id_str}, include=[])
    except Exception:
        return
    ids = existing.get("ids", []) if existing else []
    if ids:
        store.delete(ids=ids)


def retrieve_relevant_chunks(
    *,
    user_id: uuid.UUID,
    query: str,
    filenames: list[str] | None = None,
    top_k: int | None = None,
) -> list:
    store = _vector_store()
    where: dict = {"user_id": str(user_id)}
    k = top_k or settings.rag_top_k

    if filenames:
        try:
            where = {"$and": [where, {"original_filename": {"$in": filenames}}]}
        except Exception:
            where = {"user_id": str(user_id)}

    try:
        return store.similarity_search(query, k=k, filter=where)
    except Exception:
        if filenames:
            return store.similarity_search(query, k=k, filter={"user_id": str(user_id)})
        raise
