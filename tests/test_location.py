import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
import httpx
from pydantic import ValidationError
from app.location import BrowserLocation, LocationStore, gcj02
from app.didi_scenario import DidiScenario


def point(**changes):
    return BrowserLocation.model_validate(dict(latitude=39.9,longitude=116.4,
        accuracy=20.,timestamp=time.time()*1000,**changes))


class LocationTests(unittest.IsolatedAsyncioTestCase):
    async def test_owner_expiry_and_bad_accuracy(self):
        store=LocationStore();store.put('a',point())
        self.assertIsNone(store.get('b'))
        self.assertIsNotNone(store.get('a'))
        with patch('app.location.time.time',return_value=time.time()+121):
            self.assertIsNone(store.get('a'))
        for data in ({'latitude':True},{'longitude':float('nan')},{'accuracy':float('inf')}):
            with self.assertRaises(ValidationError):
                BrowserLocation.model_validate({'latitude':39.9,'longitude':116.4,'accuracy':20.,'timestamp':time.time()*1000,**data})
        for accuracy,age in ((1500.,0),(20.,200)):
            with self.assertRaises(ValueError):
                store.put('a',BrowserLocation(latitude=39.9,longitude=116.4,accuracy=accuracy,timestamp=(time.time()-age)*1000))

    async def test_coordinate_system(self):
        lng,lat=gcj02(116.397128,39.916527)
        self.assertAlmostEqual(lng,116.403372,places=5)
        self.assertAlmostEqual(lat,39.917931,places=5)
        self.assertEqual(gcj02(-.1,51.5),(-.1,51.5))

    async def test_location_tool_and_stale_origin_cannot_estimate(self):
        store=LocationStore();provider=SimpleNamespace(call=AsyncMock())
        tool=DidiScenario(Mock(),provider,store.get)
        session=SimpleNamespace(services={})
        events=[]
        result=await tool.dispatch(session,'a','didi_current_location',{},events)
        self.assertIn('error',result)
        self.assertEqual(events,[{'type':'location_request'}])
        store.put('a',point())
        result=await tool.dispatch(session,'a','didi_current_location',{},[])
        self.assertEqual(result['accuracy_meters'],20)
        session.services['didi']['origin'][0]['location_expires_at']=time.time()-1
        result=await tool.dispatch(session,'a','didi_estimate_ride',{'origin_index':1,'destination_index':1},[])
        self.assertIn('过期',result['error'])
        provider.call.assert_not_awaited()

    async def test_api_owner_validation_and_invalidation(self):
        import app.main as api
        fake=SimpleNamespace(locations=LocationStore(),actions=Mock())
        with patch.object(api,'agent',fake):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api.app),base_url='http://localhost') as client:
                data=point().model_dump()
                response=await client.post('/api/location',json=data)
                self.assertEqual(response.status_code,200)
                owner=client.cookies['pa_session']
                self.assertIsNotNone(fake.locations.get(owner))
                fake.actions.invalidate_pending.assert_called_with(owner)
                client.cookies.clear()
                await client.delete('/api/location')
                self.assertIsNotNone(fake.locations.get(owner))
                data['latitude']=True
                self.assertEqual((await client.post('/api/location',json=data)).status_code,422)
