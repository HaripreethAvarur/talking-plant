"""Isolated optional uAgents runtime. This module imports no SDK until explicitly enabled."""

from queue import Empty, Full


def run_worker(configuration, outgoing, messages):
    def report(status, detail):
        try:
            messages.put_nowait((status, detail))
        except Full:
            pass

    try:
        from uagents import Agent, Context, Model

        class PlantSignal(Model):
            schema_version: str = "1.0"
            event_json: str

        agent = Agent(
            name="talking-plant",
            seed=configuration["seed"],
            port=configuration["port"],
            endpoint=[configuration["endpoint"]],
        )

        @agent.on_event("startup")
        async def started(ctx: Context):
            report("enabled", "uAgents worker started; recipient delivery remains to be verified.")

        @agent.on_interval(period=1.0)
        async def send_pending(ctx: Context):
            try:
                event_json = outgoing.get_nowait()
            except Empty:
                return
            try:
                await ctx.send(configuration["target"], PlantSignal(event_json=event_json))
            except Exception:
                report(
                    "enabled", "Send failed; best-effort Fetch delivery does not retry. See backend history."
                )

        agent.run()
    except Exception as exc:
        report("untested", f"uAgents runtime unavailable ({type(exc).__name__}).")
