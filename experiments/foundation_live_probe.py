"""Real nanobot/Ark foundation checks in a dedicated, ignored test workspace."""
import argparse
import asyncio
import json
from pathlib import Path

from app.agent import AgentService
from app.mcd import McdService
from app.plans import PlanStore

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / '.local-data/foundation-live-probe'


async def main(phase):
    DATA.mkdir(parents=True, exist_ok=True)
    agent = AgentService(McdService(), PlanStore(DATA / 'plans.sqlite3'), data_dir=DATA / 'personal-agent')
    owner = 'isolated-foundation-probe'
    if phase == 'save':
        await agent.reset(owner)
        text = '这是独立的虚构测试资料，不是使用者的真实信息。请长期记住：我的测试称呼是林叔。'
    elif phase == 'read':
        await agent.reset(owner)  # New SDK conversation, retain only the stable profile.
        text = '我之前请你记住的测试称呼是什么？请根据保存的资料回答。'
    elif phase == 'forget':
        text = '请忘记我保存的测试称呼，不要再使用它。'
    elif phase == 'session_save':
        await agent.reset(owner)
        text = '这轮对话的临时口令是蓝莓船，不要写入个人资料。请回复收到。'
    elif phase == 'session_read':
        text = '刚才这轮对话的临时口令是什么？'
    else:
        text = '你现在还记得我的测试称呼吗？不知道就直说，不要猜。'
    response = await agent.chat(owner, text)
    profile = agent.store.profile()
    report = {'phase': phase, 'runtime': response['runtime'], 'text': response['text'],
              'trace': response['trace'], 'facts': profile['facts'],
              'forget_epoch': profile['forget_epoch'],
              'history_messages': len(agent.history(owner)['messages'])}
    if phase.startswith('session_'):
        report['ok'] = not profile['facts'] and (phase == 'session_save' or '蓝莓船' in response['text'])
    elif phase in ('save', 'read'):
        report['ok'] = any('林叔' in v for v in profile['facts'].values()) and (phase == 'save' or '林叔' in response['text'])
    else:
        report['ok'] = not any('林叔' in v for v in profile['facts'].values()) and profile['forget_epoch'] > 0
        if phase == 'read_forgotten':
            report['ok'] = report['ok'] and '林叔' not in response['text']
    (DATA / (phase + '.json')).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=['save', 'read', 'forget', 'read_forgotten', 'session_save', 'session_read'])
    raise SystemExit(asyncio.run(main(parser.parse_args().phase)))
