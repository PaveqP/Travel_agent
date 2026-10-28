import asyncio
import hashlib
import json
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from langgraph.checkpoint.memory import InMemorySaver

from travel_agent.api import create_app
from travel_agent.graph import build_graph
from travel_agent.schemas import ResearchResult, TripDelta, TurnPlan, WebEvidence
from travel_agent.telegram import TelegramBot, TelegramError
from test_autonomous_planning import ROLES, result, task
from test_travel_agent import TRIP, agreed_state


class TelegramFlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.user = hashlib.sha256(b'test').hexdigest()
        self.saved = {}
        self.sent = []

        async def bot_state(chat_id, trip_id=None, action=None, *, write=False):
            if write:
                self.saved[chat_id] = (trip_id, action)
            return self.saved.get(chat_id, (None, None))

        self.accounts = SimpleNamespace(bot_state=AsyncMock(side_effect=bot_state), account=AsyncMock(return_value=None),
                                        authenticate=AsyncMock(return_value=None), telegram_owner=AsyncMock(return_value=self.user),
                                        session=AsyncMock(return_value='test'), revoke=AsyncMock())
        self.runners = {}
        for role in ROLES:
            async def run(trip, revision, goal, previous, role=role):
                found = result(role, trip, revision)
                if role == 'stays':
                    for item in found.candidates:
                        item.photos = ['https://photos.example.org/' + item.id + '.jpg']
                        item.amenities = ['Бассейн', 'Wi-Fi']
                        item.address = 'Сочи, Курортный проспект, 1'
                return found
            self.runners[role] = AsyncMock(side_effect=run)

        async def decide(state):
            text = state['messages'][-1].content
            if 'Проверь' in text:
                return TurnPlan(action='research', research_role='stays', reply='Уточни услуги отеля')
            if 'Сколько' in text:
                return TurnPlan(action='answer', reply='Известная сумма включает билеты и отель. Питание оплачивается отдельно.')
            focus = 'stays' if text.startswith('Подбери только отели') else 'transport' if text.startswith('Подбери только билеты') else 'trip'
            return TurnPlan(action='plan', focus=focus, patch=TripDelta(**TRIP.model_dump(exclude={'clear'})),
                            tasks=[task(role) for role in (ROLES if focus == 'trip' else (focus,))])

        self.decider = AsyncMock(side_effect=decide)
        self.research = AsyncMock(return_value=ResearchResult(role='stays', sources=[WebEvidence(
            url='https://hotel.example.org/pool', title='Услуги отеля', text='Есть бассейн', retrieved_at=datetime.now(timezone.utc))]))
        async def present(state):
            return 'У отеля есть бассейн. Источник: https://hotel.example.org/pool' if state.get('decision', {}).get('action') == 'research' else state['answer']
        graph = build_graph(self.decider, self.runners, InMemorySaver(), autonomous=True, research=self.research, present=present)
        self.app = create_app(graph=graph, tokens=('test',))
        self.life = self.app.router.lifespan_context(self.app)
        await self.life.__aenter__()
        self.app.state.accounts = self.accounts
        self.api = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://test', headers={'Authorization': 'Bearer test'})

        async def telegram(request):
            self.sent.append((request.url.path.rsplit('/', 1)[-1], json.loads(request.content)))
            return httpx.Response(200, json={'ok': True, 'result': {'message_id': len(self.sent)}})

        self.client = httpx.AsyncClient(transport=httpx.MockTransport(telegram))
        self.bot = TelegramBot(self.app, self.client, 'test-token')

    async def asyncTearDown(self):
        await self.api.aclose()
        await self.client.aclose()
        await self.life.__aexit__(None, None, None)

    async def say(self, text='', action=None, chat_id=7):
        await self.bot.interact(self.api, chat_id, self.user, text, action)

    def text(self):
        return '\n'.join(data.get('text', '') for _, data in self.sent)

    def buttons(self):
        return [button for _, data in self.sent for row in data.get('reply_markup', {}).get('inline_keyboard', []) for button in row]

    async def state(self):
        return (await self.api.get('/trips/' + self.saved[7][0])).json()

    async def plan(self):
        await self.say('/new')
        await self.say('Из Москвы в Сочи на прогулки, 12–16 ноября, двое взрослых')
        return await self.state()

    async def test_full_plan_hotels_photos_return_tickets_select_and_checkout(self):
        state = await self.plan()
        self.assertEqual(len(state['options']), 5)
        self.assertIn('На человека:', self.text())
        self.assertIn('Программа по дням', self.text())
        trip_id = self.saved[7][0]
        revision = state['revision']
        calls_before = sum(r.await_count for r in self.runners.values())
        self.sent.clear()
        await self.say('/hotels')
        self.assertIn(state['options'][0]['stay']['name'], self.text())
        details = next(b['callback_data'] for b in self.buttons() if b.get('callback_data', '').startswith('d:'))
        photo = next(b['callback_data'] for b in self.buttons() if b.get('callback_data', '').startswith('f:'))
        await self.say(action=details)
        self.assertIn('Бассейн', self.text())
        self.assertIn('Курортный проспект', self.text())
        await self.say(action=photo)
        sent_photos = [data['photo'] for method, data in self.sent if method == 'sendPhoto']
        self.assertEqual(sent_photos, state['options'][0]['stay']['photos'])
        self.assertEqual(sum(r.await_count for r in self.runners.values()), calls_before)
        self.sent.clear()
        await self.say('/tickets')
        self.assertIn('Туда:', self.text())
        self.assertIn('Обратно:', self.text())
        self.assertIn('Багаж:', self.text())
        self.sent.clear()
        await self.say(action=f'c:{trip_id}:{revision}:1')
        state = await self.state()
        self.assertEqual(state['selected'], state['options'][1]['id'])
        self.assertEqual(sum(r.await_count for r in self.runners.values()), calls_before)
        await self.say('/pay')
        confirmation = next(b['callback_data'] for b in self.buttons() if b.get('callback_data', '').startswith('b:') and b['callback_data'].endswith(':card'))
        await self.say(action=confirmation)
        state = await self.state()
        self.assertEqual(state['stage'], 'booked')
        self.assertTrue(state['receipt']['simulated'])
        self.assertFalse(state['receipt']['paid'])
        self.assertFalse(state['receipt']['reserved'])
        await self.say('/orders')
        self.assertIn('Деньги не списаны', self.text())

    async def test_standalone_search_modes_and_extend_through_the_same_agent(self):
        for mode, command in [('stays', '/hotels'), ('transport', '/tickets')]:
            with self.subTest(mode=mode):
                self.saved.clear()
                for runner in self.runners.values():
                    runner.reset_mock()
                await self.say(command)
                self.assertEqual(self.saved[7][1], 'search:' + mode)
                await self.say('Москва — Сочи, 12–16 ноября, двое взрослых')
                state = await self.state()
                self.assertEqual(state['focus'], mode)
                self.assertTrue(state['cards'])
                self.assertEqual(self.runners[mode].await_count, 1)
                self.assertTrue(all(r.await_count == 0 for role, r in self.runners.items() if role != mode))
                await self.say(action=f"c:{self.saved[7][0]}:{state['revision']}:0")
                selected = (await self.state())['selected_stay' if mode == 'stays' else 'selected_transport']
                self.assertEqual(selected, state['choices'][0]['id'])
                await self.say(action='extend')
                state = await self.state()
                self.assertIsNone(state['focus'])
                self.assertTrue(state['options'])
                self.assertEqual(self.saved[7][1], None)

    async def test_questions_and_back_preserve_plan_without_search_or_card_spam(self):
        original = await self.plan()
        before = sum(r.await_count for r in self.runners.values())
        self.sent.clear()
        await self.say('Сколько стоит питание?')
        state = await self.state()
        for field in ('revision', 'selected', 'options', 'results'):
            self.assertEqual(state[field], original[field])
        self.assertEqual(len(self.sent), 2)
        self.assertIn('Питание оплачивается отдельно', self.text())
        self.sent.clear()
        await self.say('/back')
        self.assertIn('Напишите, что изменить', self.text())
        self.assertEqual((await self.state())['revision'], original['revision'])
        self.assertEqual(sum(r.await_count for r in self.runners.values()), before)
        await self.say('/show')
        self.assertIn('Варианты поездки', self.text())

    async def test_stale_and_cross_trip_detail_photo_select_and_payment_do_not_mutate(self):
        state = await self.plan()
        trip_id = self.saved[7][0]
        before = self.decider.await_count
        self.sent.clear()
        for action in (f'd:{trip_id}:0:h:0', f'f:{trip_id}:0:h:0', f'c:{trip_id}:0:0', f'd:other:{state["revision"]}:p:0'):
            await self.say(action=action)
        self.assertFalse(any(method == 'sendPhoto' for method, _ in self.sent))
        self.assertEqual(self.decider.await_count, before)
        await self.say('/pay')
        old_confirm = next(b['callback_data'] for b in self.buttons() if b.get('callback_data', '').startswith('b:'))
        await self.say(action=f"c:{trip_id}:{state['revision']}:1")
        await self.say(action=old_confirm)
        self.assertFalse((await self.state())['bookings'])
        self.assertIn('Состав заказа изменился', self.text())

    async def test_hotel_research_preserves_plan_and_links_to_evidence(self):
        original = await self.plan()
        before = sum(r.await_count for r in self.runners.values())
        self.sent.clear()
        await self.say('Проверь в интернете, есть ли бассейн в отеле')
        state = await self.state()
        self.research.assert_awaited_once()
        self.assertIn('https://hotel.example.org/pool', self.text())
        for field in ('revision', 'selected', 'options', 'results'):
            self.assertEqual(state[field], original[field])
        self.assertEqual(sum(r.await_count for r in self.runners.values()), before)
        await self.say('/map')
        self.assertTrue(any('yandex.ru/maps/' in b.get('url', '') for b in self.buttons()))
        await self.say('/history')
        self.assertIn('есть ли бассейн', self.text())

    async def test_handle_uses_shared_api_and_revokes_temporary_session(self):
        await self.bot.handle({'message': {'chat': {'id': 7, 'type': 'private'}, 'from': {'id': 7}, 'text': '/new'}})
        self.assertTrue(self.saved[7][0])
        self.accounts.revoke.assert_awaited_once_with('test')
        await self.bot.handle({'message': {'chat': {'id': 7, 'type': 'private'}, 'from': {'id': 7}, 'photo': [{}]}})
        self.assertIn('текстовые сообщения', self.text())
        self.assertEqual(self.accounts.session.await_count, 1)


class TelegramSafetyTests(unittest.IsolatedAsyncioTestCase):
    async def test_no_photos_or_prices_are_invented_and_expired_offers_cannot_be_selected(self):
        state = agreed_state('review')
        state['options'] = []
        state['focus'] = 'stays'
        state['choices'] = [{'id': state['results']['stays']['candidates'][0]['id'], 'title': 'Отель'}]
        item = state['results']['stays']['candidates'][0]
        item.update(photos=[], price=None)
        item['source']['expires_at'] = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        accounts = SimpleNamespace(bot_state=AsyncMock(return_value=('trip', None)))
        bot = TelegramBot(SimpleNamespace(state=SimpleNamespace(accounts=accounts)), AsyncMock(), 'test')
        bot.send = AsyncMock()
        bot.call = AsyncMock()
        bot.request = AsyncMock(return_value=state)
        await bot.show(7, 'trip', state, 'h')
        text = '\n'.join(call.args[1] for call in bot.send.await_args_list)
        buttons = [b for call in bot.send.await_args_list if len(call.args) > 2 for row in call.args[2] for b in row]
        self.assertIn('источник не указал', text)
        self.assertFalse(any(b.get('callback_data') in ('c:trip:1:0', 'f:trip:1:h:0') for b in buttons))
        await bot.interact(AsyncMock(), 7, 'owner', '', 'f:trip:1:h:0')
        bot.call.assert_not_awaited()
        self.assertIn('не предоставил фотографий', bot.send.await_args.args[1])

    async def test_photo_rejection_keeps_provider_link_and_filters_unsafe_urls(self):
        state = agreed_state('review')
        state['options'] = []
        state['results']['stays']['candidates'][0]['photos'] = ['https://images.example.org/room.jpg', 'file:///tmp/key', 'https://user:password@example.org/room', 'https://127.0.0.1/private', 'https://example.org:bad/photo']
        accounts = SimpleNamespace(bot_state=AsyncMock(return_value=('trip', None)))
        bot = TelegramBot(SimpleNamespace(state=SimpleNamespace(accounts=accounts)), AsyncMock(), 'test')
        bot.request = AsyncMock(return_value=state)
        bot.send = AsyncMock()
        bot.call = AsyncMock(side_effect=TelegramError('rejected photo', 400))
        await bot.interact(AsyncMock(), 7, 'owner', '', 'f:trip:1:h:0')
        bot.call.assert_awaited_once()
        self.assertEqual(bot.call.await_args.args[1]['photo'], 'https://images.example.org/room.jpg')
        self.assertEqual(bot.send.await_args.args[2][0][0]['url'], 'https://images.example.org/room.jpg')

    async def test_unicode_messages_fit_telegram_limits_without_losing_text(self):
        bot = TelegramBot(None, AsyncMock(), 'test')
        bot.call = AsyncMock()
        text = '🧳' * 4000 + '\n' + 'День поездки\n' * 300
        await bot.send(7, text, [[bot.button('План', 'plan')]])
        data = [call.args[1] for call in bot.call.await_args_list]
        self.assertEqual(''.join(item['text'] for item in data), text)
        self.assertTrue(all(len(item['text'].encode('utf-16-le')) // 2 <= 3800 for item in data))
        self.assertTrue(all('reply_markup' not in item for item in data[:-1]))
        self.assertIn('reply_markup', data[-1])

    async def test_rate_limit_retry_is_bounded_and_does_not_repeat_successful_sends(self):
        attempts = []
        def transport(request):
            attempts.append(request)
            return httpx.Response(429, json={'ok': False, 'error_code': 429, 'parameters': {'retry_after': 1}}) if len(attempts) == 1 else httpx.Response(200, json={'ok': True, 'result': {}})
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
            bot = TelegramBot(None, client, 'test')
            with patch('travel_agent.telegram.asyncio.sleep', new_callable=AsyncMock) as sleep:
                await bot.send(7, 'Готово')
            self.assertEqual(len(attempts), 2)
            sleep.assert_awaited_once_with(1)
            await bot.send(7, 'Ещё')
            self.assertEqual(len(attempts), 3)

    async def test_autonomous_partial_results_and_legacy_program_approval_are_available(self):
        bot = TelegramBot(None, AsyncMock(), 'test')
        bot.send = AsyncMock()
        state = agreed_state('itinerary')
        state.update(choices=[{'id': 'approve-program', 'title': 'Согласовать программу'}], answer='Программа готова')
        await bot.show(7, 'trip', state)
        buttons = [b for call in bot.send.await_args_list if len(call.args) > 2 for row in call.args[2] for b in row]
        self.assertTrue(any(b.get('callback_data') == 'c:trip:1:0' for b in buttons))
        state.update(autonomous=True, options=[], choices=[], feedback=[{'code': 'no_stays'}])
        bot.send.reset_mock()
        await bot.show(7, 'trip', state, 't')
        self.assertTrue(any('Туда:' in call.args[1] for call in bot.send.await_args_list))
        self.assertTrue(any('требует уточнений' in call.args[1] for call in bot.send.await_args_list))


    async def test_progress_shows_status_and_preliminary_offers_while_search_runs(self):
        finished = asyncio.Event()
        status_reads = []
        async def transport(request):
            if request.method == 'POST':
                await finished.wait()
                return httpx.Response(200, json={'revision': 1, 'answer': 'Готово'})
            status_reads.append(request.url.path)
            return httpx.Response(200, json={'label': 'Подбираю проживание', 'previews': {'stays': [{'title': 'Отель у моря'}]}})
        bot = TelegramBot(None, AsyncMock(), 'test')
        async def send(chat_id, text, buttons=None):
            if 'Отель у моря' in text:
                finished.set()
        bot.send = AsyncMock(side_effect=send)
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport), base_url='http://test') as api:
            with patch('travel_agent.telegram.PROGRESS_INTERVAL', 0.001):
                state = await asyncio.wait_for(bot.search(api, 7, 'trip', {'revision': 0}, 'Поехали'), 2)
        self.assertEqual(state['answer'], 'Готово')
        self.assertEqual(status_reads, ['/trips/trip/status'])
        self.assertIn('Предварительно найдено', bot.send.await_args.args[1])

    async def test_pdf_progress_pagination_and_trip_deletion_use_shared_endpoints(self):
        state = agreed_state('review')
        accounts = SimpleNamespace(bot_state=AsyncMock(return_value=('trip', None)))
        bot = TelegramBot(SimpleNamespace(state=SimpleNamespace(accounts=accounts)), AsyncMock(), 'test')
        bot.call = AsyncMock()
        bot.send = AsyncMock()
        bot.request = AsyncMock(side_effect=[state, b'%PDF-test'])
        await bot.interact(AsyncMock(), 7, 'owner', '/pdf', None)
        self.assertEqual(bot.request.await_args.args[3], '/trips/trip/itinerary.pdf')
        self.assertEqual(bot.call.await_args.args[2], b'%PDF-test')
        progress = {'items': [{'id': str(i), 'title': 'Место ' + str(i), 'date': '2026-11-13'} for i in range(125)], 'completed': {}}
        bot.request = AsyncMock(side_effect=[state, progress, progress])
        await bot.interact(AsyncMock(), 7, 'owner', '', 'done:trip:1:120')
        self.assertEqual(bot.request.await_args.args[1:4], (7, 'PUT', '/trips/trip/progress'))
        self.assertEqual(bot.request.await_args.kwargs['json'], {'completed': {'120': True}})
        self.assertIn('Место 120', str(bot.send.await_args))
        self.assertIn('2026-11-13', str(bot.send.await_args))
        bot.request = AsyncMock(return_value=state)
        await bot.interact(AsyncMock(), 7, 'owner', '', 'rm:trip')
        self.assertEqual(bot.request.await_count, 1)
        self.assertIn('устарело', bot.send.await_args.args[1])
        accounts.bot_state.return_value = ('trip', 'remove:trip')
        bot.request = AsyncMock(side_effect=[state, {}])
        await bot.interact(AsyncMock(), 7, 'owner', '', 'rm:trip')
        self.assertEqual(bot.request.await_args.args[1:4], (7, 'DELETE', '/trips/trip'))
        accounts.bot_state.assert_awaited_with(7, None, write=True)

    async def test_expired_checkout_never_creates_confirmation_buttons(self):
        state = agreed_state('review')
        state['selected'] = state['options'][0]['id']
        state['options'][0]['transport']['source']['expires_at'] = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        bot = TelegramBot(SimpleNamespace(state=SimpleNamespace(accounts=SimpleNamespace(bot_state=AsyncMock(return_value=('trip', None))))), AsyncMock(), 'test')
        bot.request = AsyncMock(return_value=state)
        bot.send = AsyncMock()
        await bot.interact(AsyncMock(), 7, 'owner', '/pay', None)
        self.assertIn('Котировки устарели', bot.send.await_args.args[1])
        self.assertEqual(bot.request.await_count, 1)
        self.assertTrue(all(len(call.args) < 3 for call in bot.send.await_args_list))


class TelegramPollingTests(unittest.IsolatedAsyncioTestCase):
    async def test_chats_run_concurrently_same_chat_is_ordered_and_cursor_waits_for_completion(self):
        accounts = SimpleNamespace(bot_offset=AsyncMock(return_value=0))
        bot = TelegramBot(SimpleNamespace(state=SimpleNamespace(accounts=accounts)), AsyncMock(), 'test')
        started, second, finished = asyncio.Event(), asyncio.Event(), asyncio.Event()
        release = asyncio.Event()
        received = []
        acknowledgements = []
        updates = [
            {'update_id': 1, 'message': {'chat': {'id': 7}}},
            {'update_id': 2, 'message': {'chat': {'id': 8}}},
            {'update_id': 3, 'callback_query': {'id': 'cb', 'message': {'chat': {'id': 7}}}},
        ]

        async def handle(update, **kwargs):
            received.append(update['update_id'])
            if update['update_id'] == 1:
                started.set()
                await release.wait()
            elif update['update_id'] == 2:
                second.set()

        async def call(method, data):
            if method == 'getMe':
                return {'username': 'configured_travel_bot'}
            if method == 'getWebhookInfo':
                return {}
            if method == 'answerCallbackQuery':
                acknowledgements.append(data['callback_query_id'])
            if method == 'getUpdates':
                if data['offset'] >= 4:
                    finished.set()
                    await asyncio.Event().wait()
                return [u for u in updates if u['update_id'] >= data['offset']]
            return {}

        bot.call = AsyncMock(side_effect=call)
        bot.handle = AsyncMock(side_effect=handle)
        polling = asyncio.create_task(bot.poll())
        try:
            await asyncio.wait_for(started.wait(), 2)
            await asyncio.wait_for(second.wait(), 2)
            self.assertEqual(received, [1, 2])
            self.assertEqual(acknowledgements, ['cb'])
            self.assertTrue(bot.ready)
            self.assertEqual(bot.username, 'configured_travel_bot')
            self.assertTrue(all(not call.args for call in accounts.bot_offset.await_args_list))
            release.set()
            await asyncio.wait_for(finished.wait(), 3)
            self.assertEqual(received, [1, 2, 3])
            self.assertEqual([call.args[0] for call in accounts.bot_offset.await_args_list if call.args], [2, 3, 4])
        finally:
            await bot.stop(polling)
        self.assertFalse(bot.ready)

    async def test_startup_recovers_after_connect_timeout_instead_of_disabling_bot(self):
        accounts = SimpleNamespace(bot_offset=AsyncMock(return_value=0))
        bot = TelegramBot(SimpleNamespace(state=SimpleNamespace(accounts=accounts)), AsyncMock(), 'test')
        connected = asyncio.Event()
        attempts = 0
        async def call(method, data):
            nonlocal attempts
            if method == 'getMe':
                attempts += 1
                if attempts == 1:
                    raise httpx.ConnectTimeout('unavailable')
                return {'username': 'travel_bot'}
            if method == 'getUpdates':
                connected.set()
                await asyncio.Event().wait()
            return {}
        bot.call = AsyncMock(side_effect=call)
        with patch('travel_agent.telegram.asyncio.sleep', new_callable=AsyncMock) as sleep:
            polling = asyncio.create_task(bot.poll())
            try:
                await asyncio.wait_for(connected.wait(), 2)
                self.assertEqual(attempts, 2)
                self.assertTrue(bot.ready)
                sleep.assert_awaited_once_with(3)
            finally:
                await bot.stop(polling)

    async def test_existing_webhook_is_preserved_and_transient_polling_error_recovers(self):
        accounts = SimpleNamespace(bot_offset=AsyncMock(return_value=0))
        bot = TelegramBot(SimpleNamespace(state=SimpleNamespace(accounts=accounts)), AsyncMock(), 'test')
        bot.call = AsyncMock(side_effect=[{'username': 'bot'}, {'url': 'https://example.org/webhook'}])
        await bot.poll()
        self.assertFalse(bot.ready)
        self.assertEqual([call.args[0] for call in bot.call.await_args_list], ['getMe', 'getWebhookInfo'])
        recovered = asyncio.Event()
        count = 0
        async def call(method, data):
            nonlocal count
            if method == 'getMe': return {'username': 'bot'}
            if method == 'getWebhookInfo': return {}
            if method == 'getUpdates':
                count += 1
                if count == 1: raise TelegramError('temporary', 502)
                recovered.set()
                await asyncio.Event().wait()
            return {}
        bot.call = AsyncMock(side_effect=call)
        with patch('travel_agent.telegram.asyncio.sleep', new_callable=AsyncMock):
            polling = asyncio.create_task(bot.poll())
            try:
                await asyncio.wait_for(recovered.wait(), 2)
                self.assertEqual(count, 2)
            finally:
                await bot.stop(polling)
