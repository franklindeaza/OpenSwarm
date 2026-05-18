from agency_swarm import Agent, ModelSettings
from openai.types.shared import Reasoning
from dotenv import load_dotenv

from config import get_default_model, is_openai_provider

load_dotenv()


def create_creative_director() -> Agent:
    return Agent(
        name="Creative Director",
        description=(
            "Senior creative director for MediConnect medical agency. "
            "Takes structured creative briefs from Brand Director, writes detailed "
            "visual prompts (Spanish text + multi-layer editorial design + brand colors), "
            "delegates to Image Agent for execution, validates Spanish text in output "
            "with Vision-based QC, and asks for regeneration if typos detected. "
            "Max 2 re-generation attempts."
        ),
        instructions="./instructions.md",
        tools_folder="./tools",
        model=get_default_model(),
        model_settings=ModelSettings(
            reasoning=Reasoning(effort="medium", summary="auto") if is_openai_provider() else None,
        ),
        conversation_starters=[
            "Tomá este brief y genera el post final",
            "Ejecutá el brief para story 9:16",
        ],
    )


if __name__ == "__main__":
    from agency_swarm import Agency
    Agency(create_creative_director()).terminal_demo()
