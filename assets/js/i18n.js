(function () {
  'use strict';
  const config = JSON.parse(document.getElementById('ui-locale').textContent);
  const normalize = text => String(text).trim().replace(/\s+/g, ' ');
  window.I18n = {
    locale: config.locale,
    t(text, values = {}) {
      let result = config.messages[normalize(text)] ?? text;
      for (const [key, value] of Object.entries(values)) result = result.replaceAll('{' + key + '}', String(value));
      return result;
    }
  };
  document.addEventListener('change', event => {
    if (event.target.matches('[data-language-select]')) event.target.form.requestSubmit();
  });
})();
