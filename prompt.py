import chromadb
from openai import OpenAI
from dotenv import load_dotenv
import os
import sys

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BEACONNAV_SRC = os.path.join(BASE_DIR, "BeaconNav", "src")

if BEACONNAV_SRC not in sys.path:
    sys.path.insert(0, BEACONNAV_SRC)

from main import get_route

# Store any unanswered question by the chatbot into the unanswered_questions.txt file
# this allows us to refer to the txt file, and update our pdf data.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UNANSWERED_FILE = os.path.join(BASE_DIR, "unanswered_questions.txt")

def log_unanswered_questions(question):
    question = question.strip()
        
    if not question:
        return
    # if the question is not seen yet. Write to the unanswered file.
    if not os.path.exists(UNANSWERED_FILE):
        with open(UNANSWERED_FILE, "w", encoding="utf-8") as file:
            file.write(question + "\n")
        return
    
    with open(UNANSWERED_FILE, "r", encoding="utf-8") as file:
        existing_questions = [line.strip().lower() for line in file]

    # stops previously appeneded questions from being overwritten
    if question.lower() not in existing_questions:
        with open(UNANSWERED_FILE, "a", encoding="utf-8") as file:
            file.write(question + "\n")

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

def handle_query(user_query):
    if user_query.lower() in ["exit", "quit", "goodbye", "stop", "bye"]:
        return "Goodbye!"

    route_keywords = ["walk", "walking", "route", "directions", "get from", "go from"]

    if any(keyword in user_query.lower() for keyword in route_keywords):
        # For web UI, simulate inputs or handle via session; here, return a prompt for locations
        return "Please provide starting location, ending location, and algorithm (astar or dijkstra)."

    results = collection.query(
        query_texts=[user_query],
        n_results=3
    )
    documents = results.get('documents', [[]])[0]
    context = "\n\n".join(documents)

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

        # creating fallback phrases to help store unanswered questions returned by the chatbot

        fallback_phrases = [
            "I'm sorry, I don't have that information in my documents.",
            "I don't know",
            "I'm unsure, I don't have that information in my documents.",
            "Sorry, I don't know.",
            "I do not know",
            "I am not sure",
            "I'm not sure"
        ]
        if any(phrase.lower() in answer.lower() for phrase in fallback_phrases):
            log_unanswered_questions(user_query)

        # Add the assistant's response to the conversation history for future context
        messages_history.append({"role": "assistant", "content": answer})

        return answer

    except Exception as e:
        return f"I hit an error: {e}"

if __name__ == "__main__":
    print("Hello, I am your assistant for transportation at UMass Boston. I can help you with questions about getting to and around the campus using public transportation. Feel free to ask me anything related to this topic! Type 'exit' to stop.\n")

    while True:
        user_query = input("You: ")

        if user_query.lower() in ["exit", "quit", "goodbye", "stop", "bye"]:
            break

        route_keywords = ["walk", "walking", "route", "directions", "get from", "go from"]

        if any(keyword in user_query.lower() for keyword in route_keywords):
            start = input("Starting location: ")
            end = input("Ending location: ")
            algorithm = input("Algorithm ('astar' or 'dijkstra') [default: astar]: ")

            if algorithm.strip() == "":
                algorithm = "astar"

            try:
                route = get_route(start, end, algorithm, show_map=True)

                if not route["success"]:
                    print(f"Assistant: {route['error']}\n")
                    continue

                print(
                    f"Assistant: Here is the walking route information:\n"
                    f"Start: {route['start']}\n"
                    f"End: {route['end']}\n"
                    f"Algorithm: {route['algorithm']}\n"
                    f"Estimated walk time: {route['walk_time_minutes']:.1f} minutes\n"
                    f"Walking distance: {route['distance_miles']:.2f} miles\n"
                    f"Expanded nodes: {route['expanded_nodes']}\n"
                )

            except Exception as e:
                print(f"Assistant: I could not calculate the walking route right now. Error: {e}\n")

            continue

        answer = handle_query(user_query)
        print(f"Assistant: {answer}\n")

