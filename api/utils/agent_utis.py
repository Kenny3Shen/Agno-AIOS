from dotenv import load_dotenv
from agno.agent import Agent
from agno.models.openai import OpenAILike
from api.services.model_config_service import get_model_for_run

load_dotenv(override=True)


class BaseAgent:
    def __init__(self, thinking: bool = False, model_id: str | None = None):
        model = get_model_for_run(model_id)
        self.agent = Agent(
            model=OpenAILike(
                id=model["model_id"],
                api_key=model["api_key"],
                base_url=model["base_url"],
                extra_body={
                    "thinking": {"type": "disabled" if not thinking else "enabled"}
                },
            )
        )
