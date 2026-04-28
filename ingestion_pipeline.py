import os
import chromadb
from dotenv import load_dotenv
from pypdf import PdfReader

load_dotenv()

DATA_PATH = "data"
CHROMA_PATH = "chroma_db"

chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)

collection = chroma_client.get_or_create_collection(
    name="public_transportation",
    metadata={"hnsw:space": "cosine",}
)

def load_documents(data_path=DATA_PATH):
    """Load all .pdf files from the data directory."""

    print(f"Loading documents from {data_path}...")

    if not os.path.exists(data_path):
        raise FileNotFoundError(
            f"The directory '{data_path}' does not exist. Please create it and add your .pdf files."
        )
    
    documents = []

    for filename in os.listdir(data_path):
        if filename.endswith(".pdf"):
            file_path = os.path.join(data_path, filename)

            reader = PdfReader(file_path)

            full_text = ""

            for page_number, page in enumerate(reader.pages):
                page_text = page.extract_text()

                if page_text:
                    full_text += f"\n\n--- Page {page_number + 1} ---\n"
                    full_text += page_text

            if full_text.strip():
                documents.append({
                    "filename": filename,
                    "path": file_path,
                    "text": full_text
                })

    if len(documents) == 0:
        raise FileNotFoundError(
            f"No readable PDF files found in '{data_path}'. Add your public transportation PDFs first."
        )
    
    print (f"Loaded {len(documents)} PDF documents(s).")

    for i, doc in enumerate(documents[:2]):
        print(f"\nDocument {i + 1}:")
        print(f"  Source: {doc['path']}")
        print(f"  Content length: {len(doc['text'])} characters")
        print(f"  Preview: {doc['text'][:200]}...")

    return documents

def chunk_text(text, chunk_size=1000, chunk_overlap=100):
    """Split documents into smaller chunks."""

    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]

        if chunk.strip():
            chunks.append(chunk)

        start += chunk_size - chunk_overlap

    return chunks

def split_documents(documents, chunk_size=1000, chunk_overlap=100):
    """Split all loaded PDF documents into chunks."""

    all_chunks = []

    for doc in documents:
        chunks = chunk_text(
            doc["text"],
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )

        for i, chunk in enumerate(chunks):
            all_chunks.append({
                "id": f"{doc['filename']}_chunk_{i}",
                "text": chunk,
                "metadata": {
                    "source": doc["path"],
                    "filename": doc["filename"],
                    "chunk_number": i
                }
            })

    print(f"Created {len(all_chunks)} chunk(s).")

    for i, chunk in enumerate(all_chunks[:5]):
        print(f"\n--- Chunk {i + 1} ---")
        print(f"Source: {chunk['metadata']['source']}")
        print(f"Length: {len(chunk['text'])} characters")
        print(chunk["text"][:500])
        print("-" * 50)

    return all_chunks

def create_vector_store(chunks):
    """Add chunks to ChromaDB."""

    print(f"\nCreating embeddings and storing chunks in ChromaDB...")

    ids = [chunk["id"] for chunk in chunks]
    documents = [chunk["text"] for chunk in chunks]
    metadatas = [chunk["metadata"] for chunk in chunks]

    collection.add(
        ids=ids,
        documents=documents,
        metadatas=metadatas
    )

    print(f"Added {len(chunks)} chunks to ChromaDB.")
    print(f"Collection now has {collection.count()} total chunks.")

def main():
    print("=== UMass Boston Transportation PDF Ingestion Pipeline ===\n")

    if collection.count() > 0:
        print("Vector store already has documents.")
        print(f"Current collection count: {collection.count()}")
        print("if you want to rebuild it, delete the chroma_db folder first.")
        return

    documents = load_documents(DATA_PATH)

    chunks = split_documents(
        documents,
        chunk_size=1000,
        chunk_overlap=100
    )

    create_vector_store(chunks)

    print("\nIngestion complete. Your chatbot can now search the PDF documents.")

if __name__ == "__main__":
    main()