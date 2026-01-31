from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import os
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from llm_config import initialize_llm
from terraform_tools import get_terraform_tools
from langchain_classic.agents import initialize_agent, AgentType

app = FastAPI(title="LangChain Terraform Agent API")

class ChatRequest(BaseModel):
    message: str
    provider: Optional[str] = "perplexity"
    history: Optional[List[dict]] = []

class ChatResponse(BaseModel):
    response: str
    history: List[dict]

def dict_to_message(m: dict) -> BaseMessage:
    if m["role"] == "user":
        return HumanMessage(content=m["content"])
    return AIMessage(content=m["content"])

def message_to_dict(m: BaseMessage) -> dict:
    if isinstance(m, HumanMessage):
        return {"role": "user", "content": m.content}
    return {"role": "assistant", "content": m.content}

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        provider = request.provider or os.getenv("LLM_PROVIDER", "perplexity")
        llm = initialize_llm(provider, temperature=0)

        tools = get_terraform_tools()

        # Initialize agent with tools
        agent = initialize_agent(
            tools,
            llm,
            agent=AgentType.CHAT_CONVERSATIONAL_REACT_DESCRIPTION,
            verbose=True
        )

        history = [dict_to_message(m) for m in request.history]

        # The agent expects chat_history as a keyword argument in some configurations,
        # or it handles it via the memory. For CHAT_CONVERSATIONAL_REACT_DESCRIPTION,
        # we can pass it in.

        response = agent.run(input=request.message, chat_history=history)

        new_history = request.history + [
            {"role": "user", "content": request.message},
            {"role": "assistant", "content": response}
        ]

        return ChatResponse(response=response, history=new_history)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
