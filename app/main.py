"""Local chat, voice and confirmation API. Remote writes require exact approval."""
import os
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from app.mcd import McdService, McdRejectedError
from app.plans import PlanStore, PlanError
from app.recommendations import recommend
from app.voice import router as voice_router
from app.agent import AgentService, AgentError
from app.foundation_scheduler import FoundationScheduler

ROOT = Path(__file__).resolve().parents[1]
settings = dotenv_values(ROOT / '.env')
ORDER_ENABLED = str(os.environ.get('MCD_ORDER_ENABLED', settings.get('MCD_ORDER_ENABLED') or 'false')).lower() == 'true'


@asynccontextmanager
async def lifespan(app):
    await scheduler.start()
    try:
        yield
    finally:
        await scheduler.stop()


app = FastAPI(title='小瑞 · 本地生活助手', docs_url=None, redoc_url=None, lifespan=lifespan)
app.include_router(voice_router)
service = McdService()
plans = PlanStore(ROOT / '.local-data/plans.sqlite3')
agent = AgentService(service, plans)
scheduler = FoundationScheduler(agent.data_dir / 'scheduler')


@app.middleware('http')
async def local_boundary(request: Request, call_next):
    host = urlsplit('http://' + request.headers.get('host', '')).hostname
    if host not in {'localhost', '127.0.0.1', '::1'}:
        return JSONResponse({'detail': '仅允许本机访问。'}, status_code=403)
    origin = request.headers.get('origin')
    if origin and origin != f'{request.url.scheme}://{request.headers.get("host")}':
        return JSONResponse({'detail': '不允许跨来源操作。'}, status_code=403)
    if request.method in {'POST', 'PUT', 'PATCH'} and not request.headers.get('content-type', '').startswith('application/json'):
        return JSONResponse({'detail': '请使用 JSON 请求。'}, status_code=415)
    session = request.cookies.get('pa_session')
    fresh = not session or len(session) < 32 or len(session) > 128
    request.state.owner = secrets.token_urlsafe(32) if fresh else session
    response = await call_next(request)
    if fresh:
        response.set_cookie('pa_session', request.state.owner, httponly=True, samesite='strict', max_age=30*86400)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


@app.exception_handler(PlanError)
async def plan_error(request, error):
    return JSONResponse({'detail': error.message}, status_code=error.status)


@app.exception_handler(AgentError)
async def agent_error(request, error):
    return JSONResponse({'detail': error.message}, status_code=error.status)


class Body(BaseModel):
    model_config = ConfigDict(extra='forbid')


class ChatRequest(Body):
    text: str = Field(min_length=1, max_length=2000, strict=True)


@app.post('/api/chat')
async def chat(body: ChatRequest, request: Request):
    if not body.text.strip():
        raise HTTPException(422, '请先说一句话或输入消息。')
    return await agent.chat(request.state.owner, body.text.strip())


@app.post('/api/chat/reset')
async def reset_chat(body: Body, request: Request):
    await agent.reset(request.state.owner)
    return {'ok': True}


@app.get('/api/chat/history')
async def chat_history(request: Request):
    return agent.history(request.state.owner)


@app.get('/api/foundation')
async def foundation_status():
    return {**agent.foundation_status(), 'scheduler': scheduler.status()}


@app.get('/api/profile')
async def personal_profile():
    return agent.store.profile()


@app.get('/api/tasks')
async def personal_tasks(request: Request):
    return agent.tasks(request.state.owner)


class StoreSearch(Body):
    city: str = Field(min_length=1, max_length=80)
    keyword: str = Field(min_length=1, max_length=120)


class StoreChoice(Body):
    store_code: str = Field(min_length=1, max_length=80)


class ProductChoice(StoreChoice):
    product_code: str = Field(min_length=1, max_length=80)


class RecommendationRequest(StoreChoice):
    budget_cents: int = Field(default=3500, ge=100, le=100000, strict=True)
    limit: int = Field(default=3, ge=1, le=3, strict=True)


class Round(Body):
    round_id: str = Field(min_length=1, max_length=80)
    code: str = Field(min_length=1, max_length=80)
    quantity: int = Field(default=1, ge=1, le=5, strict=True)


class PlanRequest(ProductChoice):
    quantity: int = Field(default=1, ge=1, le=5, strict=True)
    rounds: list[Round] = Field(default_factory=list, max_length=30)


class Confirmation(Body):
    version: int = Field(ge=1, strict=True)
    confirmation_token: str = Field(min_length=1, max_length=200)
    confirmation_text: str


async def read_call(fn, *args):
    try:
        return await fn(*args)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    except RuntimeError:
        raise HTTPException(502, '麦当劳查询暂时失败，请稍后重新查询。') from None
    except Exception:
        raise HTTPException(502, '暂时无法连接麦当劳，请检查网络和配置。') from None


@app.get('/api/health')
async def health():
    return {'ok': True, 'order_execution_enabled': ORDER_ENABLED,
            'mcd_configured': bool(dotenv_values(ROOT / '.env').get('MCD_MCP_TOKEN')),
            'agent_configured': agent.configured}


@app.post('/api/mcd/stores')
async def stores(body: StoreSearch):
    return {'stores': await read_call(service.search_stores, body.city, body.keyword)}


@app.post('/api/mcd/menu')
async def menu(body: StoreChoice):
    return {'products': await read_call(service.menu, body.store_code)}


@app.post('/api/mcd/detail')
async def detail(body: ProductChoice):
    return {'detail': await read_call(service.detail, body.store_code, body.product_code)}


@app.post('/api/mcd/recommendations')
async def recommendations(body: RecommendationRequest):
    return await read_call(recommend, service, body.store_code, body.budget_cents, body.limit)


@app.post('/api/plans')
async def new_plan(body: PlanRequest, request: Request):
    prepared = await read_call(service.prepare_plan, body.model_dump())
    return {'plan': plans.create(request.state.owner, prepared)}


@app.get('/api/plans/{plan_id}')
async def get_plan(plan_id: str, request: Request):
    return {'plan': plans.get(plan_id, request.state.owner)}


@app.post('/api/plans/{plan_id}/cancel')
async def cancel(plan_id: str, request: Request):
    return {'plan': plans.cancel(plan_id, request.state.owner)}


@app.post('/api/plans/{plan_id}/confirm')
async def confirm(plan_id: str, body: Confirmation, request: Request):
    if body.confirmation_text != '确认下单':
        raise HTTPException(400, '需要明确确认下单。')
    if not ORDER_ENABLED:
        raise HTTPException(409, '当前仅核价和查看方案，真实下单尚未开启。')
    p, claimed = plans.claim(plan_id, request.state.owner, body.version, body.confirmation_token)
    if not claimed:
        return {'plan': plans.public(p)}
    try:
        quote = await service.requote(p['request'])
    except Exception:
        result = plans.update(plan_id, request.state.owner, status='needs_review',
                              version=p['version']+1, confirmation_token=secrets.token_urlsafe(32),
                              error='重新核价失败，尚未下单。请重新生成方案。', expires_at=0)
        return {'plan': result}
    if quote['amount_cents'] != p['amount_cents'] or p['request']['takeWayCode'] not in quote['take_way_codes']:
        if p['request']['takeWayCode'] not in quote['take_way_codes']:
            return {'plan': plans.update(plan_id, request.state.owner, status='expired', error='取餐方式已变化，请重新生成方案。')}
        return {'plan': plans.update(plan_id, request.state.owner, status='needs_review',
                                    amount_cents=quote['amount_cents'], version=p['version']+1,
                                    confirmation_token=secrets.token_urlsafe(32), expires_at=time.time()+300,
                                    error='价格已变化，请查看新金额并再次确认。')}
    plans.update(plan_id, request.state.owner, status='submitting')
    try:
        order = await service.create_order(p['request'])
        if not order.get('order_id'):
            result = plans.update(plan_id, request.state.owner, status='unknown', error='请求已发送，订单结果待核查，请勿重复下单。')
        else:
            # Do not expose raw account responses; a payment URL is not a paid order.
            result = plans.update(plan_id, request.state.owner, status='created',
                                  order={'order_id': order['order_id'], 'payment_url': order.get('payment_url')},
                                  error=None if order.get('payment_url') else '已创建订单，但暂未取得支付入口，请到官方渠道核查。')
    except McdRejectedError:
        result = plans.update(plan_id, request.state.owner, status='failed', error='麦当劳未接受订单，未自动重试。')
    except Exception:
        result = plans.update(plan_id, request.state.owner, status='unknown', error='订单结果待核查，请勿重复下单。')
    return {'plan': result}


DIST = ROOT / 'frontend/dist'
if (DIST / 'assets').exists():
    app.mount('/assets', StaticFiles(directory=DIST / 'assets'), name='assets')


@app.get('/')
async def home():
    if not (DIST / 'index.html').exists():
        raise HTTPException(503, '前端尚未构建，请先运行启动脚本。')
    return FileResponse(DIST / 'index.html')
