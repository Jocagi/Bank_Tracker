"""Download the first Brave Images result as each country's flag.

Run from the repository root:
    python scripts/asignar_banderas_google.py --dry-run
    python scripts/asignar_banderas_google.py

Countries that already have a flag are skipped unless --force is supplied.
Google may rate-limit automated requests; use --delay between requests.
"""

import argparse
import html
import mimetypes
import os
import re
import sys
import time
import uuid
from urllib.parse import urlparse
from urllib.request import Request, urlopen

# Allow running this file directly from the repository root.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app import create_app, db
from app.models import Pais
from app.utils.image_search import search_brave_images


ALLOWED_TYPES = {
    'image/jpeg': 'jpg',
    'image/png': 'png',
    'image/gif': 'gif',
    'image/webp': 'webp',
}
MAX_BYTES = 5 * 1024 * 1024
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36'


def brave_first_image_url(country):
    query = f'flag of {country.nombre} {country.codigo_iso}'
    suggestions = search_brave_images(query)
    if suggestions:
        return suggestions[0].get('url')
    return None


def download_image(url):
    request = Request(url, headers={'User-Agent': USER_AGENT, 'Accept': 'image/avif,image/webp,image/apng,image/*,*/*;q=0.8'})
    with urlopen(request, timeout=20) as response:
        content_type = response.headers.get_content_type().lower()
        content = response.read(MAX_BYTES + 1)

    if len(content) > MAX_BYTES:
        raise ValueError('la imagen excede 5 MB')

    # Some hosts send application/octet-stream; identify common formats by signature.
    if content.startswith(b'\xff\xd8\xff'):
        extension = 'jpg'
    elif content.startswith(b'\x89PNG\r\n\x1a\n'):
        extension = 'png'
    elif content.startswith((b'GIF87a', b'GIF89a')):
        extension = 'gif'
    elif content[:4] == b'RIFF' and content[8:12] == b'WEBP':
        extension = 'webp'
    else:
        extension = ALLOWED_TYPES.get(content_type)

    if not extension:
        guessed_type = mimetypes.guess_type(urlparse(url).path)[0]
        extension = ALLOWED_TYPES.get(guessed_type)
    if not extension:
        raise ValueError(f'contenido no reconocido como imagen ({content_type})')
    return content, extension


def save_flag(app, country, content, extension):
    folder = os.path.join(app.config['UPLOAD_FOLDER'], 'paises')
    os.makedirs(folder, exist_ok=True)
    filename = f'{uuid.uuid4().hex}.{extension}'
    path = os.path.join(folder, filename)
    with open(path, 'wb') as output:
        output.write(content)
    country.logo_filename = f'paises/{filename}'


def main():
    parser = argparse.ArgumentParser(description='Asigna la primera imagen de Brave a los países.')
    parser.add_argument('--force', action='store_true', help='Reemplaza banderas existentes.')
    parser.add_argument('--dry-run', action='store_true', help='Consulta y muestra resultados sin guardar archivos ni cambios.')
    parser.add_argument('--delay', type=float, default=1.5, help='Segundos entre países (por defecto: 1.5).')
    parser.add_argument('--limit', type=int, default=0, help='Máximo de países a procesar; 0 significa todos.')
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        countries = Pais.query.order_by(Pais.nombre).all()
        if not args.force:
            countries = [country for country in countries if not country.logo_filename]
        if args.limit:
            countries = countries[:args.limit]

        if not countries:
            print('No hay países pendientes de bandera.')
            return 0

        successes = 0
        errors = 0
        for index, country in enumerate(countries, start=1):
            label = f'[{index}/{len(countries)}] {country.nombre} ({country.codigo_iso})'
            try:
                image_url = brave_first_image_url(country)
                if not image_url:
                    raise ValueError('Brave no devolvió una imagen externa')
                if args.dry_run:
                    print(f'{label}: {image_url}')
                else:
                    content, extension = download_image(image_url)
                    save_flag(app, country, content, extension)
                    db.session.commit()
                    print(f'{label}: OK')
                successes += 1
            except Exception as error:
                db.session.rollback()
                errors += 1
                print(f'{label}: ERROR: {error}')
            if index < len(countries):
                time.sleep(max(0, args.delay))

        print(f'Proceso terminado: {successes} correctos, {errors} errores.')
        return 1 if errors and not successes else 0


if __name__ == '__main__':
    raise SystemExit(main())
