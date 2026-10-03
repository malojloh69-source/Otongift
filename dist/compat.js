/* Browser compatibility for the device-local demo only. Server auth stays in Python. */
(() => {
  'use strict';
  const hex = bytes => Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('');
  const encode = text => new TextEncoder().encode(text);
  const K = new Uint32Array([
    0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
    0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
    0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
    0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
    0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
    0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
    0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
    0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2
  ]);
  const rotate = (n,b) => (n >>> b) | (n << (32-b));
  function digest(bytes) {
    const data = new Uint8Array(Math.ceil((bytes.length+9)/64)*64);
    data.set(bytes);data[bytes.length]=0x80;
    const view=new DataView(data.buffer),bits=bytes.length*8;
    view.setUint32(data.length-8,Math.floor(bits/0x100000000));view.setUint32(data.length-4,bits>>>0);
    const H=new Uint32Array([0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19]);
    const w=new Uint32Array(64);
    for(let offset=0;offset<data.length;offset+=64){
      for(let i=0;i<16;i++)w[i]=view.getUint32(offset+i*4);
      for(let i=16;i<64;i++){
        const s0=rotate(w[i-15],7)^rotate(w[i-15],18)^(w[i-15]>>>3);
        const s1=rotate(w[i-2],17)^rotate(w[i-2],19)^(w[i-2]>>>10);
        w[i]=(w[i-16]+s0+w[i-7]+s1)>>>0;
      }
      let [a,b,c,d,e,f,g,h]=H;
      for(let i=0;i<64;i++){
        const t1=(h+(rotate(e,6)^rotate(e,11)^rotate(e,25))+((e&f)^(~e&g))+K[i]+w[i])>>>0;
        const t2=((rotate(a,2)^rotate(a,13)^rotate(a,22))+((a&b)^(a&c)^(b&c)))>>>0;
        h=g;g=f;f=e;e=(d+t1)>>>0;d=c;c=b;b=a;a=(t1+t2)>>>0;
      }
      const values=[a,b,c,d,e,f,g,h];for(let i=0;i<8;i++)H[i]=(H[i]+values[i])>>>0;
    }
    const out=new Uint8Array(32),result=new DataView(out.buffer);
    H.forEach((n,i)=>result.setUint32(i*4,n));return out;
  }
  const concat=(a,b)=>{const out=new Uint8Array(a.length+b.length);out.set(a);out.set(b,a.length);return out;};
  function hmacBytes(key,text){
    let k=encode(key);if(k.length>64)k=digest(k);
    const inner=new Uint8Array(64).fill(0x36),outer=new Uint8Array(64).fill(0x5c);
    for(let i=0;i<k.length;i++){inner[i]^=k[i];outer[i]^=k[i];}
    return digest(concat(outer,digest(concat(inner,encode(text)))));
  }
  const clone = value => typeof structuredClone==='function'?structuredClone(value):JSON.parse(JSON.stringify(value));
  const memoryStorage=new Map();
  function storage(){try{const s=globalThis.localStorage;if(s)return s;}catch{}const data=memoryStorage;return {getItem:key=>data.get(key)||null,setItem:(key,value)=>data.set(key,String(value)),removeItem:key=>data.delete(key)};}
  function randomUUID(){
    if(globalThis.crypto?.randomUUID)return crypto.randomUUID();
    if(!globalThis.crypto?.getRandomValues)throw Error('Браузер не поддерживает случайные числа. Открой HTML в современном браузере.');
    const bytes=crypto.getRandomValues(new Uint8Array(16));bytes[6]=(bytes[6]&15)|64;bytes[8]=(bytes[8]&63)|128;
    const text=hex(bytes);return `${text.slice(0,8)}-${text.slice(8,12)}-${text.slice(12,16)}-${text.slice(16,20)}-${text.slice(20)}`;
  }
  async function copyText(text){
    if(globalThis.navigator?.clipboard?.writeText){try{await navigator.clipboard.writeText(text);return;}catch{}}
    const input=document.createElement('textarea');input.value=text;input.style.cssText='position:fixed;top:0;left:-9999px';
    document.body.append(input);input.select();let ok=false;try{ok=document.execCommand('copy');}finally{input.remove();}
    if(!ok)throw Error('Браузер не разрешил копирование.');
  }
  globalThis.ClezzyPlatform={
    clone,storage,randomUUID,copyText,
    sha256:async text=>crypto.subtle?hex(new Uint8Array(await crypto.subtle.digest('SHA-256',encode(text)))):hex(digest(encode(text))),
    hmac:async(key,text)=>{
      if(!crypto.subtle)return hex(hmacBytes(key,text));
      const k=await crypto.subtle.importKey('raw',encode(key),{name:'HMAC',hash:'SHA-256'},false,['sign']);
      return hex(new Uint8Array(await crypto.subtle.sign('HMAC',k,encode(text))));
    }
  };
})();
