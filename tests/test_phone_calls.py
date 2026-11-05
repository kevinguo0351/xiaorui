"""Calls have durable summaries and isolate voice turns from chat turns."""
import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from app.contact import ContactService
from app.contact_events import contact_call, notify
from app.agent import AgentError
from app.speech import call_card_cue


class PhoneCallTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.runs = []
        session = SimpleNamespace(lock=asyncio.Lock())
        async def chat(owner, text, **kwargs):
            self.runs.append((text, contact_call.get()))
            notify({'type':'delta', 'text':'通话回复'})
            return {'text':'选一下餐品', 'speech_text':'您想选哪份？', 'events':[{'type':'meals','meals':[]}]}
        self.agent = SimpleNamespace(chat=chat, actions=SimpleNamespace(pending=Mock(return_value=None),invalidate_pending=Mock()),_session=lambda _:session,_plan=lambda *_:None)
        self.service = ContactService(self.agent, Path(self.temp.name)/'contact.db')

    async def asyncTearDown(self):
        await self.service.close()
        self.temp.cleanup()

    async def test_voice_and_text_do_not_batch_and_channel_survives_async_events(self):
        call = self.service.start_call('a')
        self.service.enqueue('a','电话里说的话','call-turn-1',call_id=call['id'])
        self.service.enqueue('a','单独文字消息','chat-turn-1')
        await self.service.workers['a']
        self.assertEqual(self.runs,[('电话里说的话',call['id']),('单独文字消息',None)])
        events = self.service.events('a')
        voice = [e for e in events if e.get('call_id')==call['id']]
        self.assertEqual({e['type'] for e in voice},{'accepted','started','delta','completed'})
        # A separate text channel must not suppress the phone reply.
        self.service.enqueue('a','第二段通话','call-turn-2',call_id=call['id'])
        await self.service.workers['a']
        self.assertTrue(any(e['type']=='delta' and e.get('call_id')==call['id'] for e in self.service.events('a')))
        completed = next(e for e in voice if e['type']=='completed')
        self.assertFalse(completed['superseded'])
        self.assertIn('我给您发了',completed['response']['speech_text'])
        self.assertEqual(completed['response']['events'][0]['type'],'meals')
        self.assertIsNone(contact_call.get())

    async def test_owner_bound_idempotent_summary_survives_restart(self):
        with patch('app.contact.time.time', return_value=1000):
            call = self.service.start_call('a')
        self.assertEqual(self.service.start_call('a'),call)
        with self.assertRaises(AgentError):
            self.service.end_call('b',call['id'])
        with patch('app.contact.time.time', return_value=1065):
            ended = self.service.end_call('a',call['id'])
        self.assertEqual(ended['duration_seconds'],65)
        self.assertEqual(self.service.end_call('a',call['id']),ended)
        restored = ContactService(self.agent,self.service.path)
        records = [e for e in restored.state('a')['events'] if e['type']=='call_ended']
        self.assertEqual(len(records),1)
        self.assertEqual(records[0]['call'],ended)
        self.assertIsNone(restored.state('a')['active_call'])
        await restored.close()

    async def test_closed_and_foreign_calls_cannot_receive_new_voice_turns(self):
        call = self.service.start_call('a')
        with self.assertRaises(AgentError):
            self.service.enqueue('b','别人的电话','foreign-1',call_id=call['id'])
        self.service.end_call('a',call['id'])
        with self.assertRaises(AgentError):
            self.service.enqueue('a','挂断后的话','late-turn-1',call_id=call['id'])
        self.assertEqual(self.runs,[])

    async def test_hangup_does_not_cancel_an_already_accepted_operation(self):
        call=self.service.start_call('a')
        self.service.enqueue('a','看一下餐品','pending-1',call_id=call['id'])
        self.service.end_call('a',call['id'])
        await self.service.workers['a']
        self.assertEqual(len(self.runs),1)
        completed=next(e for e in self.service.events('a') if e['type']=='completed')
        self.assertEqual(completed['call_id'],call['id'])
        self.assertEqual(len([e for e in self.service.events('a') if e['type']=='call_ended']),1)

    async def test_server_restart_finalizes_open_call_once(self):
        self.service.start_call('a')
        self.service.recover();self.service.recover()
        self.assertEqual(len([e for e in self.service.events('a') if e['type']=='call_ended']),1)

    async def test_card_cue_keeps_transaction_confirmation_and_only_mentions_real_cards(self):
        text='总共30元。确定的话请说确认下单。'
        response={'text':'屏幕回复','speech_text':text,'events':[{'type':'action_plan','plan':{}}]}
        self.assertIn(text,call_card_cue(response))
        self.assertIn('方案卡片',call_card_cue(response))
        self.assertEqual(call_card_cue({'speech_text':'今天过得怎么样？','events':[]}), '今天过得怎么样？')
