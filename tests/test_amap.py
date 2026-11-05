import unittest
from types import SimpleNamespace
from unittest.mock import patch,AsyncMock
import httpx
from app.amap import Amap,SCHEMAS


class AmapTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_key_never_sends_request(self):
        with patch.dict('os.environ',{'AMAP_KEY':''}),patch('app.amap.dotenv_values',return_value={}):
            result=await Amap().dispatch(SimpleNamespace(services={}),'amap_weather',{'city':'北京'})
        self.assertIn('AMAP_KEY',result['error'])

    async def test_official_endpoint_key_and_service_refusal(self):
        requests=[]
        def handler(request):
            requests.append(request)
            return httpx.Response(200,json={'status':'0','info':'sensitive response test-key'})
        client=Amap(lambda **kw:httpx.AsyncClient(transport=httpx.MockTransport(handler),**kw))
        with patch.dict('os.environ',{'AMAP_KEY':'test-key'}):
            with self.assertRaisesRegex(ValueError,'权限') as result:
                await client.get('/v3/geocode/geo',{'address':'北京'})
            self.assertNotIn('test-key',str(result.exception))
        self.assertEqual(requests[0].url.host,'restapi.amap.com')
        self.assertEqual(requests[0].url.params['key'],'test-key')
        with self.assertRaises(ValueError):await client.get('https://evil.invalid',{})

    async def test_candidate_selection_route_and_no_fabrication(self):
        client=Amap();session=SimpleNamespace(services={})
        client.get=AsyncMock(side_effect=[
            {'pois':[{'name':'起点','location':'116.4,39.9'}]},
            {'geocodes':[{'formatted_address':'终点','location':'116.41,39.91'}]},
            {'route':{'paths':[{'distance':'1500','cost':{'duration':'1200'},'steps':[{'instruction':'向北步行'}]}]}}])
        await client.dispatch(session,'amap_search_places',{'keyword':'起点','purpose':'origin'})
        await client.dispatch(session,'amap_geocode',{'address':'终点','purpose':'destination'})
        result=await client.dispatch(session,'amap_route',{'origin_index':1,'destination_index':1})
        self.assertEqual(result['routes'][0]['duration_seconds'],'1200')
        self.assertEqual(result['routes'][0]['instructions'],['向北步行'])
        self.assertTrue(result['map_url'].startswith('https://uri.amap.com/navigation?'))
        self.assertEqual(client.get.call_args.args[1]['origin'],'116.4,39.9')
        before=client.get.await_count
        bad=await client.dispatch(session,'amap_route',{'origin_index':True,'destination_index':1})
        self.assertIn('error',bad);self.assertEqual(client.get.await_count,before)

    async def test_failed_research_clears_old_candidates(self):
        client=Amap();client.get=AsyncMock(side_effect=ValueError('服务失败'))
        session=SimpleNamespace(services={'amap':{'origin':[{'name':'old'}]}})
        self.assertIn('error',await client.dispatch(session,'amap_search_places',{'keyword':'new','purpose':'origin'}))
        self.assertNotIn('origin',session.services['amap'])

    async def test_weather_uses_adcode_and_report_time(self):
        client=Amap();client.get=AsyncMock(side_effect=[{'geocodes':[{'adcode':'110000'}]},
            {'lives':[{'city':'北京','weather':'晴','temperature':'20','reporttime':'test-time'}]}])
        result=await client.dispatch(SimpleNamespace(services={}),'amap_weather',{'city':'北京'})
        self.assertEqual(result['weather'][0]['reporttime'],'test-time')
        self.assertEqual(client.get.call_args.args[1]['city'],'110000')

    async def test_tools_registered_and_allowed_in_query_mode(self):
        from app.skills import SCHEMAS as ALL
        from app.read_only import QUERY_TOOLS
        self.assertTrue(set(SCHEMAS)<=set(ALL))
        self.assertTrue(set(SCHEMAS)<=set(QUERY_TOOLS))
