"""Inbox concurrency, restart and approval binding, without external requests."""
import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from app.contact import ContactService
from app.contact_events import notify


class ContactTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.calls = []
        self.session = SimpleNamespace(lock=asyncio.Lock())
        self.actions = SimpleNamespace(pending=Mock(return_value=None), invalidate_pending=Mock())
        async def chat(owner, text, **kwargs):
            self.calls.append((owner,text,kwargs))
            notify({'type':'delta','text':'真实流式事件接口'})
            return {'text':text,'events':[]}
        self.agent = SimpleNamespace(actions=self.actions, chat=chat,
            _session=lambda _:self.session, _plan=lambda *_:None)
        self.contact = ContactService(self.agent, Path(self.temp.name)/'contact.sqlite3')

    async def asyncTearDown(self):
        await self.contact.close()
        self.temp.cleanup()

    async def drain(self, owner='a'):
        await asyncio.wait_for(self.contact.workers[owner], 5)

    async def test_fragments_are_received_immediately_batched_and_idempotent(self):
        first=self.contact.enqueue('a','想吃午饭','client-0001')
        self.contact.enqueue('a','三十元以内','client-0002')
        self.assertEqual(first,self.contact.enqueue('a','想吃午饭','client-0001'))
        self.assertEqual(len(self.contact.events('a')),2)
        self.assertEqual(self.contact.events('b'),[])
        await self.drain()
        self.assertEqual([r[1] for r in self.calls],['想吃午饭\n三十元以内'])
        self.assertTrue(any(e['type']=='delta' for e in self.contact.events('a')))
        self.assertEqual(self.contact.state('a')['pending'],0)

    async def test_new_message_during_run_is_accepted_and_old_response_superseded(self):
        entered,release=asyncio.Event(),asyncio.Event()
        original=self.agent.chat
        async def chat(owner,text,**kw):
            if text=='原来的需求':
                entered.set()
                await release.wait()
            return await original(owner,text,**kw)
        self.agent.chat=chat
        self.contact.enqueue('a','原来的需求','client-0001')
        await asyncio.wait_for(entered.wait(),2)
        self.contact.enqueue('a','改成新的地点','client-0002')
        release.set()
        await self.drain()
        done=[e for e in self.contact.events('a') if e['type']=='completed']
        self.assertTrue(done[0]['superseded'])
        self.assertFalse(done[1]['superseded'])
        self.assertEqual([c[1] for c in self.calls],['原来的需求','改成新的地点'])

    async def test_confirmation_is_separate_and_bound_to_arrival_plan(self):
        self.actions.pending.return_value={'id':'visible-plan','version':4}
        self.contact.enqueue('a','确认下单','client-0001')
        self.contact.enqueue('a','改成两份','client-0002')
        await self.drain()
        self.assertEqual(self.calls[0][1],'确认下单')
        self.assertEqual(self.calls[0][2]['expected_confirmation'],['visible-plan',4])
        self.actions.invalidate_pending.assert_called()

    async def test_restart_marks_inflight_interrupted_and_does_not_replay(self):
        self.contact.enqueue('a','确认下单','client-0001')
        await self.contact.close()
        other=ContactService(self.agent,self.contact.path)
        other.recover()
        self.assertFalse(other.workers)
        self.assertEqual(other.state('a')['pending'],0)
        self.assertEqual(other.events('a')[-1]['type'],'failed')
        await other.close()

    async def test_forgetting_removes_previous_contact_replay(self):
        self.contact.enqueue('a','旧资料','client-0001')
        await self.drain()
        async def forget(*args,**kwargs):
            return {'text':'已忘记','events':[],'conversation_reset':True}
        self.agent.chat=forget
        self.contact.enqueue('a','忘记资料','client-0002')
        await self.drain()
        self.assertNotIn('旧资料',str(self.contact.state('a')))
