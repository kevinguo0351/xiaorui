export async function locate():Promise<number>{
 if(!navigator.geolocation)throw Error('浏览器不支持定位，请说出附近地标。');
 const point=await new Promise<GeolocationPosition>((resolve,reject)=>navigator.geolocation.getCurrentPosition(resolve,reject,{enableHighAccuracy:true,maximumAge:0,timeout:10000})).catch((e:GeolocationPositionError)=>{
  throw Error(e.code===1?'定位未获授权，请在浏览器和系统设置中允许定位，或说出附近地标。':'暂时无法定位，请说出附近地标。');
 });
 const response=await fetch('/api/location',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({latitude:point.coords.latitude,longitude:point.coords.longitude,accuracy:point.coords.accuracy,timestamp:point.timestamp})});
 const result=await response.json();if(!response.ok)throw Error(typeof result.detail==='string'?result.detail:'定位未能提交，请说出附近地标。');
 return point.coords.accuracy;
}
