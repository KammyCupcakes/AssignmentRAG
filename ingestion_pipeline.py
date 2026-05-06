import os
from typing import Dict
import chromadb
from dotenv import load_dotenv
from pypdf import PdfReader
from webcrawler import WebsiteCrawler
import json

load_dotenv()

DATA_PATH = "data"
CHROMA_PATH = "chroma_db"

WEBCRAWL_URLS = [
    "https://www.umb.edu/transportation",
]

chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)

collection = chroma_client.get_or_create_collection(
    name="public_transportation",
    metadata={"hnsw:space": "cosine",}
)

def build_document_record(file_meta: Dict, text: str, source: str = "unknown") -> Dict:
        return {
            "document_name": file_meta.get("document_name", "unknown"),
            "path": file_meta.get("path", "unknown"),
            "source_type": source,
            "text": text,
            "char_count": len(text),
        }

def load_webdocs(urls):
    if not urls:
        print("No URLs provided for web crawling. Skipping web document loading.")
        return {
            "documents": [],
            "skipped_pages": [],
            "pages_seen": 0,
        }
    try: 
        saved_webdocs = json.load(open("web_crawl_documents.json", "r", encoding="utf-8"))
        if saved_webdocs:
            print("Using saved web documents. To clear and re-crawl, delete the web_crawl_documents.json file.")
            return {
                "documents": saved_webdocs,
                "skipped_pages": [],
                "pages_seen": 0,
            }
    except FileNotFoundError:
        print(f"No saved web crawl documents found. Starting web crawl for URLs: {urls}...")
        saved_webdocs = None

    crawler = WebsiteCrawler(seeds=urls)
    documents, skipped_pages, pages_seen = crawler.crawl()
    json.dump(documents, open("web_crawl_documents.json", "w", encoding="utf-8"), indent=2)
    print(f"Crawled {pages_seen} pages, extracted {len(documents)} documents, skipped {len(skipped_pages)} pages.")
    return {
        "documents": documents,
        "skipped_pages": skipped_pages,
        "pages_seen": pages_seen,
    }

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
                documents.append(
                    build_document_record(file_meta={"document_name": filename, "path": file_path}, text=full_text)
                )
    
    webdata = load_webdocs(urls=WEBCRAWL_URLS)

    for doc in webdata["documents"]:
        documents.append(build_document_record(file_meta={"document_name": doc["title"], "path": doc["url"]}, text=doc["text"]))  # Add the web documents to the list of documents

    if len(documents) == 0:
        raise FileNotFoundError(
            f"No readable documents found in '{data_path}'. Add your public transportation documents or re-crawl the web."
        )
    
    print (f"Processed {len(documents)} documents(s).")

    # for i, doc in enumerate(documents[:2]):
    #     print(f"\nDocument {i + 1}:")
    #     print(f"  Source: {doc['path']}")
    #     print(f"  Content length: {len(doc['text'])} characters")
    #     print(f"  Preview: {doc['text'][:200]}...")

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
                "id": f"{doc['document_name']}_chunk_{i}",
                "text": chunk,
                "metadata": {
                    "source": doc["path"],
                    "document_name": doc["document_name"],
                    "source_type": doc["source_type"],
                    "chunk_index": i,
                }
            })

    print(f"Created {len(all_chunks)} chunk(s).")

    # for i, chunk in enumerate(all_chunks[:5]):
    #     print(f"\n--- Chunk {i + 1} ---")
    #     print(f"Source: {chunk['metadata']['source']}")
    #     print(f"Length: {len(chunk['text'])} characters")
    #     print(chunk["text"][:500])
    #     print("-" * 50)

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
        metadatas=metadatas,
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