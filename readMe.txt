UMass Boston Transportation Chatbot

This project is a chatbot that answers questions about transportation at UMass Boston. It uses PDF documents as its knowledge source, stores the information in ChromaDB, and uses OpenRouter to generate responses.

Features
Answers transportation-related questions using PDF-based knowledge
Vector database powered by ChromaDB
AI responses via OpenRouter API
CLI and Web UI support (Flask)
Setup Instructions
1. Create a .env file

In the root project directory, create a file named .env and add your OpenRouter API key:

OPENROUTER_API_KEY=YOUR_OPENROUTER_API_KEY
2. Install Dependencies

Make sure all required packages are installed:

pip install flask chromadb openai python-dotenv networkx

(Add any additional dependencies the project needs using the requirements.txt.)

3. Run the Ingestion Pipeline

Before starting the chatbot, you MUST run the ingestion pipeline to build the ChromaDB database from the PDFs:

python ingestion_pipeline.py

This step processes the PDF documents and stores embeddings in ChromaDB.

4. Run the Chatbot
Option A: Terminal (CLI)

Run the prompt-based chatbot:

python prompt.py

Then interact directly in the terminal by asking questions or requesting routes.

Option B: Web Interface (Flask)

Run the web app:

python app.py

Then open your browser and go to:

http://localhost:5000

Use the chat interface to ask questions. Route-based inputs may prompt for additional details.

Notes
Make sure the .env file is correctly configured before running anything.
The ingestion pipeline must be run at least once before using the chatbot.
If you update PDFs, re-run the ingestion pipeline to refresh the database.
