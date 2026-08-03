window.initEntityLogoForm = function(nameInputId, suggestionsUrl) {
  const nameInput = document.getElementById(nameInputId);
  const logoInput = document.getElementById('entity-logo-input');
  const logoUrl = document.getElementById('entity-logo-url');
  const dropzone = document.getElementById('entity-logo-dropzone');
  const preview = document.getElementById('entity-logo-preview');
  const suggestions = document.getElementById('entity-logo-suggestions');
  const searchLink = document.getElementById('entity-image-search-link');
  const searchButton = document.getElementById('buscar-entity-logos');

  if (!nameInput || !logoInput || !dropzone || !preview || !suggestions) return;

  function previewLogo(source, alt) {
    preview.innerHTML = `<img src="${source}" alt="${alt}" class="img-thumbnail" style="width:96px;height:96px;object-fit:contain">`;
  }

  function showLocalLogo() {
    const file = logoInput.files[0];
    if (file) previewLogo(URL.createObjectURL(file), 'Vista previa del logo');
  }

  async function searchLogos() {
    const name = nameInput.value.trim();
    if (!name) return;
    suggestions.innerHTML = '<div class="text-muted small">Buscando imágenes...</div>';
    try {
      const response = await fetch(`${suggestionsUrl}?nombre=${encodeURIComponent(name)}`);
      const data = await response.json();
      searchLink.href = data.search_url || '#';
      searchLink.hidden = !data.search_url;
      suggestions.innerHTML = '';
      data.suggestions.forEach((suggestion, index) => {
        const column = document.createElement('div');
        column.className = 'col-4';
        column.innerHTML = `<button type="button" class="btn btn-light border w-100 p-1" title="Usar esta imagen"><img src="${suggestion.thumbnail_url || suggestion.url}" alt="${suggestion.title || `Sugerencia ${index + 1}`}" style="width:100%;height:90px;object-fit:contain"></button>`;
        column.querySelector('button').addEventListener('click', () => {
          logoUrl.value = suggestion.url;
          logoInput.value = '';
          previewLogo(suggestion.url, 'Logo seleccionado');
        });
        suggestions.appendChild(column);
      });
      if (!data.suggestions.length) suggestions.innerHTML = `<div class="text-muted small">${data.message || 'No se encontraron imágenes.'} Usa una imagen local o el enlace de resultados.</div>`;
    } catch (error) {
      suggestions.innerHTML = '<div class="text-muted small">No fue posible buscar sugerencias.</div>';
    }
  }

  logoInput.addEventListener('change', showLocalLogo);
  ['dragenter', 'dragover'].forEach(eventName => dropzone.addEventListener(eventName, event => {
    event.preventDefault();
    dropzone.classList.add('border-primary');
  }));
  ['dragleave', 'drop'].forEach(eventName => dropzone.addEventListener(eventName, event => {
    event.preventDefault();
    dropzone.classList.remove('border-primary');
  }));
  dropzone.addEventListener('drop', event => {
    if (!event.dataTransfer.files.length) return;
    logoInput.files = event.dataTransfer.files;
    showLocalLogo();
  });
  searchButton.addEventListener('click', searchLogos);
  nameInput.addEventListener('change', searchLogos);
};
