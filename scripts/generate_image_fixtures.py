"""Rebuild authored invoice renders and simulated lighting/layout variants (not real photos)."""
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = Path(__file__).resolve().parents[1] / "data" / "images"
ROOT.mkdir(parents=True, exist_ok=True)
page = Image.new("RGB", (1100, 1400), "#fffdf6")
draw = ImageDraw.Draw(page)
font = ImageFont.load_default(size=32)
title = ImageFont.load_default(size=48)
draw.text((90, 100), "INVOICE", font=title, fill="#173c46")
lines = ["Vendor: Northstar Office Supplies", "Invoice ID: INV-2026-041",
         "Invoice Date: 2026-10-01", "Currency: USD", "Subtotal: 1200.00",
         "Tax: 96.00", "Total: 1296.00"]
for index, text in enumerate(lines):
    draw.text((90, 250 + index*100), text, font=font, fill="#202525")
draw.line((90, 1050, 1000, 1050), fill="#173c46", width=3)
draw.text((90, 1100), "Synthetic fixture - not a real invoice", font=font, fill="#506060")
page.save(ROOT / "01_clean.jpg", quality=95)
shadow = page.copy()
pixels = shadow.load()
for y in range(shadow.height):
    for x in range(shadow.width):
        factor = .54 + .46*x/(shadow.width-1)
        pixels[x,y] = tuple(round(value*factor) for value in pixels[x,y])
shadow.filter(ImageFilter.GaussianBlur(.4)).save(ROOT / "02_shadow.jpg", quality=90)
angled = page.transform(page.size, Image.Transform.AFFINE, (1, .07, -65, -.025, 1, 35),
                       resample=Image.Resampling.BICUBIC, fillcolor="#a2a099")
angled.save(ROOT / "03_angled.jpg", quality=90)
Image.new("RGB", page.size, "#ffffff").save(ROOT / "04_blank.png")
gold = dict(invoice_id="INV-2026-041", vendor="Northstar Office Supplies", invoice_date="2026-10-01",
            currency="USD", subtotal="1200.00", tax="96.00", total="1296.00")
cases = [{"document": name, "fields": gold, "decision": "review", "slice": group}
         for name, group in [("01_clean.jpg", "render"), ("02_shadow.jpg", "simulated_shadow"), ("03_angled.jpg", "simulated_angle")]]
cases.append({"document": "04_blank.png", "fields": dict.fromkeys(gold), "decision": "review", "slice": "non_invoice"})
(ROOT / "gold.json").write_text(json.dumps(cases, indent=2)+"\n", encoding="utf-8")
