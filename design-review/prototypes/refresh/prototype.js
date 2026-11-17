'use strict';
// Entirely invented fixtures. No account, service, or production data is read.
const holdings = [
  { name: 'Atlas Industrie', code: 'ATI', sector: 'Industrie', qty: 140, price: 412, cost: 380, day: 1.2 },
  { name: 'Rive Banque', code: 'RVB', sector: 'Finance', qty: 90, price: 535, cost: 510, day: -.4 },
  { name: 'Noria Énergie', code: 'NRE', sector: 'Industrie', qty: 120, price: 286, cost: 260, day: .8 },
  { name: 'Orbe Services', code: 'ORB', sector: 'Services', qty: 200, price: 128, cost: 135, day: -.65 },
  { name: 'Cap Finance', code: 'CPF', sector: 'Finance', qty: 60, price: 345, cost: 320, day: .35 },
  { name: 'Ligne Télécom', code: 'LGT', sector: 'Services', qty: 180, price: 92, cost: 88, day: .9 },
].map(row => ({ ...row, value: row.qty * row.price, gain: row.qty * (row.price - row.cost) }));
const total = holdings.reduce((sum, row) => sum + row.value, 0);
const invested = holdings.reduce((sum, row) => sum + row.qty * row.cost, 0);
const daily = holdings.reduce((sum, row) => sum + row.value - row.value / (1 + row.day / 100), 0);
const number = (value, digits = 0) => new Intl.NumberFormat('fr-FR', { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(value);
const signed = (value, digits = 0) => `${value >= 0 ? '+' : '−'}${number(Math.abs(value), digits)}`;
const root = document.documentElement;
const params = new URLSearchParams(location.search);
let direction = params.get('direction') === 'workspace' ? 'workspace' : 'ledger';
let theme = params.get('theme') === 'dark' ? 'dark' : 'light';
let view = params.get('view') === 'overview' ? 'overview' : 'portfolio';
let period = '3M', sort = 'value', ascending = false;
document.getElementById('total-value').innerHTML = `${number(total)}<small>MAD</small>`;
document.getElementById('total-return').textContent = `${signed(total - invested)} MAD (${signed((total / invested - 1) * 100, 2)} %)`;
document.getElementById('invested').textContent = `${number(invested)} MAD`;
document.getElementById('daily-change').textContent = `${signed(daily)} MAD`;
document.getElementById('gainers').textContent = holdings.filter(row => row.day > 0).length;
document.getElementById('losers').textContent = holdings.filter(row => row.day < 0).length;
const leader = [...holdings].sort((a, b) => b.day - a.day)[0];
document.getElementById('leader').textContent = `${leader.name} · ${signed(leader.day, 2)} %`;
function renderRows() {
  const query = document.getElementById('search').value.trim().toLocaleLowerCase('fr');
  const rows = holdings.filter(row => `${row.name} ${row.code} ${row.sector}`.toLocaleLowerCase('fr').includes(query));
  rows.sort((a, b) => (sort === 'name' ? a.name.localeCompare(b.name, 'fr') : a[sort] - b[sort]) * (ascending ? 1 : -1));
  document.getElementById('positions').innerHTML = rows.map(row => `<tr><td><div class="company"><span class="company-code">${row.code}</span><div><div class="company-name">${row.name}</div><div class="company-sector">${row.sector}</div></div></div></td><td>${row.qty}</td><td>${number(row.price, 2)}</td><td>${number(row.value)}</td><td class="${row.day >= 0 ? 'positive' : 'negative'}">${signed(row.day, 2)} %</td><td class="${row.gain >= 0 ? 'positive' : 'negative'}">${signed(row.gain)}</td><td class="weight-col">${number(row.value / total * 100, 1)} %<div class="weight-track"><span style="width:${row.value / total * 100}%"></span></div></td></tr>`).join('');
  document.getElementById('result-count').textContent = `${rows.length} société${rows.length !== 1 ? 's' : ''}`;
  document.getElementById('empty').hidden = rows.length > 0;
}
const sectors = ['Industrie', 'Finance', 'Services'].map(name => ({ name, weight: holdings.filter(row => row.sector === name).reduce((sum, row) => sum + row.value, 0) / total * 100 }));
document.querySelector('.allocation-bar').innerHTML = sectors.map(sector => `<span style="width:${sector.weight}%"></span>`).join('');
document.getElementById('allocation').innerHTML = sectors.map(sector => `<div class="allocation-row"><span><i></i>${sector.name}</span><span>${number(sector.weight, 1)} %</span></div>`).join('');
document.getElementById('largest-weight').textContent = `${number(Math.max(...holdings.map(row => row.value)) / total * 100, 1)} %`;
function renderChart() {
  const length = 45;
  const start = period === '1M' ? .978 : period === '1A' ? .85 : .94;
  const values = Array.from({ length }, (_, i) => total * (start + (1 - start) * i / (length - 1) + Math.sin(i * 1.8) * .005 + Math.sin(i * .45) * .009));
  values[length - 1] = total;
  const min = Math.min(...values) * .99, max = Math.max(...values) * 1.01;
  const points = values.map((value, i) => [i / (length - 1) * 600, 150 - (value - min) / (max - min) * 130]);
  const path = points.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
  document.getElementById('chart-line').setAttribute('d', path);
  document.getElementById('chart-fill').setAttribute('d', `${path} L600,165 L0,165 Z`);
  document.getElementById('chart-dot').setAttribute('cx', points.at(-1)[0]);
  document.getElementById('chart-dot').setAttribute('cy', points.at(-1)[1]);
  ['axis-max', 'axis-mid', 'axis-min'].forEach((id, i) => { document.getElementById(id).textContent = `${number((max - (max - min) * i / 2) / 1000)} k`; });
  const labels = period === '1M' ? ['18 sept.', '01 oct.', '18 oct.'] : period === '1A' ? ['Oct. 2025', 'Avr. 2026', 'Oct. 2026'] : ['Juillet', 'Août', 'Septembre', 'Octobre'];
  document.getElementById('chart-months').innerHTML = labels.map(label => `<span>${label}</span>`).join('');
  document.querySelectorAll('[data-period]').forEach(button => { button.classList.toggle('active', button.dataset.period === period); button.setAttribute('aria-pressed', String(button.dataset.period === period)); });
}
function renderMode() {
  root.dataset.direction = direction; root.dataset.theme = theme; root.dataset.view = view;
  document.querySelectorAll('button[data-direction]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.direction === direction)));
  document.querySelectorAll('[data-view]').forEach(button => {
    if (button === root) return;
    button.classList.toggle('selected', button.dataset.view === view);
    if (button.dataset.view === view) button.setAttribute('aria-current', 'page'); else button.removeAttribute('aria-current');
  });
  document.getElementById('theme').innerHTML = `◐ <span>Thème ${theme === 'light' ? 'sombre' : 'clair'}</span>`;
  document.getElementById('theme').setAttribute('aria-label', `Passer au thème ${theme === 'light' ? 'sombre' : 'clair'}`);
  document.getElementById('page-title').innerHTML = view === 'portfolio' ? 'Portefeuille<span>.</span>' : 'Vue d’ensemble<span>.</span>';
  document.getElementById('eyebrow').textContent = view === 'portfolio' ? 'VOTRE CAPITAL, EN PERSPECTIVE' : 'PRENDRE DU RECUL, CHAQUE JOUR';
  document.getElementById('page-description').textContent = view === 'portfolio' ? 'L’essentiel de vos positions, sans perdre la vue d’ensemble.' : 'Votre situation en un regard. Les mouvements qui méritent votre attention.';
  document.getElementById('positions-title').innerHTML = view === 'portfolio' ? 'Vos positions <span class="count">06</span>' : 'Les mouvements du jour <span class="count">06</span>';
  document.getElementById('positions-kicker').textContent = view === 'portfolio' ? 'LE DÉTAIL QUI COMPTE' : 'VOTRE PORTEFEUILLE AUJOURD’HUI';
  document.querySelectorAll('[data-sort]').forEach(item => { item.parentElement.setAttribute('aria-sort', item.dataset.sort === sort ? (ascending ? 'ascending' : 'descending') : 'none'); item.querySelector('span').textContent = item.dataset.sort === sort ? (ascending ? '↑' : '↓') : '↕'; });
  history.replaceState(null, '', `?direction=${direction}&theme=${theme}&view=${view}`);
  document.getElementById('announcement').textContent = `${direction === 'ledger' ? 'Ledger' : 'Workspace'}, thème ${theme === 'light' ? 'clair' : 'sombre'}`;
}
document.querySelectorAll('button[data-direction]').forEach(button => button.addEventListener('click', () => { direction = button.dataset.direction; renderMode(); }));
document.querySelectorAll('button[data-view]').forEach(button => button.addEventListener('click', () => {
  view = button.dataset.view;
  sort = view === 'overview' ? 'day' : 'value'; ascending = false;
  document.querySelectorAll('[data-sort]').forEach(item => { item.parentElement.setAttribute('aria-sort', item.dataset.sort === sort ? 'descending' : 'none'); item.querySelector('span').textContent = item.dataset.sort === sort ? '↓' : '↕'; });
  renderRows(); renderMode();
}));
document.getElementById('theme').addEventListener('click', () => { theme = theme === 'light' ? 'dark' : 'light'; renderMode(); });
document.querySelectorAll('[data-period]').forEach(button => button.addEventListener('click', () => { period = button.dataset.period; renderChart(); }));
document.getElementById('search').addEventListener('input', renderRows);
document.querySelectorAll('[data-sort]').forEach(button => button.addEventListener('click', () => {
  ascending = sort === button.dataset.sort ? !ascending : true; sort = button.dataset.sort;
  document.querySelectorAll('[data-sort]').forEach(item => { item.parentElement.setAttribute('aria-sort', item === button ? (ascending ? 'ascending' : 'descending') : 'none'); item.querySelector('span').textContent = item === button ? (ascending ? '↑' : '↓') : '↕'; });
  renderRows();
}));
document.getElementById('export').addEventListener('click', () => {
  const csv = ['DEMONSTRATION — DONNEES FICTIVES', 'Societe;Quantite;Cours MAD;Valeur MAD', ...holdings.map(row => `${row.name};${row.qty};${row.price};${row.value}`)].join('\n');
  const url = URL.createObjectURL(new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8' }));
  const link = document.createElement('a'); link.href = url; link.download = 'portefeuille-fictif.csv'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  document.getElementById('announcement').textContent = 'Export des données fictives préparé.';
});
if (view === 'overview') sort = 'day';
renderRows(); renderChart(); renderMode();
