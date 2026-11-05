"""Official Amap public-landmark queries; no personal location or writes."""
import asyncio
import json
from types import SimpleNamespace
from app.amap import Amap,configured


async def main():
    if not configured():
        print('AMAP_KEY 未配置，尚未执行真实查询。')
        return 2
    service=Amap();session=SimpleNamespace(services={})
    steps=[('amap_search_places',{'keyword':'北京西站','purpose':'origin'}),
           ('amap_geocode',{'address':'北京市中国国家博物馆','purpose':'destination'}),
           ('amap_route',{'origin_index':1,'destination_index':1,'mode':'driving'}),
           ('amap_weather',{'city':'北京'})]
    for name,args in steps:
        result=await service.dispatch(session,name,args)
        print(json.dumps({'tool':name,'ok':'error' not in result,'error':result.get('error'),
            'result_count':len(result.get('places',result.get('routes',result.get('weather',[]))))},ensure_ascii=False))
        if 'error' in result:return 1
    return 0


if __name__=='__main__':raise SystemExit(asyncio.run(main()))
