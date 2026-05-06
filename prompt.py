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

# Global to store captured route image across tool execution
_captured_route_image = None

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


def _handle_query_core(user_query):
    user_query = (user_query or "").strip()

    # Add the user's message to the conversation history
    messages_history.append({"role": "user", "content": user_query})

    # pending_route_response = try_complete_pending_route(user_query, route_getter)
    # print(f"Pending route response: {pending_route_response}")  # Debug print to see if pending route is being triggered
    # if pending_route_response is not None:
    #     return pending_route_response

    try:
        response = client.chat.completions.create(
            model="openai/gpt-oss-120b:free",
            messages = messages_history, # Passing all history here
            tools=TOOLS,
        )

        answer = response.choices[0].message

        tool_calls = answer.tool_calls or []
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
        final_response = final_message.content

        if (not final_response or any(phrase.lower() in final_response.lower() for phrase in FALLBACK_PHRASES)):
            log_unanswered_questions(user_query)

        # Add the assistant's response to the conversation history for future context
        messages_history.append({"role": "assistant", "content": final_response})

        return final_response

    except Exception as e:
        return f"I hit an error: {e}"

def format_tool_results_for_prompt(tool_results) -> str:
        prompt_blocks: list[str] = []
        for tool_result in tool_results:
            name = tool_result["name"]
            result = tool_result["result"]

            # CAPTURE IMAGE FROM WALKING DIRECTIONS TOOL
            if name == "get_walking_directions" and isinstance(result, dict):
                if result.get("image"):
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
        return "\n\n".join(prompt_blocks)

def handle_query(user_query):
    return _handle_query_core(user_query, get_route)


def handle_query_web(user_query, show_route_map=False):
    global _captured_route_image
    _captured_route_image = None  # Reset for this request
    
    if not show_route_map:
        return {"response": handle_query(user_query), "route_map_url": None, "image_base64": None}

    static_routes_dir = os.path.join(BASE_DIR, "static", "routes")
    os.makedirs(static_routes_dir, exist_ok=True)
    map_result = {"route_map_url": None, "image_base64": None}



    response = _handle_query_core(user_query)
    
    # Check if image was captured during tool execution
    if _captured_route_image:
        print(f"[handle_query_web] Using captured route image from tool execution, length: {len(_captured_route_image)}")
        map_result["image_base64"] = _captured_route_image
    
    if not (isinstance(response, str) and response.startswith("Route found:")):
        map_result["route_map_url"] = None

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

