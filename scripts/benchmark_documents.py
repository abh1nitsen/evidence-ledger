"""Compare Groq-only and optional OCR fusion on independently authored layouts."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from docintel.providers import Groq
from docintel.ocr import Hybrid
from docintel.evaluate import evaluate_documents
from docintel.pipeline import atomic_json
parser=argparse.ArgumentParser()
parser.add_argument('--ocr',choices=['none','paddle'],default='none')
parser.add_argument('--output',default='runs/document-benchmark.json')
parser.add_argument('--db',default='runs/document-benchmark.sqlite')
args=parser.parse_args()
provider=Groq()
if args.ocr=='paddle':provider=Hybrid(provider)
report=evaluate_documents('data/documents',provider,args.db,str(Path(args.output).with_suffix('.batch.json')))
atomic_json(args.output,report)
print(json.dumps({k:report[k] for k in ('provider','printed_field_match','absent_field_match','document_type_accuracy','extraction_failures','elapsed_seconds')}))
raise SystemExit(2 if report['extraction_failures'] else 0)
