from openai import OpenAI
from dotenv import load_dotenv
import os
import sys
import uuid
from navigation_flow import missing_or_unresolved_message
from route_state import (
    clear_last_route_context,
    get_last_route_context,
    handle_route_continuation_query,
    handle_route_info_with_context,
    start_pending_route,
    try_complete_pending_route,
)
from route_parser import parse_route_query

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

DATA_PATH = os.path.join(BASE_DIR, "data")
CHROMA_PATH = os.path.join(BASE_DIR, "chroma_db")
collection = None


def get_collection():
    global collection
    if collection is None:
        import chromadb

        chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
        collection = chroma_client.get_or_create_collection(name="public_transportation")
    return collection

messages_history = [
    {"role": "system", "content": "You are a helpful assistant for UMass Boston transportation"}
]

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)

def format_route_request(route_info):
    if route_info.get("clarification_reason") == "unresolved_start":
        return (
            "I can help with that route, but I could not confidently identify your "
            "starting location. Can you rephrase it using a campus building name?"
        )

    if route_info.get("clarification_reason") == "unresolved_destination":
        return (
            "I can help with that route, but I could not confidently identify your "
            "destination. Can you rephrase it using a campus building name?"
        )

    if route_info["missing"] == "start":
        return "I can help with that route. Where are you starting from?"

    if route_info["missing"] == "destination":
        return "I can help with that route. Where are you trying to go?"

    start = route_info["resolved_start"] or route_info["start"]
    destination = route_info["resolved_destination"] or route_info["destination"]

    return (
        "Route request detected.\n"
        f"Start: {start}\n"
        f"Destination: {destination}\n"
        f"Algorithm: {route_info['algorithm']}"
    )


def _handle_query_core(user_query, route_getter):
    user_query = (user_query or "").strip()

    pending_route_response = try_complete_pending_route(user_query, route_getter)
    if pending_route_response is not None:
        return pending_route_response

    if user_query.lower() in ["exit", "quit", "goodbye", "stop", "bye"]:
        clear_last_route_context()
        return "Goodbye!"

    if user_query.lower() in ["cancel", "nevermind", "never mind"] and get_last_route_context():
        clear_last_route_context()
        return "Okay, I cleared the last route context."

    route_info = parse_route_query(user_query)
    if route_info["is_route"] and not missing_or_unresolved_message(route_info):
        return handle_route_info_with_context(route_info, route_getter)

    route_continuation_response = handle_route_continuation_query(user_query, route_getter)
    if route_continuation_response is not None:
        return route_continuation_response

    if route_info["is_route"]:
        if missing_or_unresolved_message(route_info):
            return start_pending_route(route_info)

        return handle_route_info_with_context(route_info, route_getter)

    results = get_collection().query(
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


def handle_query(user_query):
    return _handle_query_core(user_query, get_route)


def handle_query_web(user_query, show_route_map=False):
    if not show_route_map:
        return {"response": handle_query(user_query), "route_map_url": None}

    static_routes_dir = os.path.join(BASE_DIR, "static", "routes")
    os.makedirs(static_routes_dir, exist_ok=True)
    map_result = {"route_map_url": None}

    def web_route_getter(start, end, algorithm="astar", show_map=False):
        map_filename = f"route_{uuid.uuid4().hex}.png"
        map_file_path = os.path.join(static_routes_dir, map_filename)
        route_result = get_route(
            start,
            end,
            algorithm=algorithm,
            show_map=False,
            save_map_file=map_file_path,
        )
        if (
            isinstance(route_result, dict)
            and route_result.get("success")
            and os.path.exists(map_file_path)
        ):
            map_result["route_map_url"] = f"/static/routes/{map_filename}"
        return route_result

    response = _handle_query_core(user_query, web_route_getter)
    if not (isinstance(response, str) and response.startswith("Route found:")):
        map_result["route_map_url"] = None

    return {
        "response": response,
        "route_map_url": map_result["route_map_url"],
    }

if __name__ == "__main__":
    print("Hello, I am your assistant for transportation at UMass Boston. I can help you with questions about getting to and around the campus using public transportation. Feel free to ask me anything related to this topic! Type 'exit' to stop.\n")

    while True:
        user_query = input("You: ")

        if user_query.lower() in ["exit", "quit", "goodbye", "stop", "bye"]:
            break

        answer = handle_query(user_query)
        print(f"Assistant: {answer}\n")

