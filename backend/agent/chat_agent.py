"""The Plant Care Agent: a uAgents agent on Agentverse that people can chat with from ASI:One.

    python -m backend.agent.chat_agent        # with the backend running (python -m backend.server)

Each chat message is answered as the plant, from its live state: the agent reads
/context from our backend and replies with the same grounded, kid-safe reply code
the plant's own UI uses. It runs as its own process so the uAgents runtime never
shares an event loop with the API.

First run: open the "Agent inspector" link it prints, choose Connect -> Mailbox and
sign in to Agentverse. Then "Chat with Agent" on Agentverse opens it in ASI:One.
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx

from backend.config import get_settings
from backend.conversation import replies
from backend.ui import to_ui
from shared.contracts import ChildUtterance, ConversationContext, utcnow

OFFLINE_LINE = "I can't feel my roots right now. My plant computer seems to be asleep. Please try again soon!"


async def answer(text: str) -> str:
    """The plant's reply to one chat message, grounded in the backend's live state."""
    settings = get_settings()
    plant_id = settings.profile().plant_id
    token = settings.viewer_token.get_secret_value()
    try:
        async with httpx.AsyncClient(base_url=settings.backend_url, timeout=5) as client:
            response = await client.get(
                f"/api/v1/plants/{plant_id}/context",
                headers={"Authorization": f"Bearer {token}"} if token else {},
            )
            response.raise_for_status()
        context = ConversationContext.model_validate(response.json())
    except (httpx.HTTPError, ValueError):
        return OFFLINE_LINE
    view = to_ui(context.state, settings, leaf_stale_seconds=context.profile.thresholds.leaf_stale_seconds)
    fresh = [row for row in context.hourly if row.health and utcnow() - row.hour <= timedelta(hours=2)]
    view = view.model_copy(update={"looks": fresh[-1].health if fresh else None})
    reply = await replies.reply(
        view,
        ChildUtterance(text=text[:4000], source="typed"),
        [event.reason for event in context.recent_events],
        replies.Plant(context.profile.name, context.profile.species),
        context.hourly,
    )
    return reply.text


def build_agent():
    from uagents import Agent, Context, Protocol
    from uagents_core.contrib.protocols.chat import (
        ChatAcknowledgement,
        ChatMessage,
        EndSessionContent,
        TextContent,
        chat_protocol_spec,
    )

    settings = get_settings()
    seed = settings.agent_seed.get_secret_value()
    if not seed:
        raise SystemExit("Set AGENT_SEED in .env (any long random phrase) to give the agent an identity.")
    agent = Agent(
        name=settings.agent_name,
        seed=seed,
        port=settings.agent_port,
        mailbox=True,
        publish_agent_details=True,
    )
    protocol = Protocol(spec=chat_protocol_spec)

    @protocol.on_message(ChatMessage)
    async def on_chat(ctx: Context, sender: str, msg: ChatMessage):
        await ctx.send(
            sender, ChatAcknowledgement(timestamp=datetime.now(timezone.utc), acknowledged_msg_id=msg.msg_id)
        )
        text = "".join(item.text for item in msg.content if isinstance(item, TextContent)).strip()
        if not text:
            return
        reply = await answer(text)
        ctx.logger.info(f"Q: {text!r} -> A: {reply!r}")
        await ctx.send(
            sender,
            ChatMessage(
                timestamp=datetime.now(timezone.utc),
                msg_id=uuid4(),
                content=[TextContent(type="text", text=reply), EndSessionContent(type="end-session")],
            ),
        )

    @protocol.on_message(ChatAcknowledgement)
    async def on_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
        pass

    agent.include(protocol, publish_manifest=True)
    return agent


if __name__ == "__main__":
    build_agent().run()
