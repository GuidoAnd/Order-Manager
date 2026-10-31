"""Asignación y cierre confirmado de tandas desde la jornada."""

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .order_batches import active_batch, find_batch
from .store import DomainError, is_sale
from .table_pages import table_pages
from .templating import render


def batch_panel(journey, page=1):
    def row(author):
        batches = author.get('batches', [])
        current = active_batch(author)
        return render('web/batch_author.html', author=author, current=current,
                      previous=batches[-1]['id'] if batches else '', journey_id=journey['id'], page=page)
    pages = table_pages(journey['authors'], page, ('Autor', 'Asignación', 'Acciones'), row,
                        lambda number: f'/jornada?batch_page={number}', 'autores',
                        'Asignación de tandas', 'Agrega un autor para asignar una serie.', 'batch-results')
    return render('web/batch_panel.html', pages=pages)


def register_batch_ui(app, store, fields, notices):
    from . import web

    @app.get('/tandas/{author_id}/{batch_id}/cerrar', response_class=HTMLResponse)
    def confirm_batch(author_id: str, batch_id: str, batch_page: int = 1):
        with store.lock:
            journey = store.get_journey()
            author = next((a for a in (journey or {}).get('authors', []) if a['id'] == author_id), None)
            batch = find_batch(author, batch_id) if author else None
            if not batch or batch['closed_at'] is not None:
                raise DomainError('La tanda no está abierta o no corresponde al autor.', 409)
            orders = [o for o in journey['orders'] if o.get('batch_id') == batch_id]
            body = render('web/batch_close.html', author=author, batch=batch, journey_id=journey['id'],
                          count=len(orders), total=sum(o['total'] for o in orders if is_sale(o)),
                          page=max(1, batch_page))
            return web.layout('Cerrar tanda', body)

    @app.post('/ui/batches')
    async def batch_action(request: Request):
        values = await fields(request)
        try:
            page = max(1, int(values.get('batch_page', '1')))
        except ValueError:
            page = 1
        try:
            with store.lock:
                author_id = values.get('author_id', '')
                journey_id = values.get('journey_id', '')
                if values.get('action') == 'open':
                    batch = store.open_batch(author_id, values.get('series', ''), journey_id,
                                             values.get('previous_batch_id', ''))
                    code = 'batch_opened'
                elif values.get('action') == 'close' and values.get('confirm') == 'yes':
                    batch = store.close_batch(author_id, values.get('batch_id', ''), journey_id)
                    code = 'batch_closed'
                else:
                    raise DomainError('Confirme la acción de la tanda.')
                journey = store.get_journey()
                author = next(a for a in journey['authors'] if a['id'] == author_id)
                target = notices.url(f'/jornada?batch_page={page}#batch-results', code, author=author['name'],
                                     batch=batch['number'], series=batch['series'])
            return RedirectResponse(target, status_code=303)
        except DomainError as error:
            return HTMLResponse(web.journey_page(store, str(error), batch_page=page), status_code=error.status)
