"""Authored layout-diversity fixtures. No private receipts are used."""
import json
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1]/"data"/"documents"
ROOT.mkdir(parents=True,exist_ok=True)
CASES=[
("invoice_eur.png","invoice","""Vendor: Juniper Studio
Invoice ID: EU-2087
Invoice Date: 23/08/2026
Time: 14:35:00
Currency: EUR
Subtotal: 255.50
Tax: 51.10
Total: 306.60""",{'vendor':'Juniper Studio','invoice_id':'EU-2087','invoice_date':'2026-08-23','transaction_time':'14:35:00','currency':'EUR','subtotal':'255.50','tax':'51.10','total':'306.60'}),
("retail_sgd.png","retail_receipt","""HARBOR PHARMACY
Customer Receipt
Receipt Number: RT-701
Date: 2026-08-22
Time: 09:12:41
Currency: SGD
Product total: 13.08
Tax summary
Amount before tax: 12.00
Tax: 1.08
Total Sale: 13.08""",{'vendor':'HARBOR PHARMACY','invoice_id':'RT-701','invoice_date':'2026-08-22','transaction_time':'09:12:41','currency':'SGD','subtotal':'12.00','tax':'1.08','total':'13.08'}),
("payment_slip.png","payment_slip","""EXAMPLE COFFEE HOUSE
DATE/TIME:17/08/25 21:13:04
TID:00000017 INV:400731
CARD LABEL:AMEX
SALE
BASE : S$ 36.70
TIP : S$
TOTAL : S$
CUSTOMER COPY""",{'vendor':'EXAMPLE COFFEE HOUSE','invoice_id':'400731','invoice_date':'2025-08-17','transaction_time':'21:13:04','currency':'SGD','base_amount':'36.70'})]
keys=('vendor','invoice_id','invoice_date','transaction_time','currency','subtotal','tax','base_amount','tip','total')
gold=[]
for filename,kind,text,values in CASES:
 image=Image.new('RGB',(1100,1500),'#fffdf8');draw=ImageDraw.Draw(image);font=ImageFont.load_default(size=38)
 for n,line in enumerate(text.splitlines()):draw.text((65,110+n*90),line,font=font,fill='#182a25')
 draw.text((65,1410),'Authored test document',font=ImageFont.load_default(size=23),fill='#60786b')
 image.save(ROOT/filename)
 gold.append({'document':filename,'document_type':kind,'proposals':{k:values.get(k) for k in keys}})
(ROOT/'gold.json').write_text(json.dumps(gold,indent=2),encoding='utf-8')
