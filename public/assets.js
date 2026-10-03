(() => {
 const packed=new Map(Object.entries(globalThis.ClezzyEmbedded?.assetData||{})),requests=new Map(),decoded=new Map();
 const base=()=>new URL(globalThis.ClezzyEmbedded?.assetBase||'./',document.baseURI||location.href);
 const url=path=>globalThis.ClezzyEmbedded?.imageData?.[path]||(/^(data:|https?:|blob:)/.test(path)?path:new URL(path.replace(/^\.\//,''),base()).href);
 globalThis.ClezzyAsset=(path,data)=>packed.set(path,data);
 async function animation(path){
  const value=globalThis.ClezzyEmbedded?.animations?.[path];if(value)return value;if(decoded.has(path))return decoded.get(path);if(requests.has(path))return requests.get(path);
  const task=(async()=>{if(!packed.has(path))await new Promise((resolve,reject)=>{const script=document.createElement('script');script.src=url(path.replace(/\.(tgs|json)$/i,'.asset.js'));script.async=true;script.onload=()=>{script.remove();packed.has(path)?resolve():reject(Error('Пустой файл анимации'));};script.onerror=()=>{script.remove();reject(Error('Анимация не найдена'));};document.head.append(script);});const text=atob(packed.get(path)),bytes=Uint8Array.from(text,c=>c.charCodeAt(0));const result=JSON.parse(pako.ungzip(bytes,{to:'string'}));decoded.set(path,result);packed.delete(path);if(decoded.size>40)decoded.delete(decoded.keys().next().value);return result;})();requests.set(path,task);try{return await task;}finally{requests.delete(path);}
 }
 globalThis.ClezzyAssets={url,animation};
})();
