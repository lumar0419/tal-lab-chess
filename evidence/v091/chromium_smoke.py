from pathlib import Path
import re
import threading
from playwright.sync_api import sync_playwright
from web_server import make_server

server = make_server(0)
threading.Thread(target=server.serve_forever, daemon=True).start()
try:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path='/usr/bin/chromium',
                                            headless=True, args=['--no-sandbox'])
        page = browser.new_page()
        page.add_init_script("localStorage.setItem('tal_lab_analysis_auto_v055','off');")
        assets = Path('evidence-v087/pyodide').resolve()
        def runtime(route):
            asset = assets / route.request.url.rsplit('/',1)[-1]
            if asset.is_file():
                route.fulfill(path=asset, headers={'Access-Control-Allow-Origin':'*'})
            else:
                route.abort()
        page.route('https://cdn.jsdelivr.net/pyodide/v0.27.7/full/**', runtime)
        page.goto(f'http://127.0.0.1:{server.server_address[1]}/analysis')
        page.wait_for_function("document.querySelector('#fen-input').value.length > 0")
        box = page.locator('#auto-analyze')
        if box.is_checked():
            box.uncheck()
        page.locator('#compute-mode').select_option('local')
        page.locator('#fen-input').fill('r1bk2nr/p2p1pNp/n2B4/1p1NP2P/6P1/3P1Q2/P1P1K3/q5b1 w - - 1 22')
        page.locator('#load-fen').click()
        page.wait_for_function("document.querySelector('#fen-input').value.startsWith('r1bk')")
        page.locator('summary').filter(has_text='심층 분석').click()
        page.locator('#deep-seconds').select_option('60')
        page.locator('#start-deep').click()
        # An immediate mate makes root and reference short, but alternatives can
        # use their budgets, so inspect live results before stopping the worker.
        page.wait_for_function("document.querySelector('#best-move').textContent.includes('f3f6')",
                               timeout=35000)
        assert page.locator('#download-deep').is_enabled()
        if page.locator('#stop-analysis').is_enabled():
            page.locator('#stop-analysis').click()
        print('Chromium: local Pyodide deep start, completed f3f6, JSON export enabled, cancellation')
        browser.close()
finally:
    server.shutdown()
    server.server_close()
