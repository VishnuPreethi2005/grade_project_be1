"""Terminal chatbot helpers for the Mini IDE.

Implements three chatbot modes using LangChain + Google Gemini:
- Basic (single question)
- Memory (multi-turn)
- Fitness (system-restricted, multi-turn)

These functions are CLI-safe, and the ChatbotSession class enables
non-blocking use in the terminal websocket.
"""

from __future__ import annotations

import asyncio
from typing import List, Optional, Tuple

from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

FITNESS_SYSTEM_PROMPT = (
    "You are a professional fitness coach.\n\n"
    "You are ONLY allowed to answer questions related to:\n"
    "- Workouts\n"
    "- Exercise\n"
    "- Fat loss\n"
    "- Muscle gain\n"
    "- Diet and nutrition\n"
    "- Healthy habits\n"
    "- Weight training\n"
    "- Home workouts\n\n"
    "If the user asks anything NOT related to fitness, respond:\n"
    "\"I am a fitness coach and can only answer fitness-related questions.\""
)


def _init_llm(model: str):
    """Initialize Gemini chat model via LangChain.

    Uses GOOGLE_API_KEY from the environment implicitly.
    """
    return init_chat_model(model=model, model_provider="google_genai")


def _extract_text(response) -> str:
    if hasattr(response, "content"):
        return response.content or ""
    return str(response)


def _context_prefix(code_context: str) -> str:
    if code_context and code_context.strip():
        return f"Current editor code:\n{code_context}\n"
    return "Current editor code is empty.\n"


def basic_chatbot(code_context: str) -> None:
    """Basic single-question chatbot (CLI)."""
    llm = _init_llm(model="gemini-2.5-flash")
    question = input("You: ").strip()
    if not question or question.lower() == "exit":
        print("Chatbot exited.")
        return
    prompt = f"{_context_prefix(code_context)}\nUser question: {question}"
    response = llm.invoke(prompt)
    print(f"Bot: {_extract_text(response)}")


def memory_chatbot(code_context: str) -> None:
    """Memory chatbot (CLI)."""
    llm = _init_llm(model="gemini-2.5-flash")
    chat_history: List = [HumanMessage(content=_context_prefix(code_context))]
    print("Chatbot started (type exit to stop).")
    while True:
        question = input("You: ").strip()
        if question.lower() == "exit":
            print("Chatbot exited.")
            return
        chat_history.append(HumanMessage(content=question))
        response = llm.invoke(chat_history)
        answer = _extract_text(response)
        chat_history.append(AIMessage(content=answer))
        print(f"Bot: {answer}")


def fitness_chatbot(code_context: str) -> None:
    """Fitness-restricted chatbot (CLI)."""
    llm = _init_llm(model="gemini-2.5-flash")
    chat_history: List = [
        SystemMessage(content=FITNESS_SYSTEM_PROMPT),
        HumanMessage(content=_context_prefix(code_context)),
    ]
    print("Chatbot started (type exit to stop).")
    while True:
        question = input("You: ").strip()
        if question.lower() == "exit":
            print("Chatbot exited.")
            return
        chat_history.append(HumanMessage(content=question))
        response = llm.invoke(chat_history)
        answer = _extract_text(response)
        chat_history.append(AIMessage(content=answer))
        print(f"Bot: {answer}")


class ChatbotSession:
    """Stateful chatbot session for websocket terminal integration."""

    def __init__(self, code_context: str):
        self.code_context = code_context or ""
        self.state = "menu"
        self.mode: Optional[str] = None
        self.llm = None
        self.chat_history: List = []

    @property
    def menu_text(self) -> str:
        return (
            "Select chatbot mode:\r\n"
            "1 - Basic chatbot\r\n"
            "2 - Memory chatbot\r\n"
            "3 - Fitness chatbot\r\n"
            "4 - Exit\r\n"
            "Enter choice: "
        )

    async def handle_line(self, line: str) -> Tuple[str, bool]:
        """Process a single line of input.

        Returns: (output_text, done)
        """
        cleaned = line.strip()
        if self.state == "menu":
            return self._handle_menu(cleaned)

        if self.state == "basic_wait":
            if cleaned.lower() == "exit":
                return "Chatbot exited.\r\n", True
            prompt = f"{_context_prefix(self.code_context)}\nUser question: {cleaned}"
            response = await asyncio.to_thread(self.llm.invoke, prompt)
            answer = _extract_text(response)
            return f"Bot: {answer}\r\n", True

        if self.state in ("memory", "fitness"):
            if cleaned.lower() == "exit":
                return "Chatbot exited.\r\n", True
            self.chat_history.append(HumanMessage(content=cleaned))
            response = await asyncio.to_thread(self.llm.invoke, self.chat_history)
            answer = _extract_text(response)
            self.chat_history.append(AIMessage(content=answer))
            return f"Bot: {answer}\r\n", False

        return "Chatbot exited.\r\n", True

    def _handle_menu(self, choice: str) -> Tuple[str, bool]:
        if choice in ("4", "exit"):
            return "Chatbot exited.\r\n", True

        if choice == "1":
            self.mode = "basic"
            self.llm = _init_llm(model="gemini-2.5-flash")
            self.state = "basic_wait"
            return (
                "Chatbot started (basic).\r\n"
                "Ask one question (type exit to cancel).\r\n",
                False,
            )

        if choice == "2":
            self.mode = "memory"
            self.llm = _init_llm(model="gemini-2.5-flash")
            self.chat_history = [HumanMessage(content=_context_prefix(self.code_context))]
            self.state = "memory"
            return (
                "Chatbot started (memory). Type exit to stop.\r\n"
                "Current editor code loaded as context.\r\n",
                False,
            )

        if choice == "3":
            self.mode = "fitness"
            self.llm = _init_llm(model="gemini-2.5-flash")
            self.chat_history = [
                SystemMessage(content=FITNESS_SYSTEM_PROMPT),
                HumanMessage(content=_context_prefix(self.code_context)),
            ]
            self.state = "fitness"
            return (
                "Chatbot started (fitness). Type exit to stop.\r\n"
                "Current editor code loaded as context.\r\n",
                False,
            )

        return ("Invalid choice.\r\n" + self.menu_text, False)


def run_chatbot_menu(code_context: str) -> ChatbotSession:
    """Create a websocket-compatible chatbot session.

    The caller is responsible for sending menu_text and routing input lines.
    """
    return ChatbotSession(code_context)
