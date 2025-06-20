import os
import json
from typing import List
from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam
from pydantic import BaseModel
from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.responses import StreamingResponse
from openai import OpenAI
from .utils.prompt import ClientMessage, convert_to_openai_messages
from .utils.tools import get_report


# Load environment variables from .env for local development
load_dotenv(".env")

app = FastAPI()

client = OpenAI(
    api_key=os.environ.get("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1",
)


class Request(BaseModel):
    messages: List[ClientMessage]


available_tools = {
    "get_report": get_report,
}


def do_stream(messages: List[ChatCompletionMessageParam]):
    stream = client.chat.completions.create(
        messages=messages,
        model="openai/gpt-4o-mini",
        stream=True,
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "get_report",
                    "description": "Fetch a ranked Adobe Analytics report for a given metric(s), dimension, and date range via OAuth",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "metrics": {
                                "description": "One or more metric IDs to include in the report; can be a single string, a dict with an 'id' key, or a list of such dicts",
                                "anyOf": [
                                    {"type": "string"},
                                    {
                                        "type": "object",
                                        "properties": {
                                            "id": {
                                                "type": "string",
                                                "description": "Metric identifier",
                                            }
                                        },
                                        "required": ["id"],
                                    },
                                    {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "id": {
                                                    "type": "string",
                                                    "description": "Metric identifier",
                                                }
                                            },
                                            "required": ["id"],
                                        },
                                    },
                                ],
                            },
                            "dimension": {
                                "type": "string",
                                "description": "The dimension ID to break the report down by",
                            },
                            "start_date": {
                                "type": "string",
                                "description": "Start date for the report in YYYY-MM-DD format",
                            },
                            "end_date": {
                                "type": "string",
                                "description": "End date for the report in YYYY-MM-DD format",
                            },
                        },
                        "required": ["metrics", "dimension", "start_date", "end_date"],
                    },
                },
            }
        ],
    )

    return stream


def stream_text(messages: List[ChatCompletionMessageParam], protocol: str = "data"):
    draft_tool_calls = []
    draft_tool_calls_index = -1

    stream = client.chat.completions.create(
        messages=messages,
        model="openai/gpt-4o-mini",
        stream=True,
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "get_report",
                    "description": "Fetch a ranked Adobe Analytics report for a given metric(s), dimension, and date range via OAuth",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "metrics": {
                                "description": "One or more metric IDs to include in the report; can be a single string, a dict with an 'id' key, or a list of such dicts",
                                "anyOf": [
                                    {"type": "string"},
                                    {
                                        "type": "object",
                                        "properties": {
                                            "id": {
                                                "type": "string",
                                                "description": "Metric identifier",
                                            }
                                        },
                                        "required": ["id"],
                                    },
                                    {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "id": {
                                                    "type": "string",
                                                    "description": "Metric identifier",
                                                }
                                            },
                                            "required": ["id"],
                                        },
                                    },
                                ],
                            },
                            "dimension": {
                                "type": "string",
                                "description": "The dimension ID to break the report down by",
                            },
                            "start_date": {
                                "type": "string",
                                "description": "Start date for the report in YYYY-MM-DD format",
                            },
                            "end_date": {
                                "type": "string",
                                "description": "End date for the report in YYYY-MM-DD format",
                            },
                        },
                        "required": ["metrics", "dimension", "start_date", "end_date"],
                    },
                },
            }
        ],
    )

    for chunk in stream:
        for choice in chunk.choices:
            if choice.finish_reason == "stop":
                continue

            elif choice.finish_reason == "tool_calls":
                for tool_call in draft_tool_calls:
                    yield '9:{{"toolCallId":"{id}","toolName":"{name}","args":{args}}}\n'.format(
                        id=tool_call["id"],
                        name=tool_call["name"],
                        args=tool_call["arguments"],
                    )

                for tool_call in draft_tool_calls:
                    tool_result = available_tools[tool_call["name"]](
                        **json.loads(tool_call["arguments"])
                    )

                    yield 'a:{{"toolCallId":"{id}","toolName":"{name}","args":{args},"result":{result}}}\n'.format(
                        id=tool_call["id"],
                        name=tool_call["name"],
                        args=tool_call["arguments"],
                        result=json.dumps(tool_result),
                    )

            elif choice.delta.tool_calls:
                for tool_call in choice.delta.tool_calls:
                    id = tool_call.id
                    name = tool_call.function.name
                    arguments = tool_call.function.arguments

                    if id is not None:
                        draft_tool_calls_index += 1
                        draft_tool_calls.append(
                            {"id": id, "name": name, "arguments": ""}
                        )

                    else:
                        draft_tool_calls[draft_tool_calls_index][
                            "arguments"
                        ] += arguments

            else:
                yield "0:{text}\n".format(text=json.dumps(choice.delta.content))

        if chunk.choices == []:
            usage = chunk.usage
            prompt_tokens = usage.prompt_tokens
            completion_tokens = usage.completion_tokens

            yield 'e:{{"finishReason":"{reason}","usage":{{"promptTokens":{prompt},"completionTokens":{completion}}},"isContinued":false}}\n'.format(
                reason="tool-calls" if len(draft_tool_calls) > 0 else "stop",
                prompt=prompt_tokens,
                completion=completion_tokens,
            )


@app.post("/api/chat")
async def handle_chat_data(request: Request, protocol: str = Query("data")):
    messages = request.messages
    openai_messages = convert_to_openai_messages(messages)

    response = StreamingResponse(stream_text(openai_messages, protocol))
    response.headers["x-vercel-ai-data-stream"] = "v1"
    return response
