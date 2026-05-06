import json
import re
from openai import OpenAI
from dotenv import load_dotenv
from tools import TOOLS, execute_tool_call
import os
from typing import Any
import sys
import uuid
from navigation_flow import missing_or_unresolved_message, _route_image_context
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
    "When do shuttle busses run?",
    "How do I get from West Garage to Campus center?",
    "How much does it cost to get a parking permit for the semester?",
]
TOOLS_RESPONSE_MAX_TOKENS = 3000
MAX_TOOL_ROUNDS = 3
DEBUG = os.getenv("ASSIGNMENTRAG_DEBUG") == "1"

TOOL_REPROMPT_TEMPLATE = """Tool call results:
{tool_results}

Incorporate these results into your next response to the user, using them as needed to answer the user's question.
Do not include bracketed source markers in the answer text. The app will add a Sources section when public web sources are available.
If low confidence is False and at least one result is present, provide a direct answer from the top-ranked evidence and do not say you lack information.
IMPORTANT: Only use results that actually contain information relevant to the query. If a result only contains generic location information 
(like a standard campus address with no other details), do not use it unless it directly answers the question. 
Do not guess or infer beyond what is explicitly stated in the evidence.
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

# Removed global _captured_route_image - now passed through return values

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

    return re.sub(r"\s*\u3010[^\u3011]*\u2020source\u3011", "", answer)




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


def collect_search_citations(tool_results: list[dict]) -> list[dict]:
    citations = []
    seen = set()

    for source_info in collect_search_sources(tool_results):
        document_name = str(source_info.get("document_name") or "").strip() or "Unknown source"
        source_value = str(source_info.get("source") or "").strip()
        if not source_value:
            continue

        citation_key = (document_name, source_value)

        if citation_key in seen:
            continue
        seen.add(citation_key)

        citations.append({"document_name": document_name, "source": source_value})

    return citations


def is_boilerplate_content(text: str, query: str) -> bool:
    """
    Detect if text is likely boilerplate/footer content that's not relevant to the query.
    Common pattern: just an address with no substantive query-related content.
    """
    if not text:
        return False
    
    # Check if it's just the standard UMass Boston address repeated
    text_lower = text.lower().strip()
    if "100 morrissey" in text_lower or "morrissey blvd" in text_lower:
        # If it's ONLY the address (maybe with some formatting), it's boilerplate
        # Allow it through if there's substantial other content
        words = text_lower.split()
        if len(words) < 15:  # Short text containing the address is likely just the footer
            # Check if query terms appear in the text
            query_terms = set(query.lower().split())
            text_terms = set(text_lower.split())
            matching_terms = query_terms & text_terms
            if len(matching_terms) < 2:  # Very few query terms = boilerplate
                return True
    
    return False


def _handle_deterministic_route(user_query):
    """Handle deterministic route queries. Returns response text or None. Image captured in context variable."""
    pending_route_response = try_complete_pending_route(user_query, get_route)
    while (1):
        if pending_route_response is not None:
            if DEBUG:
                print(f"Pending route response: {pending_route_response}")
            return pending_route_response

        route_info = parse_route_query(user_query)
        clarification_message = missing_or_unresolved_message(route_info)
        if route_info["is_route"] and not clarification_message:
            if DEBUG:
                print(f"Parsed route info: {route_info}")
            return handle_route_info_with_context(route_info, get_route)

        continuation_response = handle_route_continuation_query(user_query, get_route)
        if continuation_response is not None:
            if DEBUG:
                print(f"Route continuation response: {continuation_response}")
            return continuation_response

        if route_info["is_route"]:
            if DEBUG:
                print(f"Parsed route info: {route_info}")
            return start_pending_route(route_info)
        
        return None  # Not a route query


def _handle_query_core(user_query):
    """Core query handler. Returns dict with 'response' and 'image' keys."""
    user_query = (user_query or "").strip()

    deterministic_route_result = _handle_deterministic_route(user_query)
    if deterministic_route_result is not None:
        # Route was handled; image (if any) is captured in context variable
        route_image = _route_image_context.get()
        return {"response": deterministic_route_result, "image": route_image}

    # Add the user's message to the conversation history for the RAG path.
    messages_history.append({"role": "user", "content": user_query})

    try:
        tool_results: list[dict[str, Any]] = []
        final_response = ""

        for _ in range(MAX_TOOL_ROUNDS):
            response = get_openai_response(messages_history)
            answer = response.choices[0].message

            tool_calls = getattr(answer, "tool_calls", None) or []
            if not isinstance(tool_calls, (list, tuple)):
                tool_calls = []

            if not tool_calls:
                final_response = strip_unsupported_citation_markers(getattr(answer, "content", "") or "")
                if final_response and final_response.strip():
                    break

                messages_history.append({
                    "role": "system",
                    "content": "Provide a direct, non-empty answer using the available context. Do not return an empty response.",
                })
                continue

            round_tool_results: list[dict[str, Any]] = []
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
                    round_tool_results.append(
                        {
                            "name": function_name,
                            "arguments": arguments,
                            "result": tool_result,
                        }
                    )
                except Exception as e:
                    round_tool_results.append(
                        {
                            "name": function_name,
                            "arguments": arguments,
                            "result": {"error": f"Error executing tool {function_name}: {str(e)}"},
                        }
                    )

            tool_results.extend(round_tool_results)

            formatted_results = format_tool_results_for_prompt(round_tool_results)
            generated_reprompt = TOOL_REPROMPT_TEMPLATE.format(tool_results=formatted_results["text"])
            messages_history.append({"role": "system", "content": generated_reprompt})

        citations = collect_search_citations(tool_results)

        # If response is blank, provide a helpful fallback
        if not final_response.strip():
            final_response = "I'm having trouble formulating a response from the available results. Could you rephrase your question?"

        if (not final_response or any(phrase.lower() in final_response.lower() for phrase in FALLBACK_PHRASES)):
            log_unanswered_questions(user_query)

        # Add the assistant's response to the conversation history for future context
        messages_history.append({"role": "assistant", "content": final_response})

        return {
            "response": final_response,
            "image": formatted_results.get("image") if 'formatted_results' in locals() else None,
            "citations": citations,
        }

    except Exception as e:
        error_msg = f"I hit an error: {e} at line {sys.exc_info()[-1].tb_lineno}"
        return {"response": error_msg, "image": None, "citations": []}

def format_tool_results_for_prompt(tool_results) -> dict:
        """Format tool results for LLM. Returns dict with 'text' (formatted results) and 'image' (captured route image or None)."""
        prompt_blocks: list[str] = []
        captured_image = None
        
        for tool_result in tool_results:
            name = tool_result["name"]
            result = tool_result["result"]

            # CAPTURE IMAGE FROM WALKING DIRECTIONS TOOL
            if name == "get_walking_directions" and isinstance(result, dict):
                if result.get("image"):
                    if DEBUG:
                        print(f"[format_tool_results_for_prompt] Found image in walking directions result, length: {len(result.get('image'))}")
                    captured_image = result.get("image")
                
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
                
                # Filter out boilerplate results
                query = result.get("query", "")
                filtered_results = [
                    item for item in result.get("results", [])
                    if not is_boilerplate_content(item.get("text", ""), query)
                ]
                
                for item in filtered_results:
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
                
                # If all results were filtered out, add a note
                if not filtered_results and result.get("results"):
                    lines.append("Note: All results were boilerplate or insufficient content.")
                
                prompt_blocks.append("\n".join(lines))
                continue
            prompt_blocks.append(f"Tool: {name}\nResult: {result}")
        
        return {
            "text": "\n\n".join(prompt_blocks),
            "image": captured_image
        }

def handle_query(user_query):
    """CLI interface - returns just the response text."""
    result = _handle_query_core(user_query)
    return result["response"]


def handle_query_web(user_query, show_route_map=False):
    """Web interface - returns response, route map URL, and base64 image if available."""
    get_client()  # Ensure client is initialized before handling the query

    result_dict = _handle_query_core(user_query)
    response = result_dict["response"]
    image_data = result_dict.get("image") if show_route_map else None
    
    if DEBUG:
        print(f"[handle_query_web] Final response: {response[:100] if response else 'None'}")
        print(f"[handle_query_web] image_base64 present: {bool(image_data)}")
        if image_data:
            print(f"[handle_query_web] image_base64 length: {len(image_data)}")

    return {
        "response": response,
        "image_base64": image_data,
        "citations": result_dict.get("citations", []),
    }
        
if __name__ == "__main__":
    print(ONBOARDING_MESSAGE)

    while True:
        user_query = input("You: ")

        if user_query.lower() in ["exit", "quit", "goodbye", "stop", "bye"]:
            break

        answer = handle_query(user_query)
        print(f"Assistant: {answer}\n")

