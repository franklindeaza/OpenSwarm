from agency_swarm import Agent, ModelSettings
from openai.types.shared import Reasoning
from dotenv import load_dotenv

from config import get_default_model, is_openai_provider

load_dotenv()


def create_brand_director() -> Agent:
    return Agent(
        name="Brand Director",
        description=(
            "Senior creative strategist for MediConnect medical agency. "
            "Takes raw doctor topics + brand kit, produces structured creative briefs "
            "(headline, subhead, body, CTA, visual metaphor, mood) ready for the "
            "Creative Director to execute. Spanish RD natural, Ley 42-01 compliant."
        ),
        instructions="./instructions.md",
        tools_folder="./tools",
        model=get_default_model(),
        model_settings=ModelSettings(
            reasoning=Reasoning(effort="medium", summary="auto") if is_openai_provider() else None,
        ),
        conversation_starters=[
            "Brief para Dr. Edward Rijo sobre vista para regreso a clases (post 1:1)",
            "Story 9:16 sobre detección temprana diabetes infantil para pediatra",
            "Reel landscape sobre hipertensión silenciosa para cardiólogo",
            "Carrusel educativo sobre primeros síntomas cáncer de mama",
        ],
    )


if __name__ == "__main__":
    from agency_swarm import Agency
    Agency(create_brand_director()).terminal_demo()
