"""Consultas de tandas y bloques, sin modificar órdenes ni datos históricos."""


def active_batch(author):
    return next((batch for batch in author.get('batches', []) if batch['closed_at'] is None), None)


def find_batch(author, batch_id):
    return next((batch for batch in author.get('batches', []) if batch['id'] == batch_id), None)


def subtotal_blocks(author, orders):
    by_batch = {}
    for order in orders:
        by_batch.setdefault(order.get('batch_id'), []).append(order)
    groups = [(batch['number'], by_batch.get(batch['id'], []))
              for batch in author.get('batches', [])]
    legacy = by_batch.get(None, [])
    if legacy:
        groups.append((None, legacy))
    result = []
    for batch_number, items in groups:
        items = sorted(items, key=lambda order: (order.get('serial_number', order['number']), order['number']))
        for start in range(0, len(items), 10):
            number = start // 10 + 1
            title = (f'Bloque {number} de la tanda {batch_number}' if batch_number is not None
                     else f'Bloque {number} sin tanda asignada')
            result.append(dict(title=title, number=number, batch_number=batch_number,
                               orders=items[start:start + 10]))
    return result
