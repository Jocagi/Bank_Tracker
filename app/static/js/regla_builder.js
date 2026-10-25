/**
 * Constructor de reglas de clasificación de comercios.
 *
 * Permite definir, por comercio, una o varias reglas (incluir/excluir) cada
 * una compuesta por condiciones combinables con AND/OR y negables con NOT,
 * evaluando campos como descripción, lugar, fecha, monto, banco, tipo de
 * cuenta, etc. Al enviar el formulario, el estado se serializa como JSON en
 * el campo oculto #reglas-json para que el backend lo procese.
 */
(function (window, document) {
  'use strict';

  var CAMPOS = [
    { value: 'descripcion', label: 'Descripción', tipo: 'texto', placeholder: 'Ej. SUPERMERCADO LA TORRE' },
    { value: 'detalle', label: 'Detalle', tipo: 'texto', placeholder: 'Texto del detalle del movimiento' },
    { value: 'lugar', label: 'Lugar / Ubicación', tipo: 'texto', placeholder: 'Ej. GUATEMALA, ZONA 10' },
    { value: 'numero_documento', label: 'Número de documento', tipo: 'texto' },
    { value: 'moneda', label: 'Moneda', tipo: 'catalogo', catalogoKey: 'moneda', placeholder: 'GTQ, USD...' },
    { value: 'monto', label: 'Monto', tipo: 'numero', placeholder: '0.00' },
    { value: 'fecha', label: 'Fecha', tipo: 'fecha' },
    {
      value: 'tipo_movimiento', label: 'Tipo de movimiento', tipo: 'choice',
      opciones: [{ value: 'debito', label: 'Débito' }, { value: 'credito', label: 'Crédito' }]
    },
    { value: 'banco', label: 'Banco de la cuenta', tipo: 'catalogo', catalogoKey: 'banco', placeholder: 'Ej. BI, BAC, GyT...' },
    { value: 'tipo_cuenta', label: 'Tipo de cuenta', tipo: 'catalogo', catalogoKey: 'tipo_cuenta', placeholder: 'Ej. Monetaria, Ahorro, Tarjeta...' },
    { value: 'cuenta', label: 'Cuenta (alias o número)', tipo: 'catalogo', catalogoKey: 'cuenta' }
  ];

  // Catálogos cargados dinámicamente desde el backend (bancos, tipos de
  // cuenta, cuentas y monedas existentes), para ofrecerlos como lista
  // desplegable en lugar de pedir que se escriban a mano.
  var CATALOGOS = {};
  var VALOR_PERSONALIZADO = '__personalizado__';

  var OPERADORES = {
    texto: [
      { value: 'contiene', label: 'contiene' },
      { value: 'no_contiene', label: 'no contiene' },
      { value: 'igual', label: 'es exactamente' },
      { value: 'distinto', label: 'es distinto de' },
      { value: 'empieza_con', label: 'empieza con' },
      { value: 'termina_con', label: 'termina con' },
      { value: 'comodin', label: 'coincide con patrón (usa * como comodín)' },
      { value: 'regex', label: 'coincide con expresión regular' }
    ],
    numero: [
      { value: 'igual', label: 'es igual a' },
      { value: 'distinto', label: 'es distinto de' },
      { value: 'mayor_que', label: 'es mayor que' },
      { value: 'mayor_o_igual', label: 'es mayor o igual que' },
      { value: 'menor_que', label: 'es menor que' },
      { value: 'menor_o_igual', label: 'es menor o igual que' },
      { value: 'entre', label: 'está entre (rango)' }
    ],
    fecha: [
      { value: 'igual', label: 'es el' },
      { value: 'antes_de', label: 'es antes del' },
      { value: 'despues_de', label: 'es después del' },
      { value: 'entre', label: 'está entre (rango de fechas)' },
      { value: 'dia_semana', label: 'cae en el día de la semana' },
      { value: 'dia_mes', label: 'cae en el día del mes' },
      { value: 'mes', label: 'cae en el mes' }
    ],
    choice: [
      { value: 'igual', label: 'es' },
      { value: 'distinto', label: 'no es' }
    ]
  };

  var DIAS_SEMANA = [
    { value: 'lunes', label: 'Lunes' }, { value: 'martes', label: 'Martes' },
    { value: 'miercoles', label: 'Miércoles' }, { value: 'jueves', label: 'Jueves' },
    { value: 'viernes', label: 'Viernes' }, { value: 'sabado', label: 'Sábado' },
    { value: 'domingo', label: 'Domingo' }
  ];

  var MESES = [
    { value: '1', label: 'Enero' }, { value: '2', label: 'Febrero' }, { value: '3', label: 'Marzo' },
    { value: '4', label: 'Abril' }, { value: '5', label: 'Mayo' }, { value: '6', label: 'Junio' },
    { value: '7', label: 'Julio' }, { value: '8', label: 'Agosto' }, { value: '9', label: 'Septiembre' },
    { value: '10', label: 'Octubre' }, { value: '11', label: 'Noviembre' }, { value: '12', label: 'Diciembre' }
  ];

  function campoInfo(valor) {
    return CAMPOS.filter(function (c) { return c.value === valor; })[0] || CAMPOS[0];
  }

  function operadoresPara(campoTipo) {
    return OPERADORES[campoTipo] || OPERADORES.texto;
  }

  function buildOptions(select, opciones, selected) {
    select.innerHTML = '';
    opciones.forEach(function (op) {
      var option = document.createElement('option');
      option.value = op.value;
      option.textContent = op.label;
      if (op.value === selected) option.selected = true;
      select.appendChild(option);
    });
  }

  function necesitaRango(operador) {
    return operador === 'entre';
  }

  /** Opciones de catálogo disponibles para un campo (banco, tipo de cuenta, cuenta o moneda). */
  function catalogOptions(catalogoKey) {
    var valores = CATALOGOS[catalogoKey] || [];
    return valores.map(function (item) {
      return typeof item === 'string' ? { value: item, label: item } : item;
    });
  }

  /** Construye el <select> de un campo con catálogo, agregando una opción
   * para escribir un valor manual cuando no está en la lista. */
  function buildCatalogoSelect(campo, valorActual, inputBase, selectBase) {
    var opciones = catalogOptions(campo.catalogoKey);
    var yaIncluido = opciones.some(function (op) { return op.value === valorActual; });
    var listado = opciones.slice();
    if (valorActual && !yaIncluido) {
      listado = [{ value: valorActual, label: valorActual }].concat(listado);
    }
    listado.push({ value: VALOR_PERSONALIZADO, label: 'Otro valor (escribir manualmente)…' });

    var select = selectBase('valor-input', listado);
    if (valorActual) select.value = valorActual;

    select.addEventListener('change', function () {
      if (select.value !== VALOR_PERSONALIZADO) return;
      var texto = inputBase('valor-input', 'text', campo.placeholder || 'Valor');
      texto.setAttribute('aria-label', 'Valor');
      select.replaceWith(texto);
      texto.focus();
    });

    return select;
  }

  /** Reconstruye los inputs de valor/valor2 según el tipo de campo y operador actuales. */
  function renderValorInputs(row, valoresPrevios) {
    var campo = campoInfo(row.querySelector('.campo-select').value);
    var operador = row.querySelector('.operador-select').value;
    var valorCell = row.querySelector('.valor-cell');
    var valor2Cell = row.querySelector('.valor2-cell');
    valoresPrevios = valoresPrevios || {};

    function inputBase(cls, tipo, placeholder) {
      var input = document.createElement('input');
      input.type = tipo;
      input.className = 'form-control form-control-sm ' + cls;
      if (placeholder) input.placeholder = placeholder;
      return input;
    }

    function selectBase(cls, opciones) {
      var select = document.createElement('select');
      select.className = 'form-select form-select-sm ' + cls;
      buildOptions(select, opciones);
      return select;
    }

    var valorEl;
    if (campo.tipo === 'catalogo') {
      valorEl = buildCatalogoSelect(campo, valoresPrevios.valor || '', inputBase, selectBase);
    } else if (campo.tipo === 'choice') {
      valorEl = selectBase('valor-input', campo.opciones);
    } else if (campo.tipo === 'fecha' && operador === 'dia_semana') {
      valorEl = selectBase('valor-input', DIAS_SEMANA);
    } else if (campo.tipo === 'fecha' && operador === 'mes') {
      valorEl = selectBase('valor-input', MESES);
    } else if (campo.tipo === 'fecha' && operador === 'dia_mes') {
      valorEl = inputBase('valor-input', 'number', 'Día (1-31)');
      valorEl.min = 1; valorEl.max = 31;
    } else if (campo.tipo === 'fecha') {
      valorEl = inputBase('valor-input', 'date');
    } else if (campo.tipo === 'numero') {
      valorEl = inputBase('valor-input', 'number', campo.placeholder);
      valorEl.step = '0.01';
    } else {
      valorEl = inputBase('valor-input', 'text', campo.placeholder || 'Valor');
    }
    valorEl.setAttribute('aria-label', 'Valor');
    if (campo.tipo !== 'catalogo' && valoresPrevios.valor !== undefined && valoresPrevios.valor !== null) {
      valorEl.value = valoresPrevios.valor;
    }
    valorCell.innerHTML = '';
    valorCell.appendChild(valorEl);

    valor2Cell.innerHTML = '';
    valor2Cell.hidden = !necesitaRango(operador);
    if (necesitaRango(operador)) {
      var valor2El = campo.tipo === 'fecha' ? inputBase('valor2-input', 'date') : inputBase('valor2-input', 'number', 'y');
      if (campo.tipo === 'numero') valor2El.step = '0.01';
      valor2El.setAttribute('aria-label', 'Valor hasta');
      if (valoresPrevios.valor2 !== undefined && valoresPrevios.valor2 !== null) {
        valor2El.value = valoresPrevios.valor2;
      }
      valor2Cell.appendChild(valor2El);
    }
  }

  function onCampoChange(row) {
    var campo = campoInfo(row.querySelector('.campo-select').value);
    var operadorSelect = row.querySelector('.operador-select');
    // Los campos con catálogo (valores cerrados) usan "es exactamente" por
    // defecto: es más coherente que "contiene" y además permite comparar
    // por igualdad en vez de hacer búsquedas de subcadena.
    var operadorPorDefecto = campo.tipo === 'catalogo' ? 'igual' : undefined;
    buildOptions(operadorSelect, operadoresPara(campo.tipo), operadorPorDefecto);
    renderValorInputs(row);
  }

  function onOperadorChange(row) {
    renderValorInputs(row, {
      valor: row.querySelector('.valor-input') ? row.querySelector('.valor-input').value : '',
      valor2: row.querySelector('.valor2-input') ? row.querySelector('.valor2-input').value : ''
    });
  }

  function crearCondicionRow(data) {
    data = data || {};
    var row = document.createElement('div');
    row.className = 'condicion-row d-flex align-items-center gap-2 mb-2 flex-wrap';

    var conectorSelect = document.createElement('select');
    conectorSelect.className = 'form-select form-select-sm conector-select';
    conectorSelect.style.width = '72px';
    buildOptions(conectorSelect, [{ value: 'AND', label: 'Y' }, { value: 'OR', label: 'O' }], data.conector || 'AND');

    var campoSelect = document.createElement('select');
    campoSelect.className = 'form-select form-select-sm campo-select';
    campoSelect.style.width = '190px';
    buildOptions(campoSelect, CAMPOS, data.campo || 'descripcion');

    var operadorSelect = document.createElement('select');
    operadorSelect.className = 'form-select form-select-sm operador-select';
    operadorSelect.style.width = '230px';

    var valorCell = document.createElement('div');
    valorCell.className = 'valor-cell';
    valorCell.style.minWidth = '150px';
    var valor2Cell = document.createElement('div');
    valor2Cell.className = 'valor2-cell';
    valor2Cell.style.minWidth = '110px';

    // Casilla para invertir el resultado de la condición completa. Se coloca
    // al final, después del valor, para que se lea como un modificador sobre
    // toda la condición ya formada (p.ej. "Banco es exactamente BAC" + marcar
    // "Negar" = "que NO sea ese banco"), en vez de intercalarse entre el
    // campo y el operador, donde su alcance resulta ambiguo.
    var negarId = 'negar-' + Math.random().toString(36).slice(2);
    var negarWrap = document.createElement('div');
    negarWrap.className = 'form-check form-check-sm d-flex align-items-center gap-1 m-0';
    var negarCheck = document.createElement('input');
    negarCheck.type = 'checkbox';
    negarCheck.className = 'form-check-input negar-check';
    negarCheck.id = negarId;
    negarCheck.style.marginTop = '0';
    if (data.negar) negarCheck.checked = true;
    var negarLabel = document.createElement('label');
    negarLabel.className = 'form-check-label small text-muted negar-label';
    negarLabel.setAttribute('for', negarId);
    negarLabel.title = 'Si se marca, la regla se cumple cuando esta condición NO ocurre (se invierte el resultado).';
    negarLabel.textContent = 'Negar';
    negarWrap.appendChild(negarCheck);
    negarWrap.appendChild(negarLabel);

    var removeBtn = document.createElement('button');
    removeBtn.type = 'button';
    removeBtn.className = 'btn-close remove-condicion align-self-center';
    removeBtn.setAttribute('aria-label', 'Eliminar condición');
    removeBtn.title = 'Eliminar condición';

    row.appendChild(conectorSelect);
    row.appendChild(campoSelect);
    row.appendChild(operadorSelect);
    row.appendChild(valorCell);
    row.appendChild(valor2Cell);
    row.appendChild(negarWrap);
    row.appendChild(removeBtn);

    var campoInicial = campoInfo(data.campo || 'descripcion');
    var operadorInicial = data.operador || (campoInicial.tipo === 'catalogo' ? 'igual' : 'contiene');
    buildOptions(operadorSelect, operadoresPara(campoInicial.tipo), operadorInicial);
    renderValorInputs(row, { valor: data.valor, valor2: data.valor2 });

    campoSelect.addEventListener('change', function () { onCampoChange(row); });
    operadorSelect.addEventListener('change', function () { onOperadorChange(row); });
    removeBtn.addEventListener('click', function () {
      var container = row.parentElement;
      row.remove();
      actualizarConectoresVisibles(container);
    });

    return row;
  }

  function actualizarConectoresVisibles(condicionesContainer) {
    var filas = condicionesContainer.querySelectorAll('.condicion-row');
    filas.forEach(function (fila, idx) {
      var conector = fila.querySelector('.conector-select');
      conector.hidden = idx === 0;
      conector.style.visibility = idx === 0 ? 'hidden' : 'visible';
    });
  }

  function agregarCondicion(condicionesContainer, data) {
    var row = crearCondicionRow(data);
    condicionesContainer.appendChild(row);
    actualizarConectoresVisibles(condicionesContainer);
    return row;
  }

  function crearReglaCard(reglaData) {
    reglaData = reglaData || {};
    var card = document.createElement('div');
    card.className = 'card regla-card mb-3';

    var header = document.createElement('div');
    header.className = 'card-header d-flex flex-wrap align-items-center gap-2 bg-light';

    var tipoSelect = document.createElement('select');
    tipoSelect.className = 'form-select form-select-sm regla-tipo';
    tipoSelect.style.width = 'auto';
    buildOptions(tipoSelect, [
      { value: 'incluir', label: 'Incluir (asigna el comercio)' },
      { value: 'excluir', label: 'Excluir (evita asignar el comercio)' }
    ], reglaData.tipo || 'incluir');

    var removeReglaBtn = document.createElement('button');
    removeReglaBtn.type = 'button';
    removeReglaBtn.className = 'btn btn-sm btn-outline-danger remove-regla ms-auto';
    removeReglaBtn.title = 'Eliminar regla';
    removeReglaBtn.textContent = 'Eliminar regla';

    header.appendChild(tipoSelect);
    header.appendChild(removeReglaBtn);

    var body = document.createElement('div');
    body.className = 'card-body';

    var condicionesContainer = document.createElement('div');
    condicionesContainer.className = 'condiciones-container';

    var addCondicionBtn = document.createElement('button');
    addCondicionBtn.type = 'button';
    addCondicionBtn.className = 'btn btn-sm btn-outline-secondary add-condicion mt-1';
    addCondicionBtn.textContent = '+ Agregar condición';

    var help = document.createElement('div');
    help.className = 'form-text';
    help.textContent = 'Las condiciones se evalúan en el orden mostrado, combinándose con el conector (Y/O) a la izquierda. Marca "Negar" al final de una condición para invertir su resultado.';

    body.appendChild(condicionesContainer);
    body.appendChild(addCondicionBtn);
    body.appendChild(help);

    card.appendChild(header);
    card.appendChild(body);

    var condicionesData = (reglaData.condiciones && reglaData.condiciones.length)
      ? reglaData.condiciones
      : [{ campo: 'descripcion', operador: 'contiene' }];
    condicionesData.forEach(function (c) { agregarCondicion(condicionesContainer, c); });

    addCondicionBtn.addEventListener('click', function () {
      agregarCondicion(condicionesContainer, { campo: 'descripcion', operador: 'contiene' });
    });
    removeReglaBtn.addEventListener('click', function () { card.remove(); });

    return card;
  }

  /** Etiqueta del operador seleccionado, para armar el resumen legible de una condición. */
  function etiquetaOperador(campoTipo, operadorValue) {
    var match = operadoresPara(campoTipo).filter(function (o) { return o.value === operadorValue; })[0];
    return match ? match.label : operadorValue;
  }

  /** Texto legible de una condición, p.ej. 'banco no es exactamente "BAC"'. */
  function describirCondicionTexto(cond) {
    var campo = campoInfo(cond.campo);
    var operadorLabel = etiquetaOperador(campo.tipo, cond.operador);
    var prefijo = cond.negar ? 'no ' : '';
    var detalle = '';
    if (cond.operador === 'entre') {
      detalle = cond.valor ? '"' + cond.valor + '" y "' + (cond.valor2 || '') + '"' : '';
    } else if (cond.valor) {
      detalle = '"' + cond.valor + '"';
    }
    return (campo.label.toLowerCase() + ' ' + prefijo + operadorLabel + (detalle ? ' ' + detalle : '')).trim();
  }

  /**
   * Genera automáticamente el nombre/identificador de la regla a partir de
   * sus condiciones: el usuario no necesita escribirlo, ya que no aporta
   * información que no esté ya determinada por las condiciones mismas.
   */
  function generarDescripcionRegla(condiciones) {
    if (!condiciones.length) return 'Regla sin condiciones';
    var partes = condiciones.map(function (cond, idx) {
      var texto = describirCondicionTexto(cond);
      if (idx === 0) return texto;
      var conector = (cond.conector || 'AND').toUpperCase() === 'OR' ? 'o' : 'y';
      return conector + ' ' + texto;
    });
    var resultado = partes.join(' ');
    resultado = resultado.charAt(0).toUpperCase() + resultado.slice(1);
    return resultado.length > 195 ? resultado.slice(0, 192) + '…' : resultado;
  }

  function init(options) {
    CATALOGOS = options.catalogos || {};
    var container = document.getElementById(options.containerId || 'reglas-container');
    var addBtn = document.getElementById(options.addButtonId || 'add-regla-btn');
    var form = options.form || container.closest('form');
    var hiddenInput = document.getElementById(options.hiddenInputId || 'reglas-json');

    (options.reglasIniciales || []).forEach(function (reglaData) {
      container.appendChild(crearReglaCard(reglaData));
    });

    if (options.reglaPrellenada) {
      container.appendChild(crearReglaCard(options.reglaPrellenada));
    }

    addBtn.addEventListener('click', function () {
      container.appendChild(crearReglaCard());
    });

    function serializar() {
      var reglas = [];
      container.querySelectorAll('.regla-card').forEach(function (card) {
        var tipo = card.querySelector('.regla-tipo').value;
        var condiciones = [];
        card.querySelectorAll('.condicion-row').forEach(function (row, idx) {
          var valorInput = row.querySelector('.valor-input');
          var valor2Input = row.querySelector('.valor2-input');
          var valor = valorInput ? valorInput.value.trim() : '';
          if (valor === VALOR_PERSONALIZADO) valor = '';
          condiciones.push({
            orden: idx,
            conector: row.querySelector('.conector-select').value,
            negar: row.querySelector('.negar-check').checked,
            campo: row.querySelector('.campo-select').value,
            operador: row.querySelector('.operador-select').value,
            valor: valor,
            valor2: valor2Input ? valor2Input.value.trim() : null
          });
        });
        // El nombre de la regla se infiere de sus condiciones: no depende de
        // una entrada manual del usuario.
        var descripcion = generarDescripcionRegla(condiciones);
        reglas.push({ descripcion: descripcion, tipo: tipo, condiciones: condiciones });
      });
      return reglas;
    }

    function validar(reglas) {
      for (var i = 0; i < reglas.length; i++) {
        var regla = reglas[i];
        if (!regla.condiciones.length) {
          return 'Agrega al menos una condición a cada regla antes de guardar.';
        }
        for (var j = 0; j < regla.condiciones.length; j++) {
          var cond = regla.condiciones[j];
          if (!cond.valor) {
            return 'Completa el valor de todas las condiciones de la regla "' + regla.descripcion + '".';
          }
          if (cond.operador === 'entre' && !cond.valor2) {
            return 'La condición de rango en "' + regla.descripcion + '" necesita un valor final.';
          }
        }
      }
      return null;
    }

    form.addEventListener('submit', function (event) {
      var reglas = serializar();
      var error = validar(reglas);
      if (error) {
        event.preventDefault();
        if (typeof window.alert === 'function') window.alert(error);
        return false;
      }
      hiddenInput.value = JSON.stringify(reglas);
    });
  }

  window.ReglaBuilder = { init: init };
})(window, document);
