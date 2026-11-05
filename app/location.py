"""Short-lived browser location, isolated by owner; never personal memory."""
import math
import time
from pydantic import BaseModel, ConfigDict, Field


class BrowserLocation(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    latitude: float = Field(ge=-90, le=90, strict=True)
    longitude: float = Field(ge=-180, le=180, strict=True)
    accuracy: float = Field(gt=0, le=100000, strict=True)
    timestamp: float = Field(gt=0, strict=True)


def gcj02(lng, lat):
    """WGS84 browser coordinates to GCJ02 for mainland map/ride providers."""
    if not (72.004 <= lng <= 137.8347 and .8293 <= lat <= 55.8271):
        return lng,lat
    x,y=lng-105,lat-35
    a=-100+2*x+3*y+.2*y*y+.1*x*y+.2*math.sqrt(abs(x))
    b=300+x+2*y+.1*x*x+.1*x*y+.1*math.sqrt(abs(x))
    a+=(20*math.sin(6*x*math.pi)+20*math.sin(2*x*math.pi))*2/3
    a+=(20*math.sin(y*math.pi)+40*math.sin(y/3*math.pi))*2/3
    a+=(160*math.sin(y/12*math.pi)+320*math.sin(y*math.pi/30))*2/3
    b+=(20*math.sin(6*x*math.pi)+20*math.sin(2*x*math.pi))*2/3
    b+=(20*math.sin(x*math.pi)+40*math.sin(x/3*math.pi))*2/3
    b+=(150*math.sin(x/12*math.pi)+300*math.sin(x/30*math.pi))*2/3
    rad=lat/180*math.pi
    magic=1-.00669342162296594323*math.sin(rad)**2
    a=a*180/((6378245*(1-.00669342162296594323))/(magic*math.sqrt(magic))*math.pi)
    b=b*180/(6378245/math.sqrt(magic)*math.cos(rad)*math.pi)
    return lng+b,lat+a


class LocationStore:
    def __init__(self):
        self.values={}

    def put(self,owner,point):
        now=time.time()
        if not -5 <= now-point.timestamp/1000 <= 120:
            raise ValueError('定位结果已过期，请重新定位。')
        if point.accuracy>1000:
            raise ValueError('定位范围太大，请说出附近地标，或重新定位。')
        self.values={k:v for k,v in self.values.items() if now-v['received_at']<120}
        if len(self.values)>=256:self.values.pop(next(iter(self.values)))
        lng,lat=gcj02(point.longitude,point.latitude)
        self.values[owner]={'longitude':lng,'latitude':lat,'accuracy':point.accuracy,
                            'received_at':now,'coordinate_system':'GCJ02'}

    def get(self,owner):
        point=self.values.get(owner)
        if point and time.time()-point['received_at']<120:return dict(point)
        self.values.pop(owner,None)
        return None

    def clear(self,owner):
        self.values.pop(owner,None)
