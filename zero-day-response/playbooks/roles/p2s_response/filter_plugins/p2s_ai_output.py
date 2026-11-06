"""Parse and validate AI output without dependencies or text extraction."""
import hashlib
import json
import re
from collections.abc import Mapping


KEYWORDS = {'type', 'required', 'properties', 'items', 'pattern', 'minLength', 'description'}


def _pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError('duplicate key ' + key)
        out[key] = value
    return out


def _constant(value):
    raise ValueError('non-finite constant ' + value)


def p2s_ai_output(raw, schema):
    errors = []
    digest = ''
    value = None

    def error(message):
        if len(errors) < 20:
            errors.append(message)

    def schema_check(s, path):
        if not isinstance(s, Mapping):
            error(path + ': invalid schema')
            return
        for key in s:
            if key not in KEYWORDS:
                error('unsupported schema keyword ' + str(key))
        for key, child in s.get('properties', {}).items():
            schema_check(child, path + '.' + key)
        if 'items' in s:
            schema_check(s['items'], path + '[]')

    def validate(v, s, path):
        kind = s.get('type')
        matches = {
            'object': isinstance(v, Mapping),
            'array': isinstance(v, list),
            'string': isinstance(v, str),
            'boolean': isinstance(v, bool),
            'integer': isinstance(v, int) and not isinstance(v, bool),
            'number': isinstance(v, (int, float)) and not isinstance(v, bool),
        }
        if kind is not None and (kind not in matches or not matches[kind]):
            error(path + ': not ' + ('an object' if kind == 'object' else str(kind)))
            return
        if isinstance(v, Mapping):
            for key in s.get('required', []):
                if key not in v:
                    error(path + '.' + key + ': missing')
            for key, child in s.get('properties', {}).items():
                if key in v:
                    validate(v[key], child, path + '.' + key)
        if isinstance(v, list) and 'items' in s:
            for i, item in enumerate(v):
                validate(item, s['items'], path + '[' + str(i) + ']')
        if isinstance(v, str):
            if 'minLength' in s and len(v.strip()) < s['minLength']:
                error(path + ': minLength')
            if 'pattern' in s:
                match = re.search(s['pattern'], v)
                if not match or (s['pattern'].endswith('$') and match.end() != len(v)):
                    error(path + ': pattern')

    try:
        schema_check(schema, '$')
        if isinstance(raw, str):
            digest = hashlib.sha256(raw.encode('utf-8')).hexdigest()
            if len(raw) > 65536:
                raise ValueError('more than 65536 characters')
            text = raw.strip()
            lines = text.splitlines()
            if len(lines) >= 2 and lines[0] in ('```json', '```') and lines[-1] == '```':
                text = '\n'.join(lines[1:-1])
            value = json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant)
        elif isinstance(raw, Mapping):
            digest = hashlib.sha256(json.dumps(raw, separators=(',', ':'), sort_keys=True,
                                              allow_nan=False).encode('utf-8')).hexdigest()
            value = raw
        else:
            error('$: not an object or JSON text')
        if not isinstance(value, Mapping):
            error('$: not an object')
        elif not errors:
            validate(value, schema, '$')
    except json.JSONDecodeError as exc:
        error('parse: ' + exc.msg + ' line ' + str(exc.lineno))
    except (ValueError, TypeError, RecursionError, re.error) as exc:
        error('parse: ' + str(exc)[:160])
    return {'ok': not errors, 'errors': errors, 'value': value if not errors else None,
            'sha256': digest}


class FilterModule:
    def filters(self):
        return {'p2s_ai_output': self.safe_output}

    @staticmethod
    def safe_output(raw, schema):
        from ansible.utils.unsafe_proxy import wrap_var
        result = p2s_ai_output(raw, schema)
        result['value'] = wrap_var(result['value'])
        return result
