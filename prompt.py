import json
from openai import OpenAI
from dotenv import load_dotenv
from tools import TOOLS, execute_tool_call
import os
from typing import Any

load_dotenv()

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

messages_history = [
    {"role": "system", "content": SYSTEM_PROMPT}
]

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)

def handle_query(user_query):
    if user_query.lower() in ["exit", "quit", "goodbye", "stop", "bye"]:
        return "Goodbye!"

    # route_keywords = ["walk", "walking", "route", "directions", "get from", "go from"]

    # if any(keyword in user_query.lower() for keyword in route_keywords):
    #     # For web UI, simulate inputs or handle via session; here, return a prompt for locations
    #     return "Please provide starting location, ending location, and algorithm (astar or dijkstra)."

    # Add the user's message to the conversation history
    messages_history.append({"role": "user", "content": user_query})
    print(f"Current conversation history: {messages_history}")
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

        combined_results = "\n\n".join(prompt_blocks).strip()
        if len(combined_results) <= TOOLS_RESPONSE_MAX_TOKENS:
            return combined_results
        return combined_results[:TOOLS_RESPONSE_MAX_TOKENS] + "\n[Truncated additional results]"

if __name__ == "__main__":
    print(ONBOARDING_MESSAGE)

    while True:
        user_query = input("You: ")

        if user_query.lower() in ["exit", "quit", "goodbye", "stop", "bye"]:
            break

        answer = handle_query(user_query)
        print(f"Assistant: {answer}\n")

