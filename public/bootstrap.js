(() => {
  globalThis.ClezzyBootTimer=setTimeout(()=>{
    if(globalThis.ClezzyReady)return;
    const message=document.querySelector('#app .boot p');
    if(message&&message.textContent.includes('Загружаем'))message.textContent='Не удалось загрузить приложение. Открой отдельный index.html из корня архива или запусти main.py.';
  },12000);
})();
