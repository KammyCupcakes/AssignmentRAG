import json
from openai import OpenAI
from dotenv import load_dotenv
from tools import TOOLS, execute_tool_call
import os
from typing import Any
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

from BeaconNav.src.main import get_route

# Store any unanswered question by the chatbot into the unanswered_questions.txt file
# this allows us to refer to the txt file, and update our pdf data.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UNANSWERED_FILE = os.path.join(BASE_DIR, "unanswered_questions.txt")

FALLBACK_PHRASES = [
    "I don't have that information in my documents",
    "I don't know the answer to that",
    "I don't have that information",
    "I can't find that information in my documents",
    "I'm sorry, I don't have that information in my documents"
]

SYSTEM_PROMPT = ("You are a helpful assistant for UMass Boston transportation. "
        "If the user asks a question, try to answer it based on previous context first. If the answer is not found, search the documents using a tool call."
        "If the user asks for walking directions, respond with a prompt to get unknown information (starting location and ending location), and make a tool call"
        "to get the walking directions. Always use the provided tools or previous tool responses to answer the user's question, and do not attempt to generate them yourself. ")

ONBOARDING_MESSAGE = ("Hello, I am your assistant for transportation at UMass Boston."
"You can ask me questions about UMass Boston transportation, such as bus schedules, shuttle routes, parking information, and more. "
"If you want to get walking directions between two locations, provide your starting location, ending location, and preferred algorithm (A* or Dijkstra). ")

SUGGESTED_QUESTIONS = [
    "What are the bus schedules for UMass Boston?",
    "How do I get from West Garage to Campus center?",
    "What shuttle routes are available on campus?",
    "Where can I find information about parking permits?",
]
TOOLS_RESPONSE_MAX_TOKENS = 3000

TOOL_REPROMPT_TEMPLATE = """Tool call results:
{tool_results}

Incorporate these results into your next response to the user, using them as needed to answer the user's question.
If the tool results contain factual information relevant to the user's query, use that information in your response and cite it appropriately.
If low confidence is False and at least one result is present, provide a direct answer from the top-ranked evidence and do not say you lack information.
Always prioritize accuracy and grounding in the provided tool results when formulating your response.
Treat the top-ranked evidence snippet as the primary grounding, then use additional results only if they add non-duplicative detail.
If the tool results indicate an error or issue with retrieving information, respond strictly with one of the fallback phrases, 
and no extra text:\n\nFALLBACK PHRASES: " + ", ".join(FALLBACK_PHRASES) + ". \n\n"
"""

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
    {"role": "system", "content": SYSTEM_PROMPT}
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

    # Add the user's message to the conversation history
    messages_history.append({"role": "user", "content": user_query})

    pending_route_response = try_complete_pending_route(user_query, route_getter)
    if pending_route_response is not None:
        return pending_route_response

    # if user_query.lower() in ["exit", "quit", "goodbye", "stop", "bye"]:
    #     clear_last_route_context()
    #     return "Goodbye!"

    # if user_query.lower() in ["cancel", "nevermind", "never mind"] and get_last_route_context():
    #     clear_last_route_context()
    #     return "Okay, I cleared the last route context."

    # route_info = parse_route_query(user_query)
    # if route_info["is_route"] and not missing_or_unresolved_message(route_info):
    #     return handle_route_info_with_context(route_info, get_route)

    # route_continuation_response = handle_route_continuation_query(user_query, get_route)
    # if route_continuation_response is not None:
    #     return route_continuation_response

    # if route_info["is_route"]:
    #     if missing_or_unresolved_message(route_info):
    #         return start_pending_route(route_info)

    #     return handle_route_info_with_context(route_info, get_route)

    # results = get_collection().query(
    #     query_texts=[user_query],
    #     n_results=3
    # )
    # documents = results.get('documents', [[]])[0]
    # context = "\n\n".join(documents)

    # # Telling the AI about what specific documents to use for the current question
    # current_system_prompt = (
    #     "You are a helpful assistant for UMass Boston transportation. "
    #     "Use ONLY the following context to answer. If the answer is not in the context, "
    #     "strictly say: 'I'm sorry, I don't have that information in my documents.'\n\n"
    #     f"Context:\n{context}"
    # )
    # messages_history[0]["content"] = current_system_prompt

    try:
        response = client.chat.completions.create(
            model="openai/gpt-oss-120b:free",
            messages = messages_history, # Passing all history here
            tools=TOOLS,
        )

        answer = response.choices[0].message

        tool_calls = answer.tool_calls or []
        if tool_calls:
            for tool_call in tool_calls:
                function_name = tool_call.function.name
                arguments_raw = tool_call.function.arguments or "{}"

        tool_results: list[dict[str, Any]] = []
        for tool_call in tool_calls:
            function_name = tool_call.function.name
            arguments_raw = tool_call.function.arguments or "{}"

            try:
                arguments = json.loads(arguments_raw)
            except json.JSONDecodeError:
                arguments = {}

            database_path = os.path.join(BASE_DIR, "data", "chroma_db")

            try:
                tool_result = execute_tool_call(
                    function_name,
                    arguments,
                    tool_context={"database_path": database_path},
                )
                tool_results.append(
                    {
                        "name": function_name,
                        "arguments": arguments,
                        "result": tool_result,
                    }
                )
            except Exception as e:
                tool_results.append(
                    {
                        "name": function_name,
                        "arguments": arguments,
                        "result": {"error": f"Error executing tool {function_name}: {str(e)}"},
                    }
                )

        formatted_results = format_tool_results_for_prompt(tool_results)
        generated_reprompt = TOOL_REPROMPT_TEMPLATE.format(tool_results=formatted_results)

        messages_history.append({"role": "system", "content": generated_reprompt})
        response = client.chat.completions.create(
            model="openai/gpt-oss-120b:free",
            messages = messages_history,
            tools=TOOLS,
        )
        final_message = response.choices[0].message

        if (not final_message.content or any(phrase.lower() in final_message.content.lower() for phrase in FALLBACK_PHRASES)):
            log_unanswered_questions(user_query)

        # Add the assistant's response to the conversation history for future context
        messages_history.append({"role": "assistant", "content": final_message.content})

        return final_message.content

    except Exception as e:
        return f"I hit an error: {e}"

def format_tool_results_for_prompt(tool_results) -> str:
        prompt_blocks: list[str] = []
        for tool_result in tool_results:
            name = tool_result["name"]
            result = tool_result["result"]
            print(f"\n\n\n\nTool call result for {name}: {result}")  # Debug print to see tool results
            if isinstance(result, dict) and result.get("results") is not None:
                lines = [
                    f"Tool: {name}",
                    f"Query: {result.get('query', '')}",
                    f"Low confidence: {result.get('low_confidence', False)}",
                ]
                for item in result.get("results", [])[:5]:
                    lines.extend(
                        [
                            f"Rank {item.get('rank', '?')} | Title: {item.get('title', 'Untitled')}",
                            f"URL: {item.get('url', '')}",
                            f"Matched terms: {', '.join(item.get('matched_terms', [])) or 'n/a'}",
                            f"Why it matched: {', '.join(item.get('match_reasons', [])) or 'n/a'}",
                            f"Evidence: {item.get('evidence_snippet', '')}",
                        ]
                    )
                prompt_blocks.append("\n".join(lines))
                continue
            prompt_blocks.append(f"Tool: {name}\nResult: {result}")

def handle_query(user_query):
    return _handle_query_core(user_query, get_route)


def handle_query_web(user_query, show_route_map=False):
    if not show_route_map:
        return {"response": handle_query(user_query), "route_map_url": None}

    static_routes_dir = os.path.join(BASE_DIR, "static", "routes")
    os.makedirs(static_routes_dir, exist_ok=True)
    map_result = {"route_map_url": None}

    def web_route_getter(start, end, algorithm="astar", show_map=False):
        import matplotlib.pyplot as plt

        # Web requests run in worker threads; use a non-GUI backend for safe image rendering.
        plt.switch_backend("Agg")

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

def process_query(user_query: str) -> str:
        route_info = parse_route_query(user_query)

        if route_info["is_route"]:
            if route_info.get("clarification_reason"):
                return f"Assistant: {format_route_request(route_info)}\n"

            start = route_info["resolved_start"] or route_info["start"]
            end = route_info["resolved_destination"] or route_info["destination"]
            algorithm = route_info["algorithm"]

            if not start:
                start = input("Starting location: ")

            if not end:
                end = input("Ending location: ")

            try:
                route = get_route(start, end, algorithm, show_map=True)

                if not route["success"]:
                    return f"Assistant: {route['error']}\n"

                context = (
                    f"Assistant: Here is the walking route information:\n"
                    f"Start: {route['start']}\n"
                    f"End: {route['end']}\n"
                    f"Algorithm: {route['algorithm']}\n"
                    f"Estimated walk time: {route['walk_time_minutes']:.1f} minutes\n"
                    f"Walking distance: {route['distance_miles']:.2f} miles\n"
                    f"Expanded nodes: {route['expanded_nodes']}\n"
                )

                handle_query(user_query, context)  # To maintain conversation history

            except Exception as e:
                return f"Assistant: I could not calculate the walking route right now. Error: {e}\n"
        else:
            return handle_query(user_query)
        
if __name__ == "__main__":
    print(ONBOARDING_MESSAGE)

    while True:
        user_query = input("You: ")

        if user_query.lower() in ["exit", "quit", "goodbye", "stop", "bye"]:
            break

        answer = handle_query(user_query)
        print(f"Assistant: {answer}\n")

