/* Display-only ordering; financial records, charts and valuations are untouched. */
(() => {
  const table = document.getElementById('holdingsTbl');
  if (!table || !table.tBodies.length || !table.tHead) return;
  const body = table.tBodies[0];
  const rows = Array.from(body.rows, (row, index) => ({
    row, index, values: JSON.parse(row.dataset.sortValues),
  }));
  const headers = Array.from(table.tHead.rows[0].cells);
  const collator = new Intl.Collator(document.documentElement.lang || undefined, {
    sensitivity: 'base', numeric: true,
  });
  let active = -1;
  let ascending = true;
  const ascendingLabel = table.dataset.sortAscending || 'Sort ascending';
  const descendingLabel = table.dataset.sortDescending || 'Sort descending';
  headers.forEach((header, column) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'table-sort';
    const label = header.textContent.trim();
    while (header.firstChild) button.append(header.firstChild);
    const arrow = document.createElement('span');
    arrow.className = 'table-sort__arrow';
    arrow.setAttribute('aria-hidden', 'true');
    arrow.textContent = '↕';
    button.append(arrow);
    header.append(button);
    header.setAttribute('aria-sort', 'none');
    button.setAttribute('aria-label', `${label}: ${ascendingLabel}`);
    button.addEventListener('click', () => {
      ascending = active === column ? !ascending : true;
      active = column;
      const ordered = rows.slice().sort((a, b) => {
        const left = a.values[column];
        const right = b.values[column];
        // Unavailable values remain last in either direction; they are never zero.
        if (left === null || right === null) {
          return left === right ? a.index - b.index : left === null ? 1 : -1;
        }
        const order = column === 0 ? collator.compare(left, right) : left - right;
        return (ascending ? order : -order) || a.index - b.index;
      });
      const fragment = document.createDocumentFragment();
      ordered.forEach(({row}) => fragment.append(row));
      body.append(fragment);
      headers.forEach((item, index) => {
        const selected = index === column;
        item.setAttribute('aria-sort', selected ? (ascending ? 'ascending' : 'descending') : 'none');
        item.querySelector('.table-sort__arrow').textContent = selected ? (ascending ? '↑' : '↓') : '↕';
        const name = item.textContent.replace(/[↕↑↓]/g, '').trim();
        item.querySelector('button').setAttribute('aria-label', `${name}: ${selected && ascending ? descendingLabel : ascendingLabel}`);
      });
    });
  });
})();
