# app.py (Final Corrected Version for Batch and Single Comparison)

import asyncio
import csv
import io
import uuid
import threading
from urllib.parse import urlparse
from pathlib import Path
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, jsonify
from playwright.async_api import async_playwright
from PIL import Image
from pixelmatch.contrib.PIL import pixelmatch
from slugify import slugify

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'static'

# --- CONFIGURATION & GLOBAL STATE ---
VIEWPORTS = { "desktop": {"width": 1920, "height": 1080}, "tablet": {"width": 768, "height": 1024}, "mobile": {"width": 375, "height": 812}, }
BATCH_STATUS = {}

# --- HELPER FUNCTIONS ---
def generate_paths(url):
    parsed_url = urlparse(url)
    domain_slug = slugify(parsed_url.netloc)
    path_slug = slugify(parsed_url.path, separator='-') if parsed_url.path and parsed_url.path != '/' else 'index'
    output_dir = Path(app.config['UPLOAD_FOLDER']) / domain_slug
    output_dir.mkdir(parents=True, exist_ok=True)
    return { "dir": output_dir, "base_filename": path_slug, "relative_dir": f"{domain_slug}", }

def run_in_background(coro):
    def run_coro():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(coro)
        loop.close()
    thread = threading.Thread(target=run_coro)
    thread.start()

# --- CORE LOGIC ---
async def take_screenshot(browser, url, path, viewport, hide_selectors, use_full_page):
    page = await browser.new_page(viewport=viewport)
    try:
        await page.goto(url, wait_until='networkidle', timeout=60000)
        if hide_selectors:
            for selector in hide_selectors:
                await page.evaluate(f"document.querySelectorAll('{selector}').forEach(el => el.style.display = 'none')")
        await page.screenshot(path=path, full_page=use_full_page)
    finally:
        await page.close()

def create_diff_image(path_old, path_new, path_diff):
    try:
        img_old = Image.open(path_old).convert("RGBA")
        img_new = Image.open(path_new).convert("RGBA")
        max_width, max_height = max(img_old.width, img_new.width), max(img_old.height, img_new.height)
        img_old_resized, img_new_resized = Image.new("RGBA", (max_width, max_height)), Image.new("RGBA", (max_width, max_height))
        img_old_resized.paste(img_old), img_new_resized.paste(img_new)
        img_diff = Image.new("RGBA", (max_width, max_height))
        mismatched_pixels = pixelmatch(img_old_resized, img_new_resized, img_diff, threshold=0.1)
        img_diff.save(path_diff)
        return mismatched_pixels
    except FileNotFoundError:
        return -1

# --- BACKGROUND TASK ---
async def process_batch_job(batch_id, url_pairs, options):
    total_pairs = len(url_pairs)
    BATCH_STATUS[batch_id] = { 'status': 'Running', 'start_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 'progress': 0, 'total': total_pairs, 'completed': 0, 'results': [] }
    
    # --- THIS IS THE FIX ---
    # Create a new dictionary with only the arguments that take_screenshot expects.
    # We remove 'viewport_name' which was causing the error.
    screenshot_kwargs = {
        'viewport': options['viewport'],
        'hide_selectors': options['hide_selectors'],
        'use_full_page': options['use_full_page']
    }

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        for i, (url_old, url_new) in enumerate(url_pairs):
            result_item = { 'url_old': url_old, 'url_new': url_new, 'status': 'Failed', 'mismatched_pixels': -1 }
            try:
                paths = generate_paths(url_old)
                path_old_img = paths['dir'] / f"{paths['base_filename']}_old.png"
                path_new_img = paths['dir'] / f"{paths['base_filename']}_new.png"
                path_diff_img = paths['dir'] / f"{paths['base_filename']}_diff.png"

                # Use the new, clean kwargs dictionary here
                await asyncio.gather(
                    take_screenshot(browser, url_old, path_old_img, **screenshot_kwargs),
                    take_screenshot(browser, url_new, path_new_img, **screenshot_kwargs)
                )
                mismatched_pixels = await asyncio.to_thread(create_diff_image, path_old_img, path_new_img, path_diff_img)
                
                result_item.update({
                    'status': 'Success',
                    'mismatched_pixels': mismatched_pixels,
                    'paths': { 'old': f"{paths['relative_dir']}/{paths['base_filename']}_old.png", 'new': f"{paths['relative_dir']}/{paths['base_filename']}_new.png", 'diff': f"{paths['relative_dir']}/{paths['base_filename']}_diff.png", },
                    'options': {'viewport': options['viewport_name'], 'pixels': f"{mismatched_pixels:,}"}
                })
            except Exception as e:
                print(f"Error processing {url_old}: {e}")
                result_item['error_message'] = str(e)

            BATCH_STATUS[batch_id]['results'].append(result_item)
            BATCH_STATUS[batch_id]['completed'] = i + 1
            BATCH_STATUS[batch_id]['progress'] = int(((i + 1) / total_pairs) * 100)
        await browser.close()
    
    BATCH_STATUS[batch_id]['status'] = 'Complete'

# --- FLASK ROUTES ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/compare', methods=['POST'])
async def compare():
    url_old, url_new = request.form['url_old'], request.form['url_new']
    use_full_page = request.form.get('full_page') == 'true'
    viewport_choice = request.form.get('viewport_choice', 'desktop')
    selectors_to_hide_str = request.form.get('selectors_to_hide', '')
    options = { 'viewport': VIEWPORTS.get(viewport_choice), 'hide_selectors': [s.strip() for s in selectors_to_hide_str.split(',') if s.strip()], 'use_full_page': use_full_page }
    paths = generate_paths(url_old)
    path_old_img, path_new_img, path_diff_img = paths['dir'] / f"{paths['base_filename']}_old.png", paths['dir'] / f"{paths['base_filename']}_new.png", paths['dir'] / f"{paths['base_filename']}_diff.png"
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        await asyncio.gather( take_screenshot(browser, url_old, path_old_img, **options), take_screenshot(browser, url_new, path_new_img, **options) )
        await browser.close()
    mismatched_pixels = await asyncio.to_thread(create_diff_image, path_old_img, path_new_img, path_diff_img)
    return render_template('results.html', viewport=viewport_choice.capitalize(), diff_pixels=f"{mismatched_pixels:,}", old_image_url=f"{paths['relative_dir']}/{paths['base_filename']}_old.png", new_image_url=f"{paths['relative_dir']}/{paths['base_filename']}_new.png", diff_image_url=f"{paths['relative_dir']}/{paths['base_filename']}_diff.png")

@app.route('/result')
def view_result():
    return render_template('results.html', old_image_url=request.args.get('old'), new_image_url=request.args.get('new'), diff_image_url=request.args.get('diff'), viewport=request.args.get('viewport', 'N/A'), diff_pixels=request.args.get('pixels', 'N/A'))

@app.route('/batch_compare', methods=['POST'])
def batch_compare():
    if 'csv_file' not in request.files or request.files['csv_file'].filename == '': return "No file selected", 400
    file = request.files['csv_file']
    try:
        stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
        csv_reader = csv.reader(stream)
        next(csv_reader)
        url_pairs = [(row[0], row[1]) for row in csv_reader if len(row) >= 2 and row[0] and row[1]]
    except Exception as e: return f"Error reading CSV file: {e}", 400
    
    viewport_choice = request.form.get('viewport_choice', 'desktop')
    options = { 'viewport': VIEWPORTS.get(viewport_choice), 'viewport_name': viewport_choice.capitalize(), 'hide_selectors': [], 'use_full_page': request.form.get('full_page') == 'true' }
    batch_id = str(uuid.uuid4())
    batch_coroutine = process_batch_job(batch_id, url_pairs, options)
    run_in_background(batch_coroutine)
    return redirect(url_for('batch_status', batch_id=batch_id))

@app.route('/batch_status/<batch_id>')
def batch_status(batch_id):
    return render_template('batch_status.html', batch_id=batch_id)

@app.route('/api/batch_status/<batch_id>')
def api_batch_status(batch_id):
    return jsonify(BATCH_STATUS.get(batch_id, {'status': 'Not Found'}))

@app.route('/batch_results/<batch_id>')
def batch_results(batch_id):
    batch_data = BATCH_STATUS.get(batch_id)
    if not batch_data or batch_data['status'] != 'Complete':
        return "Batch not found or still in progress.", 404
    return render_template('batch_results.html', batch_data=batch_data, batch_id=batch_id)

if __name__ == '__main__':
    app.run(debug=True)