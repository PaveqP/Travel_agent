import os
import unittest
from uuid import uuid4

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres.aio import AsyncPostgresStore

from travel_agent.graph import build_graph
from test_travel_agent import decide, run


@unittest.skipUnless(os.environ.get('TRAVEL_TEST_DATABASE_URL'), 'Separate PostgreSQL integration mode')
class PostgresTests(unittest.IsolatedAsyncioTestCase):
    async def test_reopen_checkpoint_and_profile(self):
        dsn = os.environ['TRAVEL_TEST_DATABASE_URL']
        ident = str(uuid4())
        config = {'configurable': {'thread_id': ident}}
        async with AsyncPostgresSaver.from_conn_string(dsn) as saver:
            await saver.setup()
            graph = build_graph(decide, run, saver)
            first = await graph.ainvoke({'messages': [HumanMessage(content='Сочи')], 'calls': 0}, config)
            self.assertEqual(first['stage'], 'scenarios')
            first = await graph.ainvoke({'requested_choice': first['choices'][0]['id'], 'calls': 0}, config)
            self.assertEqual(first['status'], 'needs_input')
        async with AsyncPostgresStore.from_conn_string(dsn) as store:
            await store.setup()
            await store.aput(('profiles', ident), 'preferences', {'interests': ['море']})
        async with AsyncPostgresSaver.from_conn_string(dsn) as saver:
            graph = build_graph(decide, run, saver)
            saved = await graph.aget_state(config)
            self.assertEqual(saved.values['constraints']['origin'], 'Москва')
            second = await graph.ainvoke({'messages': [HumanMessage(content='даты')], 'calls': 0, 'attempts': []}, config)
            self.assertEqual(second['stage'], 'transport')
            self.assertTrue(second['choices'])
        async with AsyncPostgresSaver.from_conn_string(dsn) as saver:
            graph = build_graph(decide, run, saver)
            saved = await graph.aget_state(config)
            self.assertEqual(saved.values['revision'], second['revision'])
            self.assertGreaterEqual(len(saved.values['messages']), 4)
        async with AsyncPostgresStore.from_conn_string(dsn) as store:
            profile = await store.aget(('profiles', ident), 'preferences')
            self.assertEqual(profile.value['interests'], ['море'])
            self.assertIsNone(await store.aget(('profiles', 'foreign'), 'preferences'))
