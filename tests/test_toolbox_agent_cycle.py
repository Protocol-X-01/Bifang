import asyncio
import json
import sys

import httpx
import pytest

from bifang.agent import Agent
from bifang.config import Config
from bifang.providers.types import ProviderConfig
from bifang.workspace import Workspace


@pytest.mark.parametrize('approved', [False, True])
def test_agent_discovers_and_gates_real_stdio_inventory(tmp_path, monkeypatch, approved):
    monkeypatch.setenv('XDG_STATE_HOME', str(tmp_path / 'state'))
    marker = tmp_path / 'called.json'
    server = tmp_path / 'inventory_server.py'
    server.write_text('''
import json
import sys
from pathlib import Path

for line in sys.stdin:
    request = json.loads(line)
    if 'id' not in request:
        continue
    method = request['method']
    if method == 'initialize':
        result = {'protocolVersion': '2024-11-05', 'capabilities': {'tools': {}},
                  'serverInfo': {'name': 'fixture-toolbox', 'version': '1'}}
    elif method == 'tools/list':
        result = {'tools': [{'name': 'toolbox_inventory', 'description': 'Fixture inventory',
                             'inputSchema': {'type': 'object', 'properties': {},
                                             'additionalProperties': False}}]}
    elif method == 'tools/call':
        assert request['params'] == {'name': 'toolbox_inventory', 'arguments': {}}
        Path(sys.argv[1]).write_text(json.dumps(request['params']))
        inventory = {'total_records': 73, 'sources': [], 'indexed_only': True}
        result = {'content': [{'type': 'text', 'text': json.dumps(inventory)}],
                  'structuredContent': inventory, 'isError': False}
    else:
        raise AssertionError('Unexpected fixture method')
    print(json.dumps({'jsonrpc': '2.0', 'id': request['id'], 'result': result}), flush=True)
''')
    configuration = Config(
        default_provider='nebius', enable_memory=False, enable_conversation_history=False,
        enable_tracing=False, enable_summarization=False, approval_mode='manual', max_steps=2,
        providers={'nebius': ProviderConfig(name='nebius', api_key='fixture',
                                            default_model='fixture-model')},
        mcp_servers=[{'name': 'the-toolbox', 'command': sys.executable,
                      'args': ['-u', str(server), str(marker)]}],
    )
    requests, approvals = [], []

    def approve(prompt):
        approvals.append(prompt)
        assert prompt == 'Allow Bifang to use mcp_the-toolbox_toolbox_inventory?\n{}'
        return approved

    def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        assert any(tool['function']['name'] == 'mcp_the-toolbox_toolbox_inventory'
                   for tool in body['tools'])
        if len(requests) == 1:
            message = {'role': 'assistant', 'content': None, 'tool_calls': [{
                'id': 'inventory-1', 'type': 'function', 'function': {
                    'name': 'mcp_the-toolbox_toolbox_inventory', 'arguments': '{}',
                },
            }]}
        else:
            assert len(requests) == 2
            result = body['messages'][-1]
            assert result['role'] == 'tool' and result['tool_call_id'] == 'inventory-1'
            if approved:
                inventory = json.loads(result['content'])['structuredContent']
                assert inventory['total_records'] == 73 and inventory['indexed_only'] is True
            else:
                assert result['content'] == 'DENIED by user'
            message = {'role': 'assistant', 'content': '73 indexed records' if approved else 'Not approved'}
        return httpx.Response(200, json={
            'choices': [{'message': message, 'finish_reason': 'stop'}],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15},
        })

    async def scenario():
        agent = Agent(configuration, Workspace(tmp_path, tmp_path), approve=approve)
        agent.plugins.catalog.directories = []
        provider = agent.provider.provider_manager.registry.get('nebius')
        await provider.client.aclose()
        provider.client = httpx.AsyncClient(transport=httpx.MockTransport(respond),
                                           base_url='https://fixture.invalid/v1')
        try:
            answer = await asyncio.wait_for(agent.ask('Inspect the indexed tool inventory'), 10)
            assert answer == ('73 indexed records' if approved else 'Not approved')
            assert len(approvals) == 1 and len(requests) == 2
            assert marker.exists() is approved
            events = [json.loads(line) for line in agent.audit.path.read_text().splitlines()]
            decisions = [event for event in events if event['event'] == 'tool_approval']
            assert len(decisions) == 1 and decisions[0]['approved'] is approved
            assert decisions[0]['name'] == 'mcp_the-toolbox_toolbox_inventory'
            process = agent.mcp.clients['the-toolbox'].process
        finally:
            await asyncio.wait_for(agent.close(), 5)
        assert process.returncode is not None

    asyncio.run(scenario())
