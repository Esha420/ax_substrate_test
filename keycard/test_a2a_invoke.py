#!/usr/bin/env python3
import asyncio
import sys
import uvicorn
from pathlib import Path

# Add official A2A samples agent path
A2A_SAMPLES_DIR = Path(__file__).resolve().parent / "a2a-samples/samples/python/agents/helloworld"
sys.path.insert(0, str(A2A_SAMPLES_DIR))

from agent_executor import HelloWorldAgentExecutor
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.agent_execution import RequestContext
from a2a.server.events import EventQueue
from a2a.helpers import get_message_text, new_task_from_user_message, new_text_message
from a2a.server.tasks import TaskUpdater
from a2a.types import TaskState

from keycardai.a2a import (
    AgentServiceConfig, DelegationClient, KeycardServerCallContextBuilder, 
    build_agent_card_from_config, keycard_user
)
from keycardai.starlette import AuthProvider, KeycardAuthBackend, keycard_on_error
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.authentication import AuthenticationMiddleware

# Reuse HelloWorldAgentExecutor, but log Keycard verified caller
class KeycardAwareHelloWorldExecutor(HelloWorldAgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        caller = keycard_user(context)
        query = get_message_text(context.message)
        
        if context.current_task:
            task = context.current_task
        else:
            task = new_task_from_user_message(context.message)
            await event_queue.enqueue_event(task)

        task_updater = TaskUpdater(event_queue=event_queue, task_id=task.id, context_id=task.context_id)
        
        caller_info = f"Caller: {caller.client_id}, On behalf of: {caller.sub}" if caller else "Unauthenticated"
        print(f"[Agent B Executor] Received task ({query}) from {caller_info}")
        
        resp_text = f"Hello! Processed '{query}'. [{caller_info}]"
        await task_updater.update_status(
            state=TaskState.TASK_STATE_COMPLETED,
            message=new_text_message(resp_text)
        )

# Agent B (Server) Configuration
agent_b_cfg = AgentServiceConfig(
    service_name='HelloWorldDefender',
    client_id='agent-b',
    client_secret='secret-b',
    identity_url='http://127.0.0.1:9002',
    zone_id='default',
    authorization_server_url='http://127.0.0.1:8088',
    capabilities=['echo', 'triage']
)
card = build_agent_card_from_config(agent_b_cfg)
handler = DefaultRequestHandler(
    agent_executor=KeycardAwareHelloWorldExecutor(),
    task_store=InMemoryTaskStore(),
    agent_card=card
)

auth_provider = AuthProvider(zone_url='http://127.0.0.1:8088', server_url='http://127.0.0.1:9002')
verifier = auth_provider.get_token_verifier()
# Keycard Auth Backend that allows public Agent Card discovery
class AgentAuthBackend(KeycardAuthBackend):
    async def authenticate(self, conn):
        if conn.url.path.endswith("agent-card.json"):
            return None
        return await super().authenticate(conn)

auth_backend = AgentAuthBackend(verifier, require_authentication=True)

routes = create_agent_card_routes(card) + create_jsonrpc_routes(
    handler, rpc_url='/a2a/jsonrpc', context_builder=KeycardServerCallContextBuilder()
)
app = Starlette(
    routes=routes,
    middleware=[Middleware(AuthenticationMiddleware, backend=auth_backend, on_error=keycard_on_error)]
)

async def run_test():
    # Start server in background
    config = uvicorn.Config(app, host="127.0.0.1", port=9002, log_level="warning")
    server = uvicorn.Server(config)
    server_task = asyncio.create_task(server.serve())
    await asyncio.sleep(0.5)

    try:
        # Agent A (Caller) Configuration
        agent_a_cfg = AgentServiceConfig(
            service_name='OrchestratorAgent',
            client_id='agent-a',
            client_secret='secret-a',
            identity_url='http://127.0.0.1:9001',
            zone_id='default',
            authorization_server_url='http://127.0.0.1:8088'
        )
        client = DelegationClient(agent_a_cfg)

        # 1. Discover service
        print("1. Discovering Agent B via A2A Agent Card...")
        discovered_card = await client.discover_service("http://127.0.0.1:9002")
        print(f"✓ Discovered service: {discovered_card.get('name')}")

        # 2. Token exchange & invoke service
        print("\n2. Exchanging token for Agent B and invoking task...")
        # Simulate initial user session token for Alice
        import urllib.request, json
        req = urllib.request.Request(
            "http://127.0.0.1:8088/oauth/token",
            data=json.dumps({"grant_type": "client_credentials", "client_id": "agent-a", "user_id": "alice", "scope": "support:read tasks:delegate"}).encode(),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as resp:
            alice_token = json.loads(resp.read().decode())["access_token"]

        result = await client.invoke_service(
            "http://127.0.0.1:9002",
            {"task": "Analyze suspicious account #4821"},
            subject_token=alice_token
        )
        print("✓ Received result from Agent B:")
        print(" ", result)

        await client.close()
    finally:
        server.should_exit = True
        await server_task

if __name__ == "__main__":
    asyncio.run(run_test())
