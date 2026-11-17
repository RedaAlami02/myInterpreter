"""Strict extraction of explicitly labeled annual tables from saved primary text.

Extraction evidence is not permission to publish financial updates.
"""
from decimal import Decimal
import hashlib
import re
import unicodedata


def normalized(value):
    return ' '.join(unicodedata.normalize('NFKC', value).casefold().split())


def number(token):
    token = token.replace('\u00a0', ' ').replace('\u202f', ' ')
    if not re.fullmatch(r'-?(?:[0-9]{1,3}(?: [0-9]{3})+|[0-9]+)(?:,[0-9]+)?',token):
        raise ValueError('AMBIGUOUS_PRIMARY_NUMBER')
    return Decimal(token.replace(' ', '').replace(',', '.'))


def extract(text, pdf_sha256, issuer, page_index, context, row_bindings, years):
    if not re.fullmatch('[a-f0-9]{64}',pdf_sha256) or len(text)>12*1024*1024:
        raise ValueError('INVALID_PRIMARY_EVIDENCE')
    pages=text.split('\f')
    if not issuer or normalized(issuer) not in normalized(text[:100000]) or not 0<=page_index<len(pages):
        raise ValueError('PRIMARY_ISSUER_OR_PAGE_DIFFERS')
    page=pages[page_index]
    if normalized(context) not in normalized(page):
        raise ValueError('PRIMARY_SCOPE_CONTEXT_DIFFERS')
    headers=[line for line in page.splitlines() if re.match(r'^\s*En KMAD\s+',line)]
    if len(headers)!=1 or [int(v) for v in re.findall(r'\b[12][0-9]{3}\b',headers[0])]!=years:
        raise ValueError('PRIMARY_UNIT_OR_YEAR_COLUMNS_DIFFER')
    output=[]
    for metric,binding in row_bindings.items():
        rows=[]
        for line in page.splitlines():
            columns=re.split(r'\s{2,}',line.strip())
            if columns and normalized(columns[0])==normalized(binding['label']):
                rows.append((line,columns))
        if len(rows)!=1 or len(rows[0][1])<len(years)+1:
            raise ValueError('PRIMARY_ROW_AMBIGUOUS_OR_MISSING')
        raw,columns=rows[0]
        for year,token in zip(years,columns[1:]):
            value=number(token)
            output.append({'metric':metric,'source_year':year,'scope':binding['scope'],
                'source_value_decimal':format(value,'f'),'source_unit':'KMAD',
                'currency':'MAD','value_mad_decimal':format(value*1000,'f'),
                'pdf_sha256':pdf_sha256,'text_sha256':hashlib.sha256(text.encode()).hexdigest(),
                'page_index':page_index,'header_quote':headers[0].strip(),'row_quote':raw.strip(),
                'period_context':context,'status':'PRIMARY_TABLE_EXTRACTED','publication_eligible':False})
    return output
