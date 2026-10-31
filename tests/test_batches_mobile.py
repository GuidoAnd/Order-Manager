"""Flujo de tandas sin JavaScript, botones y subtotales desde 320 px."""

import asyncio

import pytest
from playwright.async_api import async_playwright

from order_manager.api import make_app
from test_mobile import VIEWPORTS, assert_layout, choose_order_article, serve_asgi


async def check_batches(tmp_path, viewport):
    app = make_app(data_dir=tmp_path / 'data')
    store = app.state.store
    store.create_journey('Turno')
    author = store.add_author('Ana')
    for n in range(6):
        store.add_author(f'Autor {n} con nombre y apellido extendidos para revisión móvil')
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': viewport[0], 'height': viewport[1]},
                                            java_script_enabled=False)
        await context.route('**/*', lambda route: serve_asgi(app, route))
        page = await context.new_page()
        page.set_default_timeout(5000)
        try:
            await page.goto('http://127.0.0.1/jornada')
            view = page.locator('#batch-results .table-page-view:visible')
            assert await view.count() == 1
            size = 2 if viewport[0] < 375 else 3 if viewport[0] <= 650 else 4 if viewport[0] < 1024 else 5
            assert await view.locator('tbody tr').count() == size
            await view.get_by_role('link', name='Siguiente').click()
            await view.get_by_role('link', name='Anterior').click()
            row = view.locator('tbody tr').first
            await row.get_by_label('Serie para Ana').select_option('20')
            assert (await row.get_by_label('Serie para Ana').bounding_box())['height'] >= 44
            await row.get_by_role('button', name='Asignar serie').click()
            assert await row.get_by_text('Serie 20 · Tanda 1 · Abierta').is_visible()
            await assert_layout(page, viewport)
            if viewport[0] <= 650:
                assert await page.locator('.batch-panel h3').evaluate('n => getComputedStyle(n).textAlign') == 'center'
                assert await row.locator('td').first.evaluate('n => getComputedStyle(n).textAlign') == 'center'
                assert await page.locator('.journey-final-panel').evaluate('n => getComputedStyle(n).textAlign') == 'center'
            else:
                assert await page.locator('.journey-final-panel').evaluate('n => getComputedStyle(n).textAlign') == 'right'
            await page.goto('http://127.0.0.1/ordenes/nueva')
            assert await page.locator('select[name="series"]').count() == 0
            await page.get_by_label('Autor', exact=True).select_option(author['id'])
            await page.get_by_label('Numeración', exact=True).fill('081')
            await choose_order_article(page, 0, 'Cafe')
            await assert_layout(page, viewport)
            add = await page.get_by_role('button', name='Agregar artículo', exact=True).bounding_box()
            save = await page.get_by_role('button', name='Guardar orden', exact=True).bounding_box()
            assert save['y'] - add['y'] - add['height'] >= 24
            await page.get_by_role('button', name='Guardar orden', exact=True).click()
            assert store.get_journey()['orders'][0]['series'] == '20'
            await page.goto('http://127.0.0.1/jornada')
            await row.get_by_role('link', name='Cerrar tanda', exact=True).click()
            assert await page.get_by_text('Serie 20 · Tanda 1', exact=True).is_visible()
            await assert_layout(page, viewport)
            close = page.get_by_role('button', name='Confirmar cierre de tanda')
            cancel = page.get_by_role('link', name='Cancelar', exact=True)
            assert (await close.bounding_box())['height'] >= 44
            assert (await cancel.bounding_box())['height'] >= 44
            if viewport[0] <= 650:
                a, b = await close.bounding_box(), await cancel.bounding_box()
                assert b['y'] - a['y'] - a['height'] >= 20
            await close.click()
            await row.get_by_label('Serie para Ana').select_option('10')
            await row.get_by_role('button', name='Asignar serie').click()
            assert await row.get_by_text('Serie 10 · Tanda 2 · Abierta').is_visible()
            order = store.get_journey()['orders'][0]
            await page.goto(f'http://127.0.0.1/ordenes/{order["id"]}/editar')
            assert await page.get_by_text('Cerrada; se permiten correcciones.', exact=False).is_visible()
            await page.get_by_label('Numeración', exact=True).fill('083')
            await page.locator('input[name="quantity_0"]').fill('2')
            await page.get_by_role('button', name='Guardar orden', exact=True).click()
            assert store.get_journey()['orders'][0]['batch_id'] == order['batch_id']
            await page.goto('http://127.0.0.1/jornada')
            assert await page.get_by_text('Bloque 1 de la tanda 1', exact=True).filter(visible=True).count() == 1
            await assert_layout(page, viewport)
            await view.get_by_role('link', name='Siguiente').click()
            later = view.locator('tbody tr').first
            name = (await later.locator('td').first.inner_text()).removeprefix('Autor').strip()
            await later.locator('select[name="series"]').select_option('10')
            await later.get_by_role('button', name='Asignar serie').click()
            assert await later.get_by_text('Serie 10 · Tanda 1 · Abierta').is_visible()
            assert name in await later.locator('td').first.inner_text()
            await later.get_by_role('link', name='Cerrar tanda', exact=True).click()
            await page.get_by_role('link', name='Cancelar', exact=True).click()
            assert await later.get_by_text('Serie 10 · Tanda 1 · Abierta').is_visible()
            await later.get_by_role('link', name='Cerrar tanda', exact=True).click()
            await page.get_by_role('button', name='Confirmar cierre de tanda').click()
            assert await later.get_by_text('Tanda 1 cerrada. Sin tanda abierta.').is_visible()
            await assert_layout(page, viewport)
        finally:
            await context.close()
            await browser.close()


@pytest.mark.parametrize('viewport', VIEWPORTS)
def test_batch_workflow_mobile_and_desktop(tmp_path, viewport):
    asyncio.run(check_batches(tmp_path, viewport))
