"""Avisos de operaciones confirmadas, acotados y asociados a su redirección."""

from collections import OrderedDict
from contextvars import ContextVar
from secrets import token_urlsafe
from threading import RLock
from time import monotonic
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


CURRENT_NOTICE = ContextVar('operation_notice', default=None)
MESSAGES = {
    'batch_opened': 'Serie {series} · Tanda {batch} asignada a {author}.',
    'batch_closed': 'Tanda {batch} de {author} cerrada con éxito.',
    'order_created': 'La orden {number} de {author} ha sido exitosamente guardada!',
    'order_updated': 'Orden {number} ha sido modificada con éxito!',
    'order_deleted': 'La orden {number} de {author} ha sido eliminada!',
    'article_created': 'Artículo agregado al inventario.',
    'article_updated': '{article} ha sido modificado con éxito!',
    'article_deleted': 'Artículo eliminado del inventario.',
    'journey_created': 'Jornada iniciada.',
    'journey_updated': 'Nombre de la jornada actualizado.',
    'journey_closed': 'Jornada cerrada. Los archivos están disponibles para descargar.',
    'journey_recovered': 'Jornada {journey} ha sido recuperada exitosamente!',
    'journey_discarded': 'Jornada descartada.',
    'author_created': '{author} ha sido agregado a la jornada {journey}.',
    'author_updated': 'Nombre del autor actualizado.',
    'author_deleted': 'Autor eliminado.',
}


def order_details(order, journey):
    number = (f"{order['serial_number']:03d}" if order.get('serial_number') is not None
              else str(order['number']))
    author = next((item['name'] for item in journey['authors'] if item['id'] == order['author_id']),
                  'autor no disponible')
    return dict(number=number, author=author)


class OperationNotices:
    lifetime = 300
    max_entries = 256

    def __init__(self):
        self.lock = RLock()
        self.entries = OrderedDict()

    def _expire(self):
        for token, entry in list(self.entries.items()):
            if monotonic() - entry['created'] >= self.lifetime:
                del self.entries[token]

    def url(self, target, code, **details):
        if code not in MESSAGES:
            raise ValueError('Aviso desconocido.')
        message = MESSAGES[code].format(**details)
        parts = urlsplit(target)
        with self.lock:
            self._expire()
            while len(self.entries) >= self.max_entries:
                self.entries.popitem(last=False)
            token = token_urlsafe(24)
            self.entries[token] = dict(created=monotonic(), path=parts.path, code=code, message=message)
        query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
                 if key != 'notice']
        query.append(('notice', token))
        return urlunsplit(('', '', parts.path, urlencode(query), 'operation-notice'))

    def get(self, token, path):
        with self.lock:
            self._expire()
            entry = self.entries.get(token)
            if not entry or entry['path'] != path:
                return None
            return entry['message']


class NoticeContext:
    def __init__(self, app, notices):
        self.app = app
        self.notices = notices

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        notice = None
        raw_query = scope.get('query_string', b'')
        if scope['method'] == 'GET' and b'notice=' in raw_query:
            query = parse_qsl(raw_query.decode('utf-8', errors='replace'), keep_blank_values=True)
            token = next((value for key, value in query if key == 'notice'), '')
            saved = self.notices.get(token, scope['path'])
            if saved:
                notice = dict(message=saved)
        context = CURRENT_NOTICE.set(notice)
        try:
            await self.app(scope, receive, send)
        finally:
            CURRENT_NOTICE.reset(context)
