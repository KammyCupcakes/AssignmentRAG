import re
import sys
import os
from openai.types.chat import ChatCompletionFunctionToolParam
from typing import Any
import inspect
import chromadb
from pathlib import Path

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

BEACONNAV_SRC = os.path.join(BASE_DIR, "BeaconNav", "src")

if BEACONNAV_SRC not in sys.path:
    sys.path.insert(0, BEACONNAV_SRC)
    
from BeaconNav.src.main import get_route

DATA_PATH = r"data"
CHROMA_PATH = Path(BASE_DIR) / "chroma_db"
DEBUG = os.getenv("ASSIGNMENTRAG_DEBUG") == "1"

_chroma_client = None
_collection = None


def get_collection():
    global _chroma_client, _collection
    if _collection is None:
        _chroma_client = chromadb.PersistentClient(path=str(CHROMA_PATH))
        _collection = _chroma_client.get_or_create_collection(name="public_transportation")
    return _collection


def search_documents(query: str, max_results: int = 3) -> dict[str, Any]:
    try:
        collection = get_collection()
        results = collection.query(
            query_texts=[query],
            n_results=max_results,
            include=["documents", "metadatas", "distances"],
        )
    except Exception:
        return {
            "query": query,
            "low_confidence": True,
            "results": [],
            "error": (
                "Document search is temporarily unavailable because the local "
                "vector database could not be opened."
            ),
        }

    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    if DEBUG:
        print(f"Search query: '{query}' returned {len(documents)} results.")

    structured_results = []
    for index, document in enumerate(documents):
        metadata = metadatas[index] if index < len(metadatas) and metadatas[index] else {}
        distance = distances[index] if index < len(distances) else None
        structured_results.append(
            {
                "rank": index + 1,
                "text": document,
                "source": metadata.get("source", ""),
                "document_name": metadata.get("document_name", "Unknown source"),
                "source_type": metadata.get("source_type", ""),
                "chunk_index": metadata.get("chunk_index"),
                "distance": distance,
            }
        )

    return {
        "query": query,
        "low_confidence": len(structured_results) == 0,
        "results": structured_results,
    }

def clean_location_text(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    cleaned = re.sub(
        r"\s+(?:using|with)\s+[\w*']+(?:\s+algorithm)?\b.*$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\s+(?:a\s*\*|astar|dijkstra)\s+algorithm\b.*$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    return cleaned.strip(" \t\r\n.,!?;:")

def get_walking_directions(starting_location: str, ending_location: str, algorithm: str = "astar") -> dict[str, Any]:
        starting_location = clean_location_text(starting_location)
        ending_location = clean_location_text(ending_location)
        try:
            route = get_route(starting_location, ending_location, algorithm, show_map=True)

            if not route["success"]:
                    raise RuntimeError(f"Assistant: {route['error']}\n")

            return route
        except Exception as e:
            raise RuntimeError(f"Error getting walking directions: {e}")

SEARCH_DOCUMENTS: ChatCompletionFunctionToolParam = {
    "type": "function",
    "function": {
        "name": "search_documents",
        "description": "Search the SQLite chunk database for retrieval-augmented answers with citations.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The user question or search query.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of search results to return.",
                    "default": 3,
                },
            },
            "required": ["query"],
        },
    },
}

GET_WALKING_DIRECTIONS: ChatCompletionFunctionToolParam = {
    "type": "function",
    "function": {
        "name": "get_walking_directions",
        "description": "Get walking directions between two locations.",
        "parameters": {
            "type": "object",
            "properties": {
                "starting_location": {
                    "type": "string",
                    "description": "The starting location to get directions for.",
                    "default": "Dorms",
                },
                "ending_location": {
                    "type": "string",
                    "description": "The ending location to get directions for.",
                    "default": "Campus Center",
                },
            },
            "required": ["starting_location", "ending_location"],
        },
    },
}

TOOLS: list[ChatCompletionFunctionToolParam] = [SEARCH_DOCUMENTS, GET_WALKING_DIRECTIONS]

TOOL_HANDLERS = {
    "search_documents": search_documents,
    "get_walking_directions": get_walking_directions,
}

def _invoke_handler_with_supported_args(handler: Any, call_arguments: dict[str, Any]) -> Any:
    signature = inspect.signature(handler)
    params = signature.parameters
    accepts_var_kwargs = any(param.kind == inspect.Parameter.VAR_KEYWORD for param in params.values())
    if accepts_var_kwargs:
        return handler(**call_arguments)

    supported_args = {key: value for key, value in call_arguments.items() if key in params}
    return handler(**supported_args)


def execute_tool_call(
    function_name: str,
    function_arguments: dict[str, Any],
    tool_context: dict[str, Any] | None = None,
) -> Any:
    handler = TOOL_HANDLERS.get(function_name)
    if not handler:
        return {"error": f"No handler for tool: {function_name}"}
    try:
        call_arguments = dict(function_arguments or {})
        if tool_context:
            for key, value in tool_context.items():
                call_arguments.setdefault(key, value)
        return _invoke_handler_with_supported_args(handler, call_arguments)
    except Exception as exc:
        return {"error": f"Error executing tool {function_name}: {exc}"}

__all__ = ["TOOLS", "execute_tool_call", "TOOL_HANDLERS"]
