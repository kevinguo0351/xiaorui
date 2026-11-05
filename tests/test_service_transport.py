import os
import unittest
from contextlib import asynccontextmanager
from unittest.mock import patch

import httpx

from app.service_transport import service_http_client
from app.life_services import OfficialMcp, ServiceUnavailable, transport_diagnostic
from mcp.shared.exceptions import McpError
from mcp.types import ErrorData


class ServiceTransportTests(unittest.TestCase):
    def test_nested_errors_expose_only_types_statuses_and_codes(self):
        request = httpx.Request('POST', 'https://example.invalid/?key=private-key')
        response = httpx.Response(429, request=request)
        http_error = httpx.HTTPStatusError('private-key', request=request, response=response)
        mcp_error = McpError(ErrorData(code=-32001, message='private-key'))
        result = transport_diagnostic(ExceptionGroup('private-key', [http_error, mcp_error]))
        self.assertEqual(result, {'error_types': ['ExceptionGroup', 'HTTPStatusError', 'McpError'],
                                  'http_statuses': [429], 'mcp_codes': [-32001]})
        self.assertNotIn('private-key', str(result))

    def test_default_preserves_proxy_and_transport_options(self):
        timeout = httpx.Timeout(7, read=19)
        auth = httpx.BasicAuth('test', 'test')
        with patch.dict(os.environ, {}, clear=True), \
             patch('app.service_transport.dotenv_values', return_value={}), \
             patch('app.service_transport.httpx.AsyncClient') as client:
            service_http_client(headers={'test': 'value'}, timeout=timeout, auth=auth)
        client.assert_called_once_with(headers={'test': 'value'}, timeout=timeout,
                                       auth=auth, trust_env=True)

    def test_dotenv_can_disable_proxy_without_modifying_process_environment(self):
        with patch.dict(os.environ, {'HTTPS_PROXY': 'http://proxy.invalid:1234'}, clear=True), \
             patch('app.service_transport.dotenv_values', return_value={'LIFE_SERVICES_TRUST_ENV': 'false'}), \
             patch('app.service_transport.httpx.AsyncClient') as client:
            service_http_client()
            self.assertEqual(os.environ['HTTPS_PROXY'], 'http://proxy.invalid:1234')
        self.assertFalse(client.call_args.kwargs['trust_env'])
        self.assertEqual(client.call_count, 1)

    def test_environment_overrides_local_file(self):
        with patch.dict(os.environ, {'LIFE_SERVICES_TRUST_ENV': 'true'}), \
             patch('app.service_transport.dotenv_values', return_value={'LIFE_SERVICES_TRUST_ENV': 'false'}), \
             patch('app.service_transport.httpx.AsyncClient') as client:
            service_http_client()
        self.assertTrue(client.call_args.kwargs['trust_env'])


class ServiceFailureTests(unittest.IsolatedAsyncioTestCase):
    async def test_didi_rate_limit_is_explained_without_retry_or_secret(self):
        @asynccontextmanager
        async def limited(*args, **kwargs):
            raise ExceptionGroup('private-key', [McpError(ErrorData(code=-32001, message='private-key'))])
            yield

        adapter = OfficialMcp('didi')
        with patch.object(adapter, '_credential', return_value='private-key'), \
             patch('app.life_services.streamablehttp_client', side_effect=limited) as transport:
            with self.assertRaises(ServiceUnavailable) as caught:
                async with adapter.connection():
                    self.fail('Rate limited connection must not be usable')
        self.assertIn('频繁', str(caught.exception))
        self.assertNotIn('private-key', str(caught.exception))
        self.assertEqual(caught.exception.diagnostic['mcp_codes'], [-32001])
        self.assertEqual(transport.call_count, 1)


if __name__ == '__main__':
    unittest.main()
