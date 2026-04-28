import chromadb
from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()

# DEBUG
# api_key = os.getenv("OPENROUTER_API_KEY")
# if not api_key:
#     print("API key not found. Please set the OPENROUTER_API_KEY environment variable.")
# else:
#     print(f"API key loaded successfully. (starts with: {api_key[:8]}..)")

# setting the environment

DATA_PATH = r"data"
CHROMA_PATH = r"chroma_db"

chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)

collection = chroma_client.get_or_create_collection(name="public_transportation")

messages_history = [
    {"role": "system", "content": "You are a helpful assistant for UMass Boston transportation"}
]

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)

print("Hello, I am your assistant for transportation at UMass Boston. I can help you with questions about getting to and around the campus using public transportation. Feel free to ask me anything related to this topic! Type 'exit' to stop.\n")

while True:
    user_query = input("You: ")

    if user_query.lower() in ["exit", "quit", "goodbye", "stop", "bye"]:
        break

    results = collection.query(
        query_texts=[user_query],
        n_results=3
    )
    documents = results.get('documents', [[]])[0]
    context = "\n\n".join(documents)

#print results['documents']
#print results['metadatas']


# Telling the AI about what specific documents to use for the current question
    current_system_prompt = (
        "You are a helpful assistant for UMass Boston transportation. "
        "Use ONLY the following context to answer. If the answer is not in the context, "
        "strictly say: 'I'm sorry, I don't have that information in my documents.'\n\n"
        f"Context:\n{context}"
    )
    messages_history[0]["content"] = current_system_prompt

    # Add the user's message to the conversation history
    messages_history.append({"role": "user", "content": user_query})

    try:
        response = client.chat.completions.create(
            model="openai/gpt-oss-120b:free",
            messages = messages_history # Passing all history here
        )

        answer = response.choices[0].message.content
        print(f"Assistant: {answer}\n")

        # Add the assistant's response to the conversation history for future context
        messages_history.append({"role": "assistant", "content": answer})

    except Exception as e:
        print(f"Assistant: I hit an error: {e}")

