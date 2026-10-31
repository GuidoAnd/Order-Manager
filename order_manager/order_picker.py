"""Selección de artículos sobre borradores, con formularios HTML y sin escrituras de negocio."""

from copy import deepcopy

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse

from . import web
from .article_search import ArticleSearch
from .input_validation import bounded_text
from .store import DomainError, MAX_INPUT_INTEGER
from .templating import render


PICKER_PATH = '/ui/orders/articles'


def picker_url(key):
    return f'/ordenes/borrador/{key}/articulos'


def search_state(picker):
    return ArticleSearch(picker['query'], picker['category'], picker['subcategory'], picker['page'])


def quantity(value):
    try:
        number = int(value)
    except (ValueError, TypeError):
        raise DomainError('La cantidad de cada artículo seleccionado debe ser un entero positivo.') from None
    if not 1 <= number <= MAX_INPUT_INTEGER:
        raise DomainError(f'La cantidad debe estar entre 1 y {MAX_INPUT_INTEGER}.')
    return number


def register_order_picker(app, store, fields, drafts):
    def snapshot(entry, picker, error='', status=200):
        key = drafts.put(entry['session'], entry['values'], entry['rows'], error, status, picker=picker)
        return RedirectResponse(picker_url(key), status_code=303)

    def open_picker(session, values, rows, target=None):
        selected = {}
        if target is not None and rows[target].get('catalog_id'):
            selected[rows[target]['catalog_id']] = rows[target].get('quantity') or '1'
        picker = dict(query='', category='', subcategory='', page=1, selected=selected,
                      target=target, flow={'result': ''})
        return snapshot(dict(session=session, values=values, rows=rows), picker)

    def entry_for(key):
        entry = drafts.get(key)
        if not entry.get('picker'):
            raise DomainError('Selección de artículos no disponible.', 409)
        return entry

    def completed(entry):
        if entry['session']['result']:
            return RedirectResponse(entry['session']['result'], status_code=303)
        result = entry['picker']['flow']['result']
        if result:
            return RedirectResponse('/ordenes/borrador/' + result, status_code=303)

    @app.get('/ordenes/borrador/{draft_id}/articulos')
    def picker_page(draft_id: str):
        with drafts.lock:
            entry = entry_for(draft_id)
            done = completed(entry)
            if done:
                return done
            inventory = entry['session']['context']['inventory']
            picker = entry['picker']
            search = search_state(picker)
            matches = search.matching(inventory['articles'])
            groups = []
            for size in (2, 3, 4, 5):
                articles, total, page, pages = search.paginate(matches, page_size=size)
                groups.append(dict(size=size, articles=articles, total=total, page=page, pages=pages))
            names = {article['id']: article['name'] for article in inventory['articles']}
            content = render('web/order_picker.html', token=draft_id, picker=picker, groups=groups,
                             inventory=inventory, names=names, error=entry['error'], path=PICKER_PATH,
                             max_quantity=MAX_INPUT_INTEGER)
            return HTMLResponse(web.layout('Elegir artículos', content), status_code=entry['status'])

    @app.post(PICKER_PATH)
    async def choose_articles(request: Request):
        values = await fields(request)
        with drafts.lock, store.lock:
            entry = entry_for(values.get('editor_token', ''))
            done = completed(entry)
            if done:
                return done
            session = entry['session']
            journey = store.get_journey()
            if not journey or journey['id'] != session['journey_id']:
                raise DomainError('La jornada cambió. La selección no se incorporó a la orden.', 409)
            picker = deepcopy(entry['picker'])
            picker['flow'] = entry['picker']['flow']
            inventory = session['context']['inventory']
            try:
                size = int(values.get('page_size', '5'))
                visible, _, page, _ = search_state(picker).results(inventory['articles'], page_size=size)
                if picker['target'] is not None:
                    chosen = values.get('selected_id', '')
                    if chosen and not any(article['id'] == chosen for article in visible):
                        raise DomainError('Artículo no disponible en esta página.')
                    # Una selección en otra página sigue vigente hasta elegir otra.
                    if chosen:
                        picker['selected'] = {chosen: values.get('amount_' + chosen, '1')}
                    elif any(article['id'] in picker['selected'] for article in visible):
                        picker['selected'] = {}
                else:
                    for article in visible:
                        article_id = article['id']
                        picker['selected'].pop(article_id, None)
                        if values.get('selected_' + article_id) == '1':
                            picker['selected'][article_id] = values.get('amount_' + article_id, '1')
                if len(picker['selected']) > 50:
                    raise DomainError('La orden admite hasta 50 líneas.')
                action = values.get('action', '')
                if action == 'apply':
                    if not picker['selected']:
                        raise DomainError('Selecciona al menos un artículo.')
                    rows = deepcopy(entry['rows'])
                    catalog = {article['id']: article for article in inventory['articles']}
                    for article_id, amount in picker['selected'].items():
                        if article_id not in catalog:
                            raise DomainError('Artículo no disponible en el inventario del editor.')
                        row = dict(source='inventory', catalog_id=article_id, quantity=str(quantity(amount)))
                        target = picker['target']
                        if target is not None:
                            previous = rows[target]
                            if previous.get('catalog_id') == article_id:
                                row = {**previous, **row}
                            rows[target] = row
                        else:
                            blank = next((i for i, old in enumerate(rows) if not old.get('catalog_id')
                                          and not old.get('name') and old.get('source', 'inventory') == 'inventory'), None)
                            if blank is None:
                                rows.append(row)
                            else:
                                rows[blank] = row
                    if len(rows) > 50:
                        raise DomainError('La orden admite hasta 50 líneas; quita líneas antes de agregar más.')
                    key = drafts.put(session, entry['values'], rows)
                    picker['flow']['result'] = key
                    return RedirectResponse('/ordenes/borrador/' + key, status_code=303)
                if action.startswith('unpick_'):
                    picker['selected'].pop(action.removeprefix('unpick_'), None)
                elif action not in ('search', 'previous', 'next', 'keep'):
                    raise DomainError('Acción de selección no reconocida.')
                try:
                    filters = {key: bounded_text(values.get(field, ''), 'Filtro')
                               for key, field in (('query', 'search_q'), ('category', 'category'),
                                                  ('subcategory', 'subcategory'))}
                except ValueError as error:
                    raise DomainError(str(error)) from None
                changed = any(picker[key] != value for key, value in filters.items())
                picker.update(filters)
                picker['page'] = 1 if changed or action == 'search' else max(1, page + (
                    1 if action == 'next' else -1 if action == 'previous' else 0))
                return snapshot(entry, picker)
            except (DomainError, ValueError) as error:
                message = str(error) if isinstance(error, DomainError) else 'Página de artículos inválida.'
                status = error.status if isinstance(error, DomainError) else 400
                return snapshot(entry, picker, message, status)

    return open_picker
