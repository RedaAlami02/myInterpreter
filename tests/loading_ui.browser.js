// Run with a Playwright page and the contents of app.js/global.css.
async function testLoadingUI(page, script, css) {
  await page.setViewportSize({ width: 1365, height: 768 });
  await page.route('https://loading.example.invalid/**', route => route.fulfill({
    contentType: 'text/html', body: '<!doctype html><html lang="fr"><head><title>Loading preview — synthetic data</title></head><body><main style="max-width:900px;margin:60px auto;padding:24px"><h1>Aperçu du chargement</h1><p>Données fictives · aucun compte connecté</p><a id="next" href="/next">Autre page</a><form data-loading><button name="first" value="1" type="submit">Premier</button><button name="save" value="yes" type="submit" data-loading-text="Enregistrement…">Enregistrer</button></form><div id="mkt-loading"></div></main></body></html>'
  }));
  await page.goto('https://loading.example.invalid/');
  // Avoid contacting font services in this isolated fixture.
  await page.addStyleTag({ content: css.replace(/^@import[^\n]+\n/gm, '') });
  await page.evaluate(() => {
    let now = 0, id = 0;
    const tasks = new Map();
    window.setTimeout = (fn, delay) => { tasks.set(++id, { at: now + delay, fn }); return id; };
    window.clearTimeout = key => tasks.delete(key);
    window.advanceLoadingTime = ms => {
      now += ms;
      for (const [key, task] of [...tasks]) {
        if (task.at <= now && tasks.delete(key)) task.fn();
      }
    };
  });
  await page.addScriptTag({ content: script });
  const results = await page.evaluate(async () => {
    const passed = [];
    const check = (condition, message) => { if (!condition) throw new Error(message); passed.push(message); };
    const indicator = document.querySelector('.page-loading');
    const status = document.querySelector('.page-loading__status');
    const link = document.querySelector('#next');
    const form = document.querySelector('form');
    const button = form.querySelector('[name=save]');
    const reset = () => window.dispatchEvent(new Event('pageshow'));
    const dispatch = async (type, target, props = {}, cancel = false) => {
      const event = new Event(type, { bubbles: true, cancelable: true });
      for (const [key, value] of Object.entries({ target, button: 0, ...props })) {
        Object.defineProperty(event, key, { value });
      }
      if (cancel) event.preventDefault();
      document.dispatchEvent(event);
      await Promise.resolve();
      return event;
    };
    check(indicator.hidden && !status.textContent, 'No loading screen on initial render');
    check(document.querySelectorAll('#mkt-loading .skeleton').length === 6, 'Skeleton replaces only the async placeholder');
    check(getComputedStyle(document.querySelector('.skeleton')).backgroundColor !== 'rgba(0, 0, 0, 0)', 'Skeleton uses the existing theme colors');
    check(document.querySelector('.content-loading__preview').getAttribute('aria-hidden') === 'true', 'Skeleton decoration hidden from assistive technology');
    for (const [label, attrs, props, cancelled] of [
      ['modified click', {}, { ctrlKey: true }, false],
      ['middle click', {}, { button: 1 }, false],
      ['new tab', { target: '_blank' }, {}, false],
      ['external link', { href: 'https://example.invalid/' }, {}, false],
      ['anchor', { href: '#section' }, {}, false],
      ['download', { download: '' }, {}, false],
      ['opt out', { 'data-no-overlay': '' }, {}, false],
      ['cancelled navigation', {}, {}, true],
    ]) {
      link.removeAttribute('target'); link.removeAttribute('download'); link.removeAttribute('data-no-overlay'); link.setAttribute('href', '/next');
      for (const [key, value] of Object.entries(attrs)) link.setAttribute(key, value);
      await dispatch('click', link, props, cancelled);
      window.advanceLoadingTime(250);
      check(indicator.hidden && !status.textContent, `Ignore ${label}`);
    }
    await dispatch('click', link);
    window.advanceLoadingTime(179);
    check(indicator.hidden, 'Fast navigation does not flash');
    window.advanceLoadingTime(1);
    check(!indicator.hidden && status.textContent.includes('Chargement'), 'Delayed navigation feedback');
    check(getComputedStyle(indicator).pointerEvents === 'none', 'Navigation does not block the page');
    reset();
    check(indicator.hidden && !status.textContent, 'Back/forward restores idle state');
    window.advanceLoadingTime(30000);
    await dispatch('click', link);
    window.advanceLoadingTime(180);
    check(!indicator.hidden, 'Navigation works long after initial page load');
    window.advanceLoadingTime(20000);
    check(indicator.hidden && status.textContent.includes('prolongé'), 'Timeout is attached to each navigation');
    reset();
    await dispatch('submit', form, { submitter: button }, true);
    check(!form.hasAttribute('aria-busy'), 'Cancelled form stays idle');
    await dispatch('submit', form, { submitter: button });
    check(button.textContent === 'Enregistrement…' && form.querySelector('[name=first]').textContent === 'Premier', 'Actual submitter receives feedback');
    check(new FormData(form, button).get('save') === 'yes' && !button.disabled, 'Submitter name and value remain in POST payload');
    const duplicate = await dispatch('submit', form, { submitter: button });
    check(duplicate.defaultPrevented, 'Repeat submission is prevented while pending');
    reset();
    check(button.textContent === 'Enregistrer' && !button.hasAttribute('aria-disabled') && !form.hasAttribute('aria-busy'), 'Back/forward restores form controls');
    await dispatch('submit', form, { submitter: button });
    window.advanceLoadingTime(20000);
    check(status.textContent.includes('Vérifiez le résultat') && button.textContent === 'Enregistrer', 'Slow form recovers with explicit outcome warning');
    reset();
    return passed;
  });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  const animation = await page.locator('.page-loading__track').evaluate(el => getComputedStyle(el).animationName);
  if (animation !== 'none') throw new Error('Reduced motion not honored');
  results.push('Reduced motion uses static feedback');
  await page.setViewportSize({ width: 412, height: 915 });
  const fits = await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth);
  if (!fits) throw new Error('Mobile layout overflows');
  results.push('Mobile layout fits 412px viewport');
  return results;
}
