import json
import re
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
        "Your goal is to help answer questions about UMass Boston transportation and campus services. "
        "For any question about transportation, parking, shuttle schedules, walking directions, or campus services, use the search tool to find relevant information. "
        "If the user asks for walking directions between campus locations, make a tool call to get_walking_directions with the starting and ending locations. "
        "Always prioritize providing helpful information based on tool results. "
        "If a user asks about something outside UMass Boston's scope, politely explain that you can only help with UMass Boston transportation topics.")

ONBOARDING_MESSAGE = ("Hello, I am your assistant for transportation at UMass Boston."
"You can ask me questions about UMass Boston transportation, such as bus schedules, shuttle routes, parking information, and more. "
"If you want to get walking directions between two locations, provide your starting location, ending location, and preferred algorithm (A* or Dijkstra). ")

SUGGESTED_QUESTIONS = [
    "What are the shuttle routes at UMass Boston?",
    "When does the last bus leave campus?",
    "How do I get from West Garage to Campus center?",
    "How much does it cost to get a parking permit for the semester?",
]
TOOLS_RESPONSE_MAX_TOKENS = 3000
DEBUG = os.getenv("ASSIGNMENTRAG_DEBUG") == "1"

TOOL_REPROMPT_TEMPLATE = """Tool call results:
{tool_results}

Incorporate these results into your next response to the user, using them as needed to answer the user's question.
If the tool results contain factual information relevant to the user's query, use that information in your response.
Do not include bracketed source markers in the answer text. The app will add a Sources section when public web sources are available.
If low confidence is False and at least one result is present, provide a direct answer from the top-ranked evidence and do not say you lack information.
Always prioritize accuracy and grounding in the provided tool results when formulating your response.
If the tool results indicate an error or issue with retrieving information, respond with a message letting the user know that relevant information could not be found.
Only use fallback phrases if no useful information was found despite searching multiple times, responding only with the fallback phrase.
\n\nFALLBACK PHRASES: " + ", ".join(FALLBACK_PHRASES) + ". \n\n"
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

# Global to store captured route image across tool execution
_captured_route_image = None

client = None

def get_client():
    global client
    if client is None:
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPENROUTER_API_KEY"),
        )
    return client

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

def get_openai_response(messages):
    return client.chat.completions.create(
        model="gpt-oss-120b:free",
        messages=messages,
        tools=TOOLS,
    )

def is_web_source(source: str | None) -> bool:
    return isinstance(source, str) and source.strip().lower().startswith(("http://", "https://"))


def format_sources_section(sources: list[dict], max_sources: int = 3) -> str:
    lines = []
    seen_urls = set()

    for source_info in sources:
        source_url = str(source_info.get("source") or "").strip()
        if not is_web_source(source_url):
            continue

        if source_url in seen_urls:
            continue

        seen_urls.add(source_url)
        document_name = str(source_info.get("document_name") or "").strip()
        if document_name:
            lines.append(f"{len(lines) + 1}. {document_name} \u2014 {source_url}")
        else:
            lines.append(f"{len(lines) + 1}. {source_url}")

        if len(lines) >= max_sources:
            break

    if not lines:
        return ""

    return "Sources:\n" + "\n".join(lines)


def strip_unsupported_citation_markers(answer: str) -> str:
    if not isinstance(answer, str):
        return answer

    return re.sub(r"\s*【[^】]*†source】", "", answer)


def append_sources_section(answer: str, sources: list[dict]) -> str:
    answer = strip_unsupported_citation_markers(answer)

    if not isinstance(answer, str) or answer.startswith("Route found:"):
        return answer

    sources_section = format_sources_section(sources)
    if not sources_section:
        return answer

    if "Sources:" in answer:
        return answer

    return f"{answer.rstrip()}\n\n{sources_section}"


def collect_search_sources(tool_results: list[dict]) -> list[dict]:
    sources = []
    for tool_result in tool_results:
        if tool_result.get("name") != "search_documents":
            continue

        result = tool_result.get("result")
        if not isinstance(result, dict):
            continue

        for item in result.get("results", []):
            if isinstance(item, dict):
                sources.append(item)

    return sources


def _handle_deterministic_route(user_query):
    final_response = None
    pending_route_response = try_complete_pending_route(user_query, get_route)
    while (1):
        if pending_route_response is not None:
            print(f"Pending route response: {pending_route_response}")
            final_response = pending_route_response
            break

        route_info = parse_route_query(user_query)
        clarification_message = missing_or_unresolved_message(route_info)
        if route_info["is_route"] and not clarification_message:
            print(f"Parsed route info: {route_info}")
            final_response = handle_route_info_with_context(route_info, get_route)
            break

        continuation_response = handle_route_continuation_query(user_query, get_route)
        if continuation_response is not None:
            print(f"Route continuation response: {continuation_response}")
            final_response = continuation_response
            break

        if route_info["is_route"]:
            print(f"Parsed route info: {route_info}")
            final_response = start_pending_route(route_info)
            break
        break  # Not a route query, exit the loop

    global _captured_route_image
    if final_response and final_response.startswith("Route found:"):
        _captured_route_image = final_response

    return final_response


def _handle_query_core(user_query):
    user_query = (user_query or "").strip()

    deterministic_route_response = _handle_deterministic_route(user_query)
    if deterministic_route_response is not None:
        return deterministic_route_response

    # Add the user's message to the conversation history for the RAG path.
    messages_history.append({"role": "user", "content": user_query})

    try:
        response = get_openai_response(messages_history)

        answer = response.choices[0].message

        tool_calls = getattr(answer, "tool_calls", None) or []
        if not isinstance(tool_calls, (list, tuple)):
            tool_calls = []

        if not tool_calls and getattr(answer, "content", None):
            final_response = strip_unsupported_citation_markers(answer.content)
            messages_history.append({"role": "assistant", "content": final_response})
            return final_response

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
        response = get_openai_response(messages_history)
        final_message = response.choices[0].message
        final_response = getattr(final_message, "content", "")
        final_response = strip_unsupported_citation_markers(final_response)
        final_response = append_sources_section(final_response, collect_search_sources(tool_results))
        final_response = final_message.content or ""

        # If response is blank, provide a helpful fallback
        if not final_response.strip():
            final_response = "I'm having trouble formulating a response. Could you rephrase your question?"

        if (not final_response or any(phrase.lower() in final_response.lower() for phrase in FALLBACK_PHRASES)):
            log_unanswered_questions(user_query)

        # Add the assistant's response to the conversation history for future context
        messages_history.append({"role": "assistant", "content": final_response})

        return final_response

    except Exception as e:
        return f"I hit an error: {e} at line {sys.exc_info()[-1].tb_lineno}"

def format_tool_results_for_prompt(tool_results) -> str:
        prompt_blocks: list[str] = []
        for tool_result in tool_results:
            name = tool_result["name"]
            result = tool_result["result"]

            # CAPTURE IMAGE FROM WALKING DIRECTIONS TOOL
            if name == "get_walking_directions" and isinstance(result, dict):
                if result.get("image"):
                    if DEBUG:
                        print(f"[format_tool_results_for_prompt] Found image in walking directions result, length: {len(result.get('image'))}")
                    # Store image in a global that handle_query_web can access
                    global _captured_route_image
                    _captured_route_image = result.get("image")
                
                lines = [
                    f"Tool: {name}",
                    f"Start: {result.get('start', 'n/a')}",
                    f"End: {result.get('end', 'n/a')}",
                    f"Algorithm: {result.get('algorithm', 'n/a')}",
                    f"Success: {result.get('success', False)}",
                ]

                if result.get("walk_time_minutes") is not None:
                    lines.append(f"Walk time minutes: {result.get('walk_time_minutes'):.1f}")

                if result.get("distance_miles") is not None:
                    lines.append(f"Distance miles: {result.get('distance_miles'):.2f}")

                if result.get("expanded_nodes") is not None:
                    lines.append(f"Expanded nodes: {result.get('expanded_nodes')}")

                if result.get("error"):
                    lines.append(f"Error: {result.get('error')}")

                prompt_blocks.append("\n".join(lines))
                continue

            if isinstance(result, dict) and result.get("results") is not None:
                lines = [
                    f"Tool: {name}",
                    f"Query: {result.get('query', '')}",
                    f"Low confidence: {result.get('low_confidence', False)}",
                ]
                if result.get("error"):
                    lines.append(f"Error: {result.get('error')}")
                for item in result.get("results", [])[:5]:
                    document_name = item.get("document_name") or item.get("title") or "Unknown source"
                    source = item.get("source") or item.get("url") or ""
                    chunk_index = item.get("chunk_index")
                    distance = item.get("distance")
                    evidence = item.get("text") or item.get("evidence_snippet", "")
                    lines.extend(
                        [
                            f"Rank {item.get('rank', '?')} | Source: {document_name}",
                            f"Path or URL: {source}",
                            f"Chunk: {chunk_index if chunk_index is not None else 'n/a'}",
                            f"Distance: {distance if distance is not None else 'n/a'}",
                            f"Evidence: {evidence}",
                        ]
                    )
                prompt_blocks.append("\n".join(lines))
                continue
            prompt_blocks.append(f"Tool: {name}\nResult: {result}")
        return "\n\n".join(prompt_blocks)

def handle_query(user_query):
    return _handle_query_core(user_query)


def handle_query_web(user_query, show_route_map=False):
    global _captured_route_image
    _captured_route_image = None  # Reset for this request
    
    get_client()  # Ensure client is initialized before handling the query

    if not show_route_map:
        return {"response": handle_query(user_query), "route_map_url": None, "image_base64": None}

    static_routes_dir = os.path.join(BASE_DIR, "static", "routes")
    os.makedirs(static_routes_dir, exist_ok=True)
    map_result = {"route_map_url": None, "image_base64": None}

    response = _handle_query_core(user_query)
    
    # Check if image was captured during tool execution
    if _captured_route_image:
        if DEBUG:
            print(f"[handle_query_web] Using captured route image from tool execution, length: {len(_captured_route_image)}")
        map_result["image_base64"] = _captured_route_image
    
    if not (isinstance(response, str) and response.startswith("Route found:")):
        map_result["route_map_url"] = None

    if DEBUG:
        print(f"[handle_query_web] Final response: {response[:100] if response else 'None'}")
        print(f"[handle_query_web] map_result keys: {map_result.keys()}")
        print(f"[handle_query_web] image_base64 present: {bool(map_result.get('image_base64'))}")
        if map_result.get('image_base64'):
            print(f"[handle_query_web] image_base64 length: {len(map_result.get('image_base64'))}")

    return {
        "response": response,
        "route_map_url": map_result["route_map_url"],
        "image_base64": map_result.get("image_base64"),
    }
        
if __name__ == "__main__":
    print(ONBOARDING_MESSAGE)

    while True:
        user_query = input("You: ")

        if user_query.lower() in ["exit", "quit", "goodbye", "stop", "bye"]:
            break

        answer = handle_query(user_query)
        print(f"Assistant: {answer}\n")

