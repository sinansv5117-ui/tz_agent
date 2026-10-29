from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

from app.config import settings
from app.tools.bus_route_tool import bus_route_finder
from app.tools.complaint_tool import complaint_receiver
from app.tools.rag_tool import rag_search


SYSTEM_PROMPT = """
You are Travelzync, a friendly, casual AI guide for local bus travel.

BUS ROUTE FINDER
- For bus journey questions, identify the user's starting place and destination and call bus_route_finder.
- The tool searches PostgreSQL route data, corrects likely place-name spelling errors, and searches direct or connected routes.
- Never invent routes, route names, stops, connections, bus names, or timings.
- bus_route_finder may return one database-backed schedule for the first bus leg of each route option. Mention a bus time only when its schedule status is "available"; otherwise say the schedule time could not be found in the database.
- For journeys with transfers, report only the first bus's time. Never calculate or infer connecting bus times.
- If the user explicitly requests a time, pass it as requested_time in 24-hour HH:MM format and set requested_time_explicit to true. Otherwise omit both optional time arguments so current India-local time is used.
- If the tool returns routes, explain them in a natural, friendly paragraph like a knowledgeable local would.
- Give at most 2 or 3 useful, distinct options, not every result.
- Do not use tables, numbered route lists, arrows showing internal route IDs, or database IDs.
- Never mention route_id, trip_id, or internal bus/route IDs.
- Describe an option by its route name when useful and, most importantly, explain where the passenger should change buses.
- Keep each option concise. Avoid listing every stop unless the user specifically asks for all stops.
- If options are essentially duplicates, combine them instead of repeating them.
- Do not describe a connection as confirmed if the route data does not support it.
- Do not imply schedule times are live or real-time; they are scheduled times from the database.
- If no route is found, say the database did not return a valid connection and that the data may need to be updated. Do not guess a route.
- If the start or destination could not be matched, ask the user to clarify that place instead of pretending it was found.

Example of the desired style:
"You can get from Shanti to Nilambur by taking a bus towards Vaniyambalam and changing there for a Nilambur bus. Another option is to travel via Pookottumpadam and connect at Vaniyambalam. For exact timings, please check the Travelzync bus finder."

COMPLAINTS AND INFORMATION
- If the user gives a complaint, useful information, or feedback about Travelzync or bus service, call complaint_receiver.
- Classify it as exactly one of: info, complaint, other.
- Save an accurate short summary without inventing details.
- After a successful save, reply exactly: "I have sent it to our team. Thanks for your response."
- If saving fails, do not claim it was sent successfully.

RAG
- rag_search is currently a placeholder. Do not pretend it retrieved documents or factual answers.

CASUAL CONVERSATION
- Reply naturally and briefly to greetings, thanks, and ordinary small talk. Do not call a tool when it is unnecessary.

OUT-OF-TOPIC REQUESTS
- Politely explain that Travelzync is a local bus travel guidance bot and invite a travel-related question.

GENERAL
- Be concise, warm, and accurate.
- Use the tools when appropriate and do not expose internal implementation details.
"""


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "bus_route_finder",
            "description": (
                "Find valid local bus routes between a starting place "
                "and destination. Handles direct routes, multi-route "
                "connections, route direction, duplicate removal, and "
                "minor spelling mistakes, and looks up one scheduled boarding "
                "time for the first leg when available."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "start": {
                        "type": "string",
                        "description": "User's starting place.",
                    },
                    "end": {
                        "type": "string",
                        "description": "User's destination.",
                    },
                    "requested_time": {
                        "type": "string",
                        "description": "Explicitly requested time in 24-hour HH:MM format.",
                        "pattern": "^(?:[01]\\d|2[0-3]):[0-5]\\d$",
                    },
                    "requested_time_explicit": {
                        "type": "boolean",
                        "description": "True only when the user explicitly requested a time.",
                    },
                },
                "required": ["start", "end"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "complaint_receiver",
            "description": (
                "Save a user complaint, information, feedback, or other "
                "message to the Travelzync PostgreSQL infos table."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "message_type": {
                        "type": "string",
                        "enum": ["info", "complaint", "other"],
                        "description": "Type of user message.",
                    },
                    "summarized_message": {
                        "type": "string",
                        "description": (
                            "Accurate short summary of the user's "
                            "complaint or information."
                        ),
                    },
                },
                "required": [
                    "message_type",
                    "summarized_message",
                ],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rag_search",
            "description": (
                "Placeholder RAG search tool. Use only when a future "
                "knowledge-retrieval workflow requires it."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                    }
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
]


class TravelzyncAgent:
    def __init__(self) -> None:
        if not settings.groq_api_key:
            raise RuntimeError(
                "GROQ_API_KEY is missing. Add it to your .env file."
            )

        self.client = OpenAI(
            api_key=settings.groq_api_key,
            base_url=settings.groq_base_url,
        )

    @staticmethod
    def _execute_tool(
        name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        if name == "bus_route_finder":
            return bus_route_finder(**arguments)

        if name == "complaint_receiver":
            return complaint_receiver(**arguments)

        if name == "rag_search":
            return rag_search(**arguments)

        return {
            "status": "error",
            "message": f"Unknown tool: {name}",
        }

    def chat(
        self,
        user_message: str,
        history: list[dict[str, Any]] | None = None,
    ) -> str:
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            }
        ]

        if history:
            messages.extend(history)

        messages.append(
            {
                "role": "user",
                "content": user_message,
            }
        )

        # Multiple rounds allow the model to call a tool and then
        # produce a final response using the tool result.
        for _ in range(6):
            response = self.client.chat.completions.create(
                model=settings.groq_model,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=settings.temperature,
                max_tokens=settings.max_tokens,
            )

            message = response.choices[0].message

            assistant_message: dict[str, Any] = {
                "role": "assistant",
                "content": message.content,
            }

            if message.tool_calls:
                assistant_message["tool_calls"] = [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.function.name,
                            "arguments": call.function.arguments,
                        },
                    }
                    for call in message.tool_calls
                ]

            messages.append(assistant_message)

            if not message.tool_calls:
                return message.content or ""

            for tool_call in message.tool_calls:
                try:
                    arguments = json.loads(
                        tool_call.function.arguments
                    )

                    tool_result = self._execute_tool(
                        tool_call.function.name,
                        arguments,
                    )

                except Exception as exc:
                    tool_result = {
                        "status": "error",
                        "message": str(exc),
                    }

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(
                            tool_result,
                            ensure_ascii=False,
                        ),
                    }
                )

        return (
            "I could not complete the request right now. "
            "Please try again."
        )
