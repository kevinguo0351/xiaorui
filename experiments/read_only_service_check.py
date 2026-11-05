"""Bounded public-landmark connectivity check; never queries private account data.

Run: uv run python experiments/read_only_service_check.py --output PATH
Only three fixed read tools are callable. Discovery and business-query outcomes
are separate. Reports omit provider payloads, credentials and exception strings.
"""
import argparse
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
import json
import logging
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from jsonschema import validate, ValidationError
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from app.life_services import OfficialMcp
from app.mcd import ENDPOINT, mcd_token, _payload

# Hand-reviewed public test points, never inferred as the user's current location.
CHECKS = {
    'mcd': {'tool': 'query-nearby-stores',
            'arguments': {'beType': 1, 'searchType': 2, 'city': '北京', 'keyword': '北京西站'},
            'source': 'https://open.mcd.cn/mcp', 'test_location': '北京西站（公开地标）'},
    'luckin': {'tool': 'queryShopList',
               'arguments': {'longitude': 116.397128, 'latitude': 39.916527, 'deptName': ''},
               'source': 'https://open.lkcoffee.com/mcp',
               'test_location': '北京公开固定测试坐标 116.397128,39.916527；非用户定位'},
    'didi': {'tool': 'maps_textsearch',
             'arguments': {'keywords': '北京西站', 'city': '北京市'},
             'source': 'https://mcp.didichuxing.com/', 'test_location': '北京西站（公开地标）'},
}
ALLOWED_TOOLS = frozenset(item['tool'] for item in CHECKS.values())


def configured(provider):
    return bool(mcd_token()) if provider == 'mcd' else OfficialMcp(provider).configured


@asynccontextmanager
async def connection(provider):
    if provider != 'mcd':
        async with OfficialMcp(provider).connection() as pair:
            yield pair
        return
    async with streamablehttp_client(
        ENDPOINT, headers={'Authorization': 'Bearer ' + mcd_token()},
        timeout=12, sse_read_timeout=20,
    ) as (read, write, _):
        async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=20)) as session:
            await session.initialize()
            tools, cursor = {}, None
            for _ in range(10):
                page = await session.list_tools(cursor=cursor)
                tools.update((tool.name, tool) for tool in page.tools)
                if not page.nextCursor:
                    break
                if cursor == page.nextCursor:
                    raise RuntimeError('Invalid pagination')
                cursor = page.nextCursor
            else:
                raise RuntimeError('Pagination limit')
            yield session, tools


def business_rows(provider, result):
    """Strictly recognize successful list queries; never save returned account data."""
    if provider == 'mcd':
        payload = _payload(result)
    else:
        if result.isError:
            raise ValueError('Provider rejected request')
        payload = result.structuredContent
        if payload is None:
            values = []
            for block in result.content:
                if block.type == 'text':
                    try:
                        values.append(json.loads(block.text))
                    except (ValueError, TypeError):
                        pass
            if len(values) != 1:
                raise ValueError('Unrecognized result')
            payload = values[0]
        if provider == 'luckin':
            if (not isinstance(payload, dict) or payload.get('code') != 0
                    or payload.get('success') is False or 'data' not in payload):
                raise ValueError('Business refusal')
            payload = payload['data']
    if not isinstance(payload, list) or any(not isinstance(row, dict) for row in payload):
        raise ValueError('Unrecognized list')
    return len(payload)


async def check_provider(provider, timeout=45):
    spec = CHECKS[provider]
    report = {'provider': provider, 'configured': configured(provider),
              'discovery': 'not_run', 'query': 'not_run', 'tool': spec['tool'],
              'source': spec['source'], 'test_location': spec['test_location'],
              'scope': 'public-fixed-inputs-only', 'transactions_attempted': 0}
    if not report['configured']:
        report.update(discovery='not_configured', query='not_configured')
        return report
    started = time.monotonic()
    phase = 'discovery'
    try:
        async with asyncio.timeout(timeout):
            async with connection(provider) as (session, tools):
                report.update(discovery='passed', discovered_tools=len(tools))
                tool = tools.get(spec['tool'])
                if tool is None:
                    report['query'] = 'tool_not_available'
                    return report
                # Exact provider+tool pairing is fixed in code, not configurable.
                if spec['tool'] not in ALLOWED_TOOLS:
                    raise RuntimeError('Not allowed')
                try:
                    validate(spec['arguments'], tool.inputSchema)
                except ValidationError:
                    report['query'] = 'schema_mismatch'
                    return report
                phase = 'query'
                result = await session.call_tool(spec['tool'], arguments=dict(spec['arguments']))
                count = business_rows(provider, result)
                report.update(query='passed' if count else 'empty', results_returned=count)
    except TimeoutError:
        report[phase] = 'timeout'
    except Exception:
        # Intentionally never stringify exceptions: DiDi URLs contain the key,
        # and provider errors may contain contact/address/order information.
        report[phase] = 'failed'
    finally:
        report['elapsed_seconds'] = round(time.monotonic() - started, 2)
    return report


async def matrix(providers=None, timeout=45):
    previous = logging.root.manager.disable
    # Transport libraries can log request URLs before an exception is caught.
    logging.disable(logging.CRITICAL)
    try:
        checks = [await check_provider(p, timeout) for p in (providers or CHECKS)]
    finally:
        logging.disable(previous)
    return {'checked_at_utc': datetime.now(timezone.utc).isoformat(),
            'mode': 'read-only-public-connectivity', 'checks': checks,
            'note': 'discovery=passed 仅表示目录可读；query=passed 才表示本次公开输入返回了可识别的非空结果。未验证下单、支付、私人地址或订单。'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--provider', action='append', choices=list(CHECKS))
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report = asyncio.run(matrix(args.provider))
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding='utf-8')
    print(rendered, end='')
    return 1 if any(c['query'] not in {'passed', 'empty', 'not_configured'} for c in report['checks']) else 0


if __name__ == '__main__':
    raise SystemExit(main())
