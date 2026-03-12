// Table Sorting Functionality
document.addEventListener('DOMContentLoaded', function () {
  // State for sorting
  const sortState = {};

  // Setup headers for all sortable tables
  document.querySelectorAll('th[data-column]').forEach(function (th) {
    th.style.cursor = 'pointer';
    th.style.userSelect = 'none';
    th.addEventListener('click', handleColumnSort);
  });

  function handleColumnSort(event) {
    const th = event.currentTarget;
    const column = th.getAttribute('data-column');
    const table = th.closest('table');
    const tableId = table.id || 'default-table-' + Math.random().toString(36).substr(2, 9);

    if (!table.id) table.id = tableId;

    // Initialize sort state for this table
    if (!sortState[tableId]) {
      sortState[tableId] = {};
    }

    // Toggle sort order
    if (sortState[tableId].column === column) {
      sortState[tableId].order = sortState[tableId].order === 'asc' ? 'desc' : 'asc';
    } else {
      sortState[tableId].column = column;
      sortState[tableId].order = 'asc';
    }

    // Clear indicators
    th.closest('thead').querySelectorAll('.sort-indicator').forEach(function (span) {
      span.textContent = '';
    });

    // Add indicator to current column
    const indicator = th.querySelector('.sort-indicator');
    if (indicator) {
      indicator.textContent = sortState[tableId].order === 'asc' ? ' ▲' : ' ▼';
    }

    // Sort table
    sortTable(table, column, sortState[tableId].order);
  }

  function sortTable(table, column, order) {
    const tbody = table.querySelector('tbody');
    const rows = Array.from(tbody.querySelectorAll('tr'));

    rows.sort(function (a, b) {
      const aValue = a.getAttribute('data-' + column);
      const bValue = b.getAttribute('data-' + column);

      if (!aValue || !bValue) return 0;

      // Try to parse as date
      const aDate = parseDate(aValue);
      const bDate = parseDate(bValue);

      if (aDate && bDate) {
        const comparison = aDate.getTime() - bDate.getTime();
        return order === 'asc' ? comparison : -comparison;
      }

      // Try to parse as number (strict full-string match)
      const aNum = parseNumber(aValue);
      const bNum = parseNumber(bValue);

      if (aNum !== null && bNum !== null) {
        return order === 'asc' ? aNum - bNum : bNum - aNum;
      }

      // String comparison
      const aStr = aValue.toLowerCase();
      const bStr = bValue.toLowerCase();

      if (order === 'asc') {
        return aStr.localeCompare(bStr);
      } else {
        return bStr.localeCompare(aStr);
      }
    });

    // Re-insert sorted rows
    rows.forEach(function (row) {
      tbody.appendChild(row);
    });
  }

  function parseDate(dateString) {
    if (!dateString) return null;

    // YYYY-MM-DD format
    if (/^\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?$/.test(dateString)) {
      const isoLike = dateString.includes(' ') ? dateString.replace(' ', 'T') : dateString;
      const date = new Date(isoLike);
      if (!isNaN(date.getTime())) {
        return date;
      }
    }

    // MM/DD/YYYY format
    const match = dateString.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})/);
    if (match) {
      const [, month, day, year] = match;
      const date = new Date(parseInt(year), parseInt(month) - 1, parseInt(day));
      if (!isNaN(date.getTime())) {
        return date;
      }
    }

    // DD-MM-YYYY format
    const match2 = dateString.match(/^(\d{1,2})-(\d{1,2})-(\d{4})/);
    if (match2) {
      const [, day, month, year] = match2;
      const date = new Date(parseInt(year), parseInt(month) - 1, parseInt(day));
      if (!isNaN(date.getTime())) {
        return date;
      }
    }

    return null;
  }

  function parseNumber(value) {
    if (!value) return null;
    const normalized = value.replace(/[$Q,\s]/g, '');
    if (!/^-?\d+(?:\.\d+)?$/.test(normalized)) {
      return null;
    }
    const parsed = Number(normalized);
    return Number.isNaN(parsed) ? null : parsed;
  }
});
