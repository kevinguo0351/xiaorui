export async function locate():Promise<number>{
 if(!navigator.geolocation)throw Error('浏览器不支持定位，请说出附近地标。');
 const policy=(document as Document&{permissionsPolicy?:{allowsFeature:(s:string)=>boolean};featurePolicy?:{allowsFeature:(s:string)=>boolean}});
 if((policy.permissionsPolicy??policy.featurePolicy)?.allowsFeature('geolocation')===false)throw Error('当前内嵌浏览器不允许定位。请在 Safari 或 Chrome 打开本页，或说出附近地标。');
 const point=await new Promise<GeolocationPosition>((resolve,reject)=>{
  const timer=setTimeout(()=>reject({code:3}),15000);
  navigator.geolocation.getCurrentPosition(p=>{clearTimeout(timer);resolve(p)},e=>{clearTimeout(timer);reject(e)},{enableHighAccuracy:true,maximumAge:0,timeout:10000});
 }).catch((e:GeolocationPositionError)=>{
  throw Error(e.code===1?'定位未获授权。如果没有弹窗，请在 Safari 或 Chrome 打开本页并检查浏览器与 macOS 定位权限；也可以说出附近地标。':'暂时无法定位，请重试或说出附近地标。');
 });
 const response=await fetch('/api/location',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({latitude:point.coords.latitude,longitude:point.coords.longitude,accuracy:point.coords.accuracy,timestamp:point.timestamp})});
 const result=await response.json();if(!response.ok)throw Error(typeof result.detail==='string'?result.detail:'定位未能提交，请说出附近地标。');
 return point.coords.accuracy;
}
