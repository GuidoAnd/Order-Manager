"""Selección y descarga de los cuatro formatos desde 320 px, sin JS."""

import asyncio
from copy import deepcopy
from pathlib import Path
from zipfile import ZipFile

import pytest
from playwright.async_api import async_playwright

from order_manager.api import make_app
from test_export_formats import prepare
from test_mobile import VIEWPORTS, assert_layout, serve_asgi


async def check_downloads(tmp_path, viewport):
    app = make_app(tmp_path / "globals.json")
    journey_id = prepare(app)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": viewport[0], "height": viewport[1]},
            java_script_enabled=False,
        )
        await context.route("**/*", lambda route: serve_asgi(app, route))
        page = await context.new_page()
        page.set_default_timeout(5000)
        try:
            await page.goto("http://order-manager.test/confirmar/close")
            await assert_layout(page, viewport)
            await page.get_by_role("link", name="Cancelar", exact=True).click()
            assert app.state.store.get_journey()["id"] == journey_id
            await page.goto("http://order-manager.test/confirmar/close")
            await page.get_by_role("button", name="Cerrar ventas y elegir descarga CSV / JSON / ZIP").click()
            await page.get_by_role("heading", name="Jornada cerrada", exact=True).wait_for()
            # El adaptador ASGI sigue el 303 internamente; visita su URL GET real.
            await page.goto(f"http://order-manager.test/exportaciones?journey_id={journey_id}")
            assert app.state.store.get_journey() is None
            original = deepcopy(app.state.store.get_globals())
            assert await page.get_by_role("radio", name="Todo en ZIP").is_checked()
            await assert_layout(page, viewport)
            for label in await page.locator(".export-options label").all():
                box = await label.bounding_box()
                assert box["height"] >= 44
            for name, suffix in (
                ("CSV resumen", "-resumen.csv"), ("CSV detallado", "-detalle.csv"),
                ("JSON completo", ".json"), ("Todo en ZIP", ".zip"),
            ):
                await page.get_by_role("radio", name=name).check()
                assert await page.locator('.export-options input:checked').count() == 1
                async with page.expect_download() as download_info:
                    await page.get_by_role("button", name="Descargar", exact=True).click()
                download = await download_info.value
                assert await download.failure() is None
                assert download.suggested_filename == f"jornada-{journey_id}{suffix}"
                assert Path(await download.path()).stat().st_size > 0
                if suffix == ".zip":
                    with ZipFile(await download.path()) as archive:
                        assert len(archive.namelist()) == 3
                assert app.state.store.get_globals() == original
                assert await page.get_by_role("heading", name="Jornada cerrada", exact=True).is_visible()
            await page.reload()
            assert await page.get_by_role("radio", name="Todo en ZIP").is_checked()
            assert app.state.store.get_globals() == original
            await page.get_by_role("link", name="Volver al Dashboard", exact=True).click()
            await page.get_by_role("heading", name="Dashboard", exact=True).wait_for()
            await page.goto("http://order-manager.test/registros")
            downloads = page.locator(".export-downloads")
            toggle = downloads.locator("summary")
            assert await downloads.get_attribute("open") is None
            assert not await page.get_by_role("radio", name="CSV detallado").is_visible()
            assert (await toggle.bounding_box())["height"] >= 44
            await toggle.click()
            assert await page.get_by_role("radio", name="CSV detallado").is_visible()
            await assert_layout(page, viewport)
            await page.get_by_role("radio", name="CSV detallado").check()
            async with page.expect_download() as download_info:
                await page.get_by_role("button", name="Descargar", exact=True).click()
            assert (await download_info.value).suggested_filename.endswith("-detalle.csv")
            assert app.state.store.get_globals() == original
            await toggle.focus()
            await page.keyboard.press("Enter")
            assert not await page.get_by_role("radio", name="CSV detallado").is_visible()
            await assert_layout(page, viewport)
            await toggle.click()
            await page.reload()
            assert await downloads.get_attribute("open") is None
            assert not await page.get_by_role("radio", name="CSV detallado").is_visible()
            assert app.state.store.get_globals() == original
            app.state.store.create_journey("Otra")
            app.state.store.close_journey()
            await page.goto(f"http://order-manager.test/exportaciones?journey_id={journey_id}")
            assert await page.get_by_role("alert").is_visible()
            assert await page.get_by_role("button", name="Descargar", exact=True).count() == 0
            await assert_layout(page, viewport)
        finally:
            await browser.close()


@pytest.mark.parametrize("viewport", VIEWPORTS)
def test_export_choices_mobile_and_desktop(tmp_path, viewport):
    asyncio.run(check_downloads(tmp_path, viewport))
