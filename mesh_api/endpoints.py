"""МЭШ API endpoints — URL-адреса управляются библиотекой OctoDiary.

OctoDiary использует собственные URL через octodiary.urls.BaseURL.
Этот модуль сохраняет общие константы для хедеров.
"""

# Заголовки по умолчанию для запросов (используются OctoDiary внутри)
DEFAULT_HEADERS = {
    "x-mes-subsystem": "familymp",
    "client-type": "diary-mobile",
    "Accept": "application/json",
}
