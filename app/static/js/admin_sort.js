/**
 * admin_sort.js — SortableJS drag-and-drop for experience list
 * Posts [{id, order}] array to /admin/experiences/reorder on drag end.
 */
(function () {
  const list = document.getElementById('experienceList');
  if (!list) return;

  // Get CSRF token from a hidden input in the page
  function getCsrfToken() {
    const el = document.querySelector('input[name="csrf_token"]');
    return el ? el.value : '';
  }

  Sortable.create(list, {
    animation: 150,
    ghostClass: 'sortable-ghost',
    handle: 'td:first-child',
    onEnd: function () {
      const rows  = list.querySelectorAll('tr[data-id]');
      const order = Array.from(rows).map((row, idx) => ({
        id:    row.dataset.id,
        order: idx + 1,
      }));

      fetch('/admin/experiences/reorder', {
        method:  'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken':  getCsrfToken(),
        },
        body: JSON.stringify(order),
      })
      .then(r => r.json())
      .then(data => {
        if (data.status !== 'ok') {
          console.warn('Reorder save failed:', data);
        }
      })
      .catch(err => console.error('Reorder request failed:', err));
    },
  });
})();
