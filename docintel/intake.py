"""Conservative image admission; a model label is a suggestion, never proof."""

def disposition(document):
    if document.get('source_type') != 'image':
        return {'status': 'ready', 'message': ''}
    flags = {i['code'] for i in document.get('issues', [])}
    if 'not_invoice' in flags:
        return {'status': 'rejected', 'message': 'No supported receipt detected. Please send a bill photo. Nothing was added to purchases.'}
    if 'unreadable' in flags or not document.get('transcript', '').strip():
        return {'status': 'retake', 'message': 'The print could not be read. Retake the photo with the whole bill in focus. Nothing was added to purchases.'}
    if document.get('document_type') not in ('invoice', 'retail_receipt', 'payment_slip'):
        return {'status': 'rejected', 'message': 'This image could not be identified as a receipt. Please send a clearer bill photo. Nothing was added to purchases.'}
    return {'status': 'ready', 'message': ''}
