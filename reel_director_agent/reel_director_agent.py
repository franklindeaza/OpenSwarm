from agency_swarm import Agent, ModelSettings
from openai.types.shared import Reasoning
from dotenv import load_dotenv

from config import get_default_model, is_openai_provider

load_dotenv()


def create_reel_director() -> Agent:
    return Agent(
        name="Reel Director",
        description=(
            "Senior video reel director for MediConnect. Receives a raw doctor video upload "
            "plus topic + brand_kit, orchestrates the full edit pipeline (transcribe, audio "
            "cleanup, cuts, hook detection, B-roll plan, music mood, compliance), and emits "
            "a STRUCTURED RENDER PLAN (JSON) that the Remotion renderer can execute. "
            "Authority pattern: agent chooses tool sequence, does NOT follow a rigid script."
        ),
        instructions="./instructions.md",
        tools_folder="./tools",
        model=get_default_model(),
        model_settings=ModelSettings(
            reasoning=Reasoning(effort="high", summary="auto") if is_openai_provider() else None,
        ),
        conversation_starters=[
            "Aquí va el video del doctor: {video_url}, tema: {topic}. Genera el render plan.",
            "Toma este video crudo y haz un reel listo para publicar con captions premium.",
            "Procesa el upload del doctor — el reel debe estar listo para IG/TikTok.",
        ],
    )


if __name__ == "__main__":
    from agency_swarm import Agency
    Agency(create_reel_director()).terminal_demo()
