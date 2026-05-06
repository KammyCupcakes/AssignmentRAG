UMass Boston Transportation Chatbot

This project is a local RAG chatbot for UMass Boston transportation and campus navigation questions. It uses local PDFs from the data folder, stores chunks in ChromaDB, uses OpenRouter for chatbot answers, and can call BeaconNav for campus walking routes.

Features

- PDF-based document ingestion
- Optional UMass transportation web crawl/cache during ingestion
- ChromaDB vector search
- OpenRouter chatbot responses
- Flask web interface
- Terminal chatbot
- BeaconNav walking route support
- Unanswered question logging

Setup Instructions

1. Go into the project folder

cd AssignmentRAG

2. Create and activate a virtual environment

py -3.12 -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\.venv\Scripts\Activate.ps1

3. Install dependencies

python -m pip install -r requirements.txt

4. Create a .env file

Create a file named .env inside AssignmentRAG and add:

OPENROUTER_API_KEY=YOUR_OPENROUTER_API_KEY

Run the Ingestion Pipeline

Before using document-based answers, run:

py -3.12 ingestion_pipeline.py

This loads PDFs from data, chunks them, creates embeddings, and stores them in chroma_db. The pipeline may also use cached/crawled UMass transportation web documents.

If the vector store already exists, you may see:

Vector store already has documents.
Current collection count: ...
if you want to rebuild it, delete the chroma_db folder first.

Run the Chatbot

Web interface:

py -3.12 app.py

Then open:

http://localhost:5000

Terminal chatbot:

py -3.12 prompt.py

Example Questions

- What parking options are available?
- Can I bike to UMass Boston?
- take me from u hall to quin building
- How do I get from University Hall to McCormack?
- How do I get to Healey Library?
- from there how do i get to isc

Testing

Run all tests from the AssignmentRAG folder:

py -3.12 -m unittest

To see retrieval scores:

py .\retrieval_metrics.py --questions .\eval_questions.json

Notes

- Run ingestion before expecting RAG answers from the source documents.
- Keep OPENROUTER_API_KEY in .env, not in Git.
- BeaconNav route tests use mocks and should not require OpenRouter or ChromaDB.
- unanswered_questions.txt tracks questions the chatbot could not answer.
