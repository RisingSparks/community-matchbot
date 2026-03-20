// Runs in MAIN world - can access and patch page's fetch/XHR
// Broadcasts captured responses via CustomEvent (MAIN->ISOLATED bridge)

(function() {
  const origFetch = window.fetch;
  window.fetch = async function(...args) {
    const response = await origFetch.apply(this, args);
    const url = (typeof args[0] === 'string' ? args[0] : args[0]?.url) ?? '';
    if (url.includes('/api/graphql')) {
      response.clone().text().then((text) => {
        document.dispatchEvent(new CustomEvent('_fbgc', {detail: text}));
      }).catch((err) => {
        console.error('FBGC: error reading fetch response body', err);
      });
    }
    return response;
  };

  const OrigXHR = window.XMLHttpRequest;
  function CustomXHR() {
    const xhr = new OrigXHR();
    const origOpen = xhr.open;
    let isGraphQL = false;

    xhr.open = function(method, url) {
      if (typeof url === 'string' && url.includes('/api/graphql')) {
        isGraphQL = true;
      }
      return origOpen.apply(this, arguments);
    };

    xhr.addEventListener('load', function() {
      if (isGraphQL && xhr.responseText) {
        document.dispatchEvent(new CustomEvent('_fbgc', {detail: xhr.responseText}));
      }
    });

    return xhr;
  }
  window.XMLHttpRequest = CustomXHR;
  window.XMLHttpRequest.prototype = OrigXHR.prototype;
  Object.assign(window.XMLHttpRequest, OrigXHR);
})();
