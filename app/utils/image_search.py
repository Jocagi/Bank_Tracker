"""Shared image search helpers."""

import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from flask import current_app


BRAVE_IMAGE_COUNTRIES = {
    'AR', 'AU', 'AT', 'BE', 'BR', 'CA', 'CL', 'DK', 'FI', 'FR', 'DE',
    'GR', 'HK', 'IN', 'ID', 'IT', 'JP', 'KR', 'MY', 'MX', 'NL', 'NZ',
    'NO', 'CN', 'PL', 'PT', 'PH', 'RU', 'SA', 'ZA', 'ES', 'SE', 'CH',
    'TW', 'TR', 'GB', 'US', 'ALL',
}
IMAGE_SEARCH_TERMS = {'logo', 'bandera', 'flag'}


def search_brave_images(query):
    """Return up to three validated image suggestions from Brave Images."""
    api_key = current_app.config.get('BRAVE_SEARCH_API_KEY', '')
    if not api_key:
        raise RuntimeError('BRAVE_SEARCH_API_KEY no está configurada.')

    country = current_app.config.get('BRAVE_SEARCH_COUNTRY', 'ALL')
    if country not in BRAVE_IMAGE_COUNTRIES:
        country = 'ALL'

    api_url = 'https://api.search.brave.com/res/v1/images/search?' + urlencode({
        'q': query,
        'count': 3,
        'safesearch': 'strict',
        'country': country,
        'search_lang': current_app.config.get('BRAVE_SEARCH_LANG', 'es'),
    })
    req = Request(api_url, headers={
        'Accept': 'application/json',
        'X-Subscription-Token': api_key,
        'User-Agent': 'BankTracker/1.0 (logo suggestions)',
    })
    payload = json.loads(urlopen(req, timeout=10).read().decode('utf-8'))
    if payload.get('error'):
        raise RuntimeError(payload['error'])

    return [
        {
            'url': item.get('properties', {}).get('url') or item.get('url'),
            'thumbnail_url': item.get('thumbnail', {}).get('src'),
            'title': item.get('title') or 'Logo sugerido',
        }
        for item in payload.get('results', [])
        if (item.get('properties', {}).get('url') or item.get('url', '')).startswith(('http://', 'https://'))
        and item.get('thumbnail', {}).get('src', '').startswith(('http://', 'https://'))
    ][:3]


def build_image_search_url(name, term='logo'):
    """Build the browser-search URL used as a fallback for suggestions."""
    name = (name or '').strip()
    term = (term or 'logo').strip().lower()
    if term not in IMAGE_SEARCH_TERMS:
        term = 'logo'
    query = f'{name} {term}'
    return 'https://www.google.com/search?' + urlencode({
        'tbm': 'isch',
        'q': query,
        'gl': current_app.config.get('BRAVE_SEARCH_COUNTRY', 'GT').lower(),
        'hl': current_app.config.get('BRAVE_SEARCH_LANG', 'es'),
    })


def search_image_suggestions(name, term='logo'):
    """Build a reusable image-suggestion response for an entity name."""
    name = (name or '').strip()
    if not name:
        return {'suggestions': []}

    term = (term or 'logo').strip().lower()
    if term not in IMAGE_SEARCH_TERMS:
        term = 'logo'
    query = f'{name} {term}'

    return {
        'suggestions': search_brave_images(query),
        'search_url': build_image_search_url(name, term),
    }
