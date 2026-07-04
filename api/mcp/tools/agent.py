# import re
# from agno.run.agent import RunEvent
# from typing import Any, AsyncIterator, cast
# from agno.models.openai import OpenAILike
# from agno.agent import Agent, RunOutput
# from agno.skills import Skills, LocalSkills
# from textwrap import dedent
# import os
from fastmcp import FastMCP

agent_mcp = FastMCP("Agent")
