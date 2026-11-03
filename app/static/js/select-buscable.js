(function () {
  function placeholderDe(select) {
    var vacio = select.querySelector('option[value=""]');
    return vacio ? vacio.textContent.trim() : 'Buscar...';
  }

  function initSelectBuscable(root) {
    $(root || document).find('select.select-buscable').each(function () {
      if ($(this).data('select2')) return;
      $(this).select2({
        placeholder: placeholderDe(this),
        allowClear: true,
        minimumResultsForSearch: 0,
        width: '100%'
      });
      // El select nativo queda oculto, así que el navegador no puede enfocarlo
      // al validar "required". Se enfoca el buscador visible en su lugar.
      $(this).on('invalid', function () {
        $(this).next('.select2-container').find('.select2-selection').trigger('focus');
      });
    });
  }

  // Las opciones se reconstruyen desde una copia en lugar de ocultarlas con
  // display:none, porque Select2 no respeta esa propiedad.
  function vincularSubcategorias(categoriaSelect, subcategoriaSelect) {
    if (!categoriaSelect || !subcategoriaSelect) return;
    var todas = Array.from(subcategoriaSelect.options).map(function (opt) {
      return opt.cloneNode(true);
    });

    function actualizar() {
      var catId = categoriaSelect.value;
      var valorActual = subcategoriaSelect.value;
      subcategoriaSelect.innerHTML = '';
      todas.forEach(function (opt) {
        var generica = opt.value === '' || opt.value === '0';
        if (generica || catId === '' || opt.getAttribute('data-categoria-id') === catId) {
          subcategoriaSelect.appendChild(opt.cloneNode(true));
        }
      });
      var sigue = Array.from(subcategoriaSelect.options).some(function (opt) {
        return opt.value === valorActual;
      });
      subcategoriaSelect.value = sigue ? valorActual : '';
      $(subcategoriaSelect).trigger('change.select2');
    }

    $(categoriaSelect).on('change', actualizar);
    actualizar();
  }

  window.initSelectBuscable = initSelectBuscable;
  window.vincularSubcategorias = vincularSubcategorias;

  $(function () {
    initSelectBuscable(document);
  });
})();
