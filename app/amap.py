"""Fixed official Amap REST endpoints; query-only, no mock fallback."""
import os
from pathlib import Path
from urllib.parse import urlencode
import httpx
from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
from app.life_services import _credential_filter

ROOT=Path(__file__).resolve().parents[1]


class Args(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)


class Search(Args):
    keyword:str=Field(min_length=1,max_length=100)
    city:str=Field(default='北京',min_length=1,max_length=30)
    purpose:Literal['origin','destination']='destination'


class Geocode(Args):
    address:str=Field(min_length=1,max_length=200)
    city:str=Field(default='北京',min_length=1,max_length=30)
    purpose:Literal['origin','destination']='destination'


class Route(Args):
    origin_index:int=Field(ge=1,le=5,strict=True)
    destination_index:int=Field(ge=1,le=5,strict=True)
    mode:Literal['walking','driving']='walking'


class Weather(Args):
    city:str=Field(default='北京',min_length=1,max_length=30)


SCHEMAS={
 'amap_search_places':(Search,'用高德官方API搜索真实地点，保存本轮起点或终点候选供用户选择。默认北京，不猜当前位置。'),
 'amap_geocode':(Geocode,'用高德官方地理编码将用户明确提供的地址解析为地点候选；家必须来自已确认资料，不能猜地址。'),
 'amap_route':(Route,'按用户确认的本轮起终点序号规划高德步行或驾车路线，返回耗时距离及道路指引。这不是持续导航、也不会叫车。'),
 'amap_weather':(Weather,'查询指定城市的高德实时天气，带官方报告时间；不是当前位置定位。'),
}


def configured():
    return bool(os.environ.get('AMAP_KEY') or dotenv_values(ROOT/'.env').get('AMAP_KEY'))


class Amap:
    def __init__(self,client_factory=None):
        self.client_factory=client_factory or httpx.AsyncClient

    async def get(self,path,params):
        if path not in {'/v3/place/text','/v3/geocode/geo','/v3/weather/weatherInfo','/v5/direction/walking','/v5/direction/driving'}:
            raise ValueError('未开放的高德接口。')
        key=os.environ.get('AMAP_KEY') or dotenv_values(ROOT/'.env').get('AMAP_KEY')
        if not key:raise ValueError('高德尚未配置，请家人在本地 .env 填写 Web服务类型 AMAP_KEY。')
        _credential_filter.secrets.add(key)
        try:
            async with self.client_factory(timeout=15,follow_redirects=False) as client:
                response=await client.get('https://restapi.amap.com'+path,params={**params,'key':key,'output':'JSON'})
                response.raise_for_status()
                data=response.json()
        except Exception:
            raise ValueError('高德连接或响应异常，请稍后再查，没有使用假路线。') from None
        if not isinstance(data,dict) or str(data.get('status'))!='1':
            raise ValueError('高德未接受查询，请核对 Key 类型、服务权限和额度。')
        return data

    async def dispatch(self,session,name,arguments):
        try:
            args=SCHEMAS[name][0].model_validate(arguments)
            state=session.services.setdefault('amap',{})
            if name in {'amap_search_places','amap_geocode'}:
                state.pop(args.purpose,None)
                if name=='amap_search_places':
                    data=await self.get('/v3/place/text',{'keywords':args.keyword,'city':args.city,'citylimit':'true','offset':5})
                    rows=data.get('pois',[])
                else:
                    data=await self.get('/v3/geocode/geo',{'address':args.address,'city':args.city})
                    rows=data.get('geocodes',[])
                candidates=[]
                for item in rows[:5]:
                    location=item.get('location','')
                    if not isinstance(location,str) or len(location.split(','))!=2:continue
                    lng,lat=map(float,location.split(','))
                    if not (-180<=lng<=180 and -90<=lat<=90):continue
                    candidates.append({'name':item.get('name') or item.get('formatted_address'),
                        'address':item.get('address') or item.get('formatted_address'),
                        'location':location,'adcode':item.get('adcode')})
                state[args.purpose]=candidates
                return {'places':[dict(p,index=i+1) for i,p in enumerate(candidates)],'purpose':args.purpose,
                    'next':'请用户核对具体地点，不自动把同名地点当作目的地。'}
            if name=='amap_weather':
                geo=await self.get('/v3/geocode/geo',{'address':args.city,'city':args.city})
                cities=geo.get('geocodes',[])
                if len(cities)!=1 or not cities[0].get('adcode'):raise ValueError('城市不明确，请提供省市或区县。')
                data=await self.get('/v3/weather/weatherInfo',{'city':cities[0]['adcode'],'extensions':'base'})
                return {'weather':[{k:p.get(k) for k in ('city','weather','temperature','winddirection','windpower','humidity','reporttime')} for p in data.get('lives',[])[:3]]}
            origins=state.get('origin',[]);destinations=state.get('destination',[])
            if args.origin_index>len(origins) or args.destination_index>len(destinations):raise ValueError('请先查询并确认本轮起点和目的地。')
            origin=origins[args.origin_index-1];destination=destinations[args.destination_index-1]
            data=await self.get('/v5/direction/'+args.mode,{'origin':origin['location'],'destination':destination['location'],'show_fields':'cost'})
            paths=data.get('route',{}).get('paths',[])
            if not paths:raise ValueError('当前没有可用路线，请换地点或出行方式。')
            return {'origin':origin['name'],'destination':destination['name'],'mode':args.mode,
                'routes':[{'distance_meters':p.get('distance'),'duration_seconds':p.get('cost',{}).get('duration'),
                    'instructions':[s['instruction'] for s in p.get('steps',[])[:12] if s.get('instruction')]} for p in paths[:3]],
                'map_url':'https://uri.amap.com/navigation?'+urlencode({'from':origin['location']+','+origin['name'],'to':destination['location']+','+destination['name'],'mode':'walk' if args.mode=='walking' else 'car','src':'xiaorui','coordinate':'gaode'}),
                'note':'高德路线规划快照，不是实时逐步导航，不会叫车。'}
        except ValueError as exc:
            from pydantic import ValidationError
            return {'error':'请补充正确的地点、城市或候选序号。' if isinstance(exc,ValidationError) else str(exc)}
        except Exception:
            return {'error':'高德返回的数据暂不支持，没有生成假路线或天气。'}
