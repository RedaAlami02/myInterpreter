"""Invented PDF and company for isolated official-price tests; never genuine data."""
import hashlib
from pathlib import Path
import official_close


def pdf(day='03/11/2026',price='25,00'):
    lines=['Seance du '+day,'Designation  Ouv  Clot  Haut  Bas',
           'A  B  C  D  E  F  '+price+'  MA0000000001  EXAMPLE EQUITY  24,00  '+price+'  26,00  23,00  T']
    stream='\n'.join(f'BT /F1 9 Tf 20 {1100-i*20} Td ({text}) Tj ET' for i,text in enumerate(lines)).encode()
    objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
             b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 842 1191] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
             b'<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>',
             b'<< /Length '+str(len(stream)).encode()+b' >>\nstream\n'+stream+b'\nendstream',
             b'<< /SyntheticNote ('+b'x'*11000+b') >>']
    raw=b'%PDF-1.4\n';offsets=[]
    for i,value in enumerate(objects,1):
        offsets.append(len(raw));raw+=str(i).encode()+b' 0 obj\n'+value+b'\nendobj\n'
    xref=len(raw);raw+=b'xref\n0 7\n0000000000 65535 f \n'
    raw+=b''.join(f'{offset:010} 00000 n \n'.encode() for offset in offsets)
    return raw+b'trailer\n<< /Size 7 /Root 1 0 R >>\nstartxref\n'+str(xref).encode()+b'\n%%EOF\n'


def config():
    value = {'contract':'private-official-close-config/v1','provider_namespace':'feed_0123456789abcdef',
            'archive_project_reference':'abcdefghijklmnopqrst','worker_repository':'fixture/worker',
            'source_policy_sha256':'b'*64,'parser_sha256':hashlib.sha256(Path(official_close.__file__).read_bytes()).hexdigest(),
            'url_template':'https://example.invalid/reports/{ym}/{ymd}.pdf',
            'ca_pem':'-----BEGIN CERTIFICATE-----\nfixture\n-----END CERTIFICATE-----',
            'identities':[{'company_id':'example','c_name':'EXAMPLE EQUITY','symbol':'EXA','isin':'MA0000000001'}]}

    import official_close_collect
    value['source_policy_sha256']=hashlib.sha256(official_close_collect.canonical({k:v for k,v in value.items() if k!='source_policy_sha256'}).encode()).hexdigest()
    return value
