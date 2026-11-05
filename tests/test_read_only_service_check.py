"""Connectivity matrix safety/diagnostic tests; no external network calls."""
import asyncio
from contextlib import asynccontextmanager, redirect_stderr, redirect_stdout
import io
import json
import logging
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from experiments import read_only_service_check as probe


class ReadOnlyConnectivityTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def result(payload):
        return SimpleNamespace(isError=False, structuredContent=payload, content=[])

    def connection(self, session, *, tools=None):
        @asynccontextmanager
        async def connect(provider):
            tool = probe.CHECKS[provider]['tool']
            yield session, tools if tools is not None else {
                tool: SimpleNamespace(inputSchema={'type': 'object'})}
        return connect

    async def test_missing_credentials_never_opens_connection(self):
        with patch.object(probe, 'configured', return_value=False), \
             patch.object(probe, 'connection') as connect:
            report = await probe.matrix()
        connect.assert_not_called()
        self.assertEqual(len(report['checks']), 3)
        for item in report['checks']:
            self.assertEqual(item['query'], 'not_configured')
            self.assertEqual(item['transactions_attempted'], 0)

    async def test_only_fixed_public_queries_execute_and_payloads_are_not_saved(self):
        payloads = {'mcd': {'success': True, 'data': [{'storeName': 'private-marker'}]},
                    'luckin': {'code': 0, 'data': [{'deptName': 'private-marker'}]},
                    'didi': [{'display_name': 'private-marker'}]}
        for provider in probe.CHECKS:
            session = SimpleNamespace(call_tool=AsyncMock(return_value=self.result(payloads[provider])))
            with patch.object(probe, 'configured', return_value=True), \
                 patch.object(probe, 'connection', self.connection(session)):
                report = await probe.check_provider(provider)
            self.assertEqual(report['discovery'], 'passed')
            self.assertEqual(report['query'], 'passed')
            self.assertEqual(report['results_returned'], 1)
            self.assertNotIn('private-marker', json.dumps(report))
            session.call_tool.assert_awaited_once_with(
                probe.CHECKS[provider]['tool'], arguments=probe.CHECKS[provider]['arguments'])
        self.assertEqual(probe.ALLOWED_TOOLS,
                         {'query-nearby-stores', 'queryShopList', 'maps_textsearch'})

    async def test_discovery_does_not_imply_query_permission_or_schema_compatibility(self):
        session = SimpleNamespace(call_tool=AsyncMock())
        for tools, expected in [({}, 'tool_not_available'), ({
            'maps_textsearch': SimpleNamespace(inputSchema={'type': 'object', 'required': ['new_field']})
        }, 'schema_mismatch')]:
            with patch.object(probe, 'configured', return_value=True), \
                 patch.object(probe, 'connection', self.connection(session, tools=tools)):
                report = await probe.check_provider('didi')
            self.assertEqual(report['discovery'], 'passed')
            self.assertEqual(report['query'], expected)
        session.call_tool.assert_not_awaited()

    async def test_business_error_or_unrecognized_payload_is_not_query_success(self):
        for payload in [{'success': False, 'data': []}, {'unexpected': []}]:
            session = SimpleNamespace(call_tool=AsyncMock(return_value=self.result(payload)))
            with patch.object(probe, 'configured', return_value=True), \
                 patch.object(probe, 'connection', self.connection(session)):
                report = await probe.check_provider('mcd')
            self.assertEqual(report['discovery'], 'passed')
            self.assertEqual(report['query'], 'failed')
        session = SimpleNamespace(call_tool=AsyncMock(return_value=self.result([])))
        with patch.object(probe, 'configured', return_value=True), \
             patch.object(probe, 'connection', self.connection(session)):
            report = await probe.check_provider('didi')
        self.assertEqual(report['query'], 'empty')
        self.assertEqual(report['results_returned'], 0)

    async def test_timeout_is_bounded_and_separate_from_discovery(self):
        async def wait(*args, **kwargs):
            await asyncio.sleep(1)
        session = SimpleNamespace(call_tool=AsyncMock(side_effect=wait))
        with patch.object(probe, 'configured', return_value=True), \
             patch.object(probe, 'connection', self.connection(session)):
            report = await probe.check_provider('didi', timeout=.01)
        self.assertEqual(report['discovery'], 'passed')
        self.assertEqual(report['query'], 'timeout')

    async def test_exception_and_transport_logs_cannot_leak_key_in_report_or_output(self):
        marker = 'secret-key-never-output'
        async def fail(*args, **kwargs):
            logging.getLogger('httpx').error('https://test/?key=%s', marker)
            raise RuntimeError('https://test/?key=' + marker)
        session = SimpleNamespace(call_tool=AsyncMock(side_effect=fail))
        previous = logging.root.manager.disable
        output = io.StringIO()
        with patch.object(probe, 'configured', return_value=True), \
             patch.object(probe, 'connection', self.connection(session)), \
             redirect_stderr(output), redirect_stdout(output):
            report = await probe.matrix(['didi'])
        self.assertEqual(report['checks'][0]['query'], 'failed')
        self.assertNotIn(marker, json.dumps(report) + output.getvalue())
        self.assertEqual(logging.root.manager.disable, previous)
