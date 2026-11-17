"""Read literal public-table data from old MySQL dumps without executing SQL."""
from decimal import Decimal
import re

PUBLIC_TABLES = {'company', 'data', 'format'}
HEADER = re.compile(r'INSERT\s+INTO\s+`?(\w+)`?\s*(?:\(([^)]+)\))?\s*VALUES\s*', re.I)
NUMBER = re.compile(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?')


def statements(text):
    """Split only outside literals/comments; a password cannot introduce SQL."""
    parts = []
    pos = 0
    while pos < len(text):
        char = text[pos]
        if char in ("'", '"', '`'):
            quote = char
            start = pos
            pos += 1
            while pos < len(text):
                if text[pos] == '\\':
                    pos += 2
                elif text[pos] == quote:
                    pos += 1
                    if pos < len(text) and text[pos] == quote:
                        pos += 1
                    else:
                        break
                else:
                    pos += 1
            else:
                raise ValueError('Unterminated SQL literal')
            parts.append(text[start:pos])
        elif text.startswith('/*', pos):
            end = text.find('*/', pos+2)
            if end < 0:
                raise ValueError('Unterminated SQL comment')
            parts.append(' ')
            pos = end+2
        elif char == '#' or (text.startswith('--', pos) and
                             (pos+2 == len(text) or text[pos+2].isspace())):
            end = text.find('\n', pos)
            pos = len(text) if end < 0 else end+1
            parts.append('\n')
        elif char == ';':
            yield ''.join(parts).strip()+';'
            parts = []
            pos += 1
        else:
            parts.append(char)
            pos += 1
    if ''.join(parts).strip():
        yield ''.join(parts).strip()


def literal_rows(text, pos, columns):
    rows = []
    def peek():
        nonlocal pos
        while pos < len(text) and text[pos].isspace():
            pos += 1
        if pos >= len(text):
            raise ValueError('Truncated literal INSERT')
        return text[pos]
    while True:
        if peek() != '(':
            raise ValueError('Expected literal tuple')
        pos += 1
        values = []
        while True:
            char = peek()
            if char in ("'", '"'):
                quote = char
                pos += 1
                parts = []
                while pos < len(text):
                    char = text[pos]
                    pos += 1
                    if char == '\\':
                        if pos >= len(text):
                            raise ValueError('Truncated escape')
                        char = text[pos]
                        pos += 1
                        parts.append({'0':'\0', 'b':'\b', 'n':'\n', 'r':'\r',
                                      't':'\t', 'Z':'\x1a'}.get(char, char))
                    elif char == quote:
                        if pos < len(text) and text[pos] == quote:
                            parts.append(quote)
                            pos += 1
                        else:
                            break
                    else:
                        parts.append(char)
                else:
                    raise ValueError('Unterminated value')
                value = ''.join(parts)
            elif text[pos:pos+4].upper() == 'NULL':
                value = None
                pos += 4
            else:
                number = NUMBER.match(text, pos)
                if number is None:
                    raise ValueError('Only literal SQL values are accepted')
                value = Decimal(number[0])
                pos = number.end()
            values.append(value)
            delimiter = peek()
            pos += 1
            if delimiter == ')':
                break
            if delimiter != ',':
                raise ValueError('Invalid literal delimiter')
        if len(values) != len(columns):
            raise ValueError('Column/value count mismatch')
        rows.append(dict(zip(columns, values)))
        delimiter = peek()
        pos += 1
        if delimiter == ';':
            if text[pos:].strip():
                raise ValueError('Unexpected INSERT suffix')
            return rows
        if delimiter != ',':
            raise ValueError('Invalid row delimiter')


def public_tables(text):
    output = {table: [] for table in sorted(PUBLIC_TABLES)}
    schemas = {}
    for statement in statements(text):
        create = re.match(r'CREATE TABLE\s+`?(\w+)`?\s*\((.*?)\)\s*ENGINE', statement, re.I|re.S)
        if create and create[1].lower() in PUBLIC_TABLES:
            schemas[create[1].lower()] = re.findall(r'(?:^|,)\s*`([^`]+)`\s+[A-Za-z]', create[2])
        insert = HEADER.match(statement)
        if insert is None or insert[1].lower() not in PUBLIC_TABLES:
            continue
        table = insert[1].lower()
        columns = ([c.strip().strip('`').lower() for c in insert[2].split(',')]
                   if insert[2] else [c.lower() for c in schemas.get(table, [])])
        if not columns or len(set(columns)) != len(columns):
            raise ValueError('Missing or ambiguous INSERT columns')
        output[table].extend(literal_rows(statement, insert.end(), columns))
    return output
