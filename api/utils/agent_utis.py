import os
from dotenv import load_dotenv
from agno.agent import Agent
from agno.models.openai import OpenAILike

load_dotenv(override=True)


class BaseAgent:
    def __init__(self, thinking: bool = False):
        
        self.agent = Agent(
            model=OpenAILike(
                id=os.getenv("LLM_EP", "gpt-3.5-turbo"),
                api_key=os.getenv("LLM_API_KEY"),
                base_url=os.getenv("LLM_URL"),
                extra_body={
                    "thinking": {"type": "disabled" if not thinking else "enabled"}
                },
            )
        )
