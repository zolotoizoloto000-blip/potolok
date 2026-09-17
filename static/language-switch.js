(function(){
  function initLanguageSwitchers(){
    document.querySelectorAll('[data-language-switcher]').forEach(function(w){
      var trigger=w.querySelector('[data-language-trigger]');
      if(!trigger)return;
      trigger.addEventListener('click',function(e){e.preventDefault();e.stopPropagation();var open=!w.classList.contains('open');document.querySelectorAll('[data-language-switcher].open').forEach(function(x){x.classList.remove('open');});w.classList.toggle('open',open);trigger.setAttribute('aria-expanded',open?'true':'false');});
      w.querySelectorAll('[data-language-url]').forEach(function(item){
        item.addEventListener('click',function(e){e.preventDefault();e.stopPropagation();var url=item.getAttribute('data-language-url');if(url) window.location.assign(url);});
      });
    });
    document.addEventListener('click',function(){document.querySelectorAll('[data-language-switcher].open').forEach(function(w){w.classList.remove('open');var b=w.querySelector('[data-language-trigger]');if(b)b.setAttribute('aria-expanded','false');});});
    document.addEventListener('keydown',function(e){if(e.key==='Escape')document.dispatchEvent(new MouseEvent('click'));});
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',initLanguageSwitchers);else initLanguageSwitchers();
})();
