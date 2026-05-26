import os
from dotenv import load_dotenv
from agents import set_tracing_disabled, set_tracing_export_api_key
from patches.patch_agency_swarm_dual_comms import apply_dual_comms_patch
from patches.patch_file_attachment_refs import apply_file_attachment_reference_patch
from patches.patch_ipython_interpreter_composio import apply_ipython_composio_context_patch
from patches.patch_utf8_file_reads import apply_utf8_file_read_patch

load_dotenv()

apply_utf8_file_read_patch()
apply_dual_comms_patch()
apply_file_attachment_reference_patch()
apply_ipython_composio_context_patch()

_tracing_key = os.getenv("OPENAI_API_KEY")
if _tracing_key:
    set_tracing_export_api_key(_tracing_key)
else:
    set_tracing_disabled(True)


def create_agency(load_threads_callback=None):
    from agency_swarm import Agency
    from agency_swarm.tools import Handoff, SendMessage

    from orchestrator import create_orchestrator
    from virtual_assistant import create_virtual_assistant
    from deep_research import create_deep_research
    from data_analyst_agent import create_data_analyst
    from slides_agent import create_slides_agent
    from docs_agent import create_docs_agent
    from video_generation_agent import create_video_generation_agent
    from image_generation_agent import create_image_generation_agent
    # Custom MediConnect medical agents
    from brand_director_agent import create_brand_director
    from creative_director_agent import create_creative_director
    from reel_director_agent import create_reel_director

    orchestrator = create_orchestrator()
    virtual_assistant = create_virtual_assistant()
    deep_research = create_deep_research()
    data_analyst = create_data_analyst()
    slides_agent = create_slides_agent()
    docs_agent = create_docs_agent()
    video_generation_agent = create_video_generation_agent()
    image_generation_agent = create_image_generation_agent()
    brand_director = create_brand_director()
    creative_director = create_creative_director()
    reel_director = create_reel_director()

    all_agents = [
        orchestrator,
        virtual_assistant,
        slides_agent,
        deep_research,
        data_analyst,
        docs_agent,
        video_generation_agent,
        image_generation_agent,
        brand_director,
        creative_director,
        reel_director,
    ]

    send_message_flows = [
        (orchestrator, specialist, SendMessage)
        for specialist in all_agents
        if specialist is not orchestrator
    ]

    # Free handoffs — el Orchestrator + agentes deciden estrategia óptima
    # según contexto. Tools BrowseAssets/StampTextOnImage están disponibles
    # como opción, NO obligatorias. El agente con autoridad elige el camino.
    handoff_flows = [
        (a > b, Handoff)
        for a in all_agents
        for b in all_agents
        if a is not b
    ]

    agency = Agency(
        *all_agents,
        communication_flows=send_message_flows + handoff_flows,
        name="OpenSwarm",
        shared_instructions="shared_instructions.md",
        load_threads_callback=load_threads_callback,
    )

    return agency

if __name__ == "__main__":
    agency = create_agency()
    agency.tui(show_reasoning=True, reload=False)
