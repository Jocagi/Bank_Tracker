// El CDN de miniaturas de Brave aplica límites de tasa agresivos; si la
// primera carga falla se reintenta una vez tras una breve espera y, si
// sigue fallando, se reemplaza el ícono roto por un aviso neutral.
window.handleLogoThumbnailError = function(img) {
  const retryCount = parseInt(img.dataset.retryCount || '0', 10);
  const baseSrc = img.dataset.retrySrc || img.src;
  if (retryCount < 1) {
    img.dataset.retryCount = String(retryCount + 1);
    setTimeout(() => {
      const separator = baseSrc.includes('?') ? '&' : '?';
      img.src = `${baseSrc}${separator}retry=${Date.now()}`;
    }, 4000);
    return;
  }
  const placeholder = document.createElement('div');
  placeholder.className = 'text-muted small d-flex align-items-center justify-content-center bg-light border rounded';
  placeholder.style.cssText = `${img.style.cssText};min-height:60px`;
  placeholder.textContent = 'Vista previa no disponible';
  img.replaceWith(placeholder);
};

window.initEntityLogoForm = function(nameInputId, suggestionsUrl, searchTerm = 'logo', imageProxyUrl = null) {
  const nameInput = document.getElementById(nameInputId);
  const logoInput = document.getElementById('entity-logo-input');
  const logoUrl = document.getElementById('entity-logo-url');
  const logoThumbnailUrl = document.getElementById('entity-logo-thumbnail-url');
  const dropzone = document.getElementById('entity-logo-dropzone');
  const preview = document.getElementById('entity-logo-preview');
  const suggestions = document.getElementById('entity-logo-suggestions');
  const searchLink = document.getElementById('entity-image-search-link');
  const searchButton = document.getElementById('buscar-entity-logos');

  if (!nameInput || !logoInput || !dropzone || !preview || !suggestions) return;

  // Las miniaturas de Brave se sirven desde nuestro propio servidor para
  // evitar fallos intermitentes al cargarlas directamente desde el navegador.
  function proxiedThumbnail(thumbnailUrl) {
    if (!thumbnailUrl) return thumbnailUrl;
    return imageProxyUrl ? `${imageProxyUrl}?url=${encodeURIComponent(thumbnailUrl)}` : thumbnailUrl;
  }

  function previewLogo(source, alt) {
    preview.innerHTML = `<img src="${source}" data-retry-src="${source}" onerror="window.handleLogoThumbnailError(this)" alt="${alt}" class="img-thumbnail" style="width:96px;height:96px;object-fit:contain">`;
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
      const response = await fetch(`${suggestionsUrl}?nombre=${encodeURIComponent(name)}&termino=${encodeURIComponent(searchTerm)}`);
      const data = await response.json();
      searchLink.href = data.search_url || '#';
      searchLink.hidden = !data.search_url;
      suggestions.innerHTML = '';
      data.suggestions.forEach((suggestion, index) => {
        const column = document.createElement('div');
        column.className = 'col-4';
        const thumbSrc = proxiedThumbnail(suggestion.thumbnail_url) || suggestion.url;
        column.innerHTML = `<button type="button" class="btn btn-light border w-100 p-1" title="Usar esta imagen"><img src="${thumbSrc}" data-retry-src="${thumbSrc}" onerror="window.handleLogoThumbnailError(this)" alt="${suggestion.title || `Sugerencia ${index + 1}`}" style="width:100%;height:90px;object-fit:contain"></button>`;
        column.querySelector('button').addEventListener('click', () => {
          logoUrl.value = suggestion.url;
          if (logoThumbnailUrl) logoThumbnailUrl.value = suggestion.thumbnail_url || '';
          logoInput.value = '';
          previewLogo(thumbSrc, 'Logo seleccionado');
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
