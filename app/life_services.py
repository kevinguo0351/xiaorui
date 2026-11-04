"""Official Luckin/DiDi read adapters. No remote transaction entry points.

Tool schemas are discovered from the user's account, rather than assumed from
public examples. Missing permissions and credentials never fall back to data.
"""
import asyncio
import json
import logging
import os
import traceback
from datetime import timedelta
from pathlib import Path
from contextlib import asynccontextmanager

from dotenv import dotenv_values
from jsonschema import validate, ValidationError
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

ROOT = Path(__file__).resolve().parents[1]
SPECS = {
    'luckin': {'label': '瑞幸', 'env': 'LUCKIN_MCP_TOKEN',
               'url': 'https://gwmcp.lkcoffee.com/order/user/mcp',
               'reads': {'queryShopList', 'searchProductForMcp', 'queryProductDetailInfo', 'previewOrder',
                         'switchProduct', 'queryOrderDetailInfo'},
               'writes': {'createOrder', 'cancelOrder'}},
    'didi': {'label': '滴滴', 'env': 'DIDI_MCP_KEY',
             'url': 'https://mcp.didichuxing.com/mcp-servers',
             'reads': {'maps_textsearch', 'taxi_estimate', 'taxi_query_order', 'taxi_get_driver_location', 'maps_regeocode'},
             'writes': {'taxi_create_order', 'taxi_cancel_order'}},
}


class ServiceUnavailable(RuntimeError):
    pass


class CredentialFilter(logging.Filter):
    """MCP/httpx may log exception URLs containing DiDi's query-string Key."""
    def __init__(self):
        super().__init__()
        self.secrets = set()

    def filter(self, record):
        message = record.getMessage()
        exception = ''.join(traceback.format_exception(*record.exc_info)) if record.exc_info else record.exc_text
        for secret in self.secrets:
            message = message.replace(secret, '[REDACTED]')
            if exception:
                exception = exception.replace(secret, '[REDACTED]')
        record.msg, record.args = message, ()
        if record.exc_info or record.exc_text:
            record.exc_info, record.exc_text = None, exception
        return True


_credential_filter = CredentialFilter()
for _name in ('httpx', 'mcp.client.streamable_http'):
    logging.getLogger(_name).addFilter(_credential_filter)


class OfficialMcp:
    def __init__(self, provider):
        self.spec = SPECS[provider]
        self.provider = provider

    def _credential(self):
        name = self.spec['env']
        return str(os.environ.get(name, dotenv_values(ROOT / '.env').get(name) or '')).strip()

    @property
    def configured(self):
        return bool(self._credential())

    @asynccontextmanager
    async def connection(self):
        credential = self._credential()
        label = self.spec['label']
        if not credential:
            raise ServiceUnavailable(f'{label}尚未配置，请由家人在本机填写 {self.spec["env"]}。')
        _credential_filter.secrets.add(credential)
        # DiDi's official authentication uses a query parameter. Never log this URL.
        from urllib.parse import urlencode
        url, headers = self.spec['url'], {}
        if self.provider == 'didi':
            url += '?' + urlencode({'key': credential})
        else:
            headers['Authorization'] = 'Bearer ' + credential
        try:
            async with asyncio.timeout(55):
                async with streamablehttp_client(url, headers=headers, timeout=15, sse_read_timeout=25) as (read, write, _):
                    async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=25)) as session:
                        await session.initialize()
                        tools, cursor = {}, None
                        for _ in range(10):
                            page = await session.list_tools(cursor=cursor)
                            tools.update((t.name, t) for t in page.tools)
                            if not page.nextCursor:
                                break
                            if page.nextCursor == cursor:
                                raise ServiceUnavailable(f'{label}工具目录异常。')
                            cursor = page.nextCursor
                        else:
                            raise ServiceUnavailable(f'{label}工具目录异常。')
                        yield session, tools
        except ServiceUnavailable:
            raise
        except Exception:
            raise ServiceUnavailable(f'{label}连接或查询失败，请检查账号权限、网络和凭据。尚未下单。') from None

    async def discover(self):
        async with self.connection() as (_, tools):
            return {'provider': self.provider, 'connected': True,
                    'read_tools': sorted(self.spec['reads'] & tools.keys()),
                    'order_tool_available': ('taxi_create_order' if self.provider == 'didi' else 'createOrder') in tools,
                    'order_execution_enabled': False,
                    'note': '目录可见不代表交易权限已通过实测。'}

    async def call(self, name, arguments):
        # Enforce the allowlist before opening a connection, even for a known tool.
        if name not in self.spec['reads']:
            raise ServiceUnavailable('此接入阶段只允许查询与核价，不能创建、取消订单或支付。')
        return await self._invoke(name, arguments)

    async def call_confirmed(self, name, arguments):
        """Host-only adapter method, never registered as a model tool or API."""
        if name not in self.spec['writes']:
            raise ServiceUnavailable('该写操作不在受控白名单内。')
        return await self._invoke(name, arguments)

    async def _invoke(self, name, arguments):
        async with self.connection() as (session, tools):
            if name not in tools:
                raise ServiceUnavailable(f'当前账号未开放所需的{self.spec["label"]}工具。')
            try:
                validate(arguments, tools[name].inputSchema)
            except ValidationError:
                raise ServiceUnavailable('参数与官方接口不一致，请重新选择地点、门店或商品。') from None
            result = await session.call_tool(name, arguments=arguments)
            def failure(message):
                exc = ServiceUnavailable(message)
                if name in self.spec['writes']:
                    raw = json.dumps(result.model_dump(by_alias=True, exclude_none=True), ensure_ascii=False)
                    exc.provider_response = json.loads(raw.replace(self._credential(), '[REDACTED]'))
                return exc
            if result.isError:
                raise failure(f'{self.spec["label"]}未返回可确认结果，请检查官方订单，暂不重复提交。')
            payload = result.structuredContent
            if payload is None:
                values = []
                for block in result.content:
                    if block.type == 'text':
                        try:
                            values.append(json.loads(block.text))
                        except ValueError:
                            pass
                if len(values) != 1:
                    raise failure('无法识别官方返回结果，请核查，不能推断交易是否成功。')
                payload = values[0]
            if self.provider == 'luckin':
                if not isinstance(payload, dict) or payload.get('code') != 0 or payload.get('success') is False or 'data' not in payload:
                    raise failure('瑞幸请求未返回成功，请核查账号和官方订单。')
                payload = payload['data']
            elif isinstance(payload, dict) and ('error' in payload or payload.get('success') is False):
                raise failure('滴滴请求未返回成功，请检查权限和官方订单。')
            # Do not forward account credentials even if a provider echoes them.
            if self._credential() in json.dumps(payload, ensure_ascii=False):
                raise ServiceUnavailable('官方结果包含敏感信息，已停止展示。')
            return payload


def connection_status():
    return {p: {'configured': OfficialMcp(p).configured, 'order_execution_enabled': False,
                'status_scope': 'credential-presence-only'} for p in SPECS}
