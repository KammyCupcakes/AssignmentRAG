# UMass Boston Transportation Chatbot

This project is a chatbot that answers questions about transportation at UMass Boston. It uses PDF documents as its knowledge source, stores the information in ChromaDB, and uses OpenRouter to generate responses.

## Setup Instructions

### 1. Create a `.env` file

In the main project folder, create a file named `.env`.

Inside the `.env` file, add your OpenRouter API key:

```env
OPENROUTER_API_KEY=YOUR_OPENROUTER_API_KEY


### 2. Run ingestion_pipeline file

Before running the chatbot you MUST run the ingestion_pipeline to create the database in ChromaDB

### 3. Run The Chatbot (prompt.py)