"""Preferencias de edicao compartilhadas pelo painel e pelo processador."""
import json
import os
import tempfile
from . import config as C

PATH = C.DATA / 'edit-settings.json'
DEFAULTS = {'subtitles': True, 'subtitle_style': 'highlight', 'zoom': C.ZOOM,
            'watermark': '', 'watermark_position': 'top_right', 'duration_mode': 'fixed',
            'context_before': 25, 'context_after': 10, 'min_duration': 15, 'max_duration': 55,
            'ai_provider': 'openai', 'orientation': 'vertical', 'background': 'blur'}


def validate(data):
    if not isinstance(data, dict) or set(data) - set(DEFAULTS):
        raise ValueError('Configuracao de edicao invalida.')
    data = {**DEFAULTS, **data}
    if type(data['subtitles']) is not bool or type(data['zoom']) is not bool:
        raise ValueError('Opcoes de legenda e zoom devem ser booleanas.')
    if data['subtitle_style'] not in ('highlight', 'pop', 'clean'):
        raise ValueError('Modelo de legenda invalido.')
    if data['watermark_position'] not in ('top_left', 'top_right', 'bottom_left', 'bottom_right'):
        raise ValueError('Posicao de marca invalida.')
    if not isinstance(data['watermark'], str) or len(data['watermark']) > 40 or any(ord(c) < 32 for c in data['watermark']):
        raise ValueError('Marca deve ter ate 40 caracteres em uma linha.')
    if data['duration_mode'] not in ('fixed', 'pause', 'ai'):
        raise ValueError('Modo de duracao invalido.')
    if data['ai_provider'] not in ('openai', 'anthropic'):
        raise ValueError('Provedor de IA invalido.')
    if data['orientation'] not in ('vertical', 'horizontal'):
        raise ValueError('Formato de video invalido.')
    if data['background'] not in ('blur', 'black'):
        raise ValueError('Fundo de video invalido.')
    for name, low, high in [('context_before', 5, 120), ('context_after', 5, 120),
                            ('min_duration', 5, 180), ('max_duration', 5, 180)]:
        if type(data[name]) is not int or not low <= data[name] <= high:
            raise ValueError(f'{name}: valor deve estar entre {low} e {high} segundos.')
    if data['min_duration'] > data['max_duration']:
        raise ValueError('Duracao minima nao pode superar a maxima.')
    if data['duration_mode'] != 'fixed' and data['min_duration'] > data['context_before'] + data['context_after']:
        raise ValueError('A duracao minima nao pode superar o contexto total.')
    return dict(data)


def load():
    if not PATH.exists():
        return dict(DEFAULTS)
    with PATH.open(encoding='utf-8') as f:
        return validate(json.load(f))


def save(data):
    settings = validate(data)
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=PATH.parent, delete=False) as f:
            name = f.name
            json.dump(settings, f, ensure_ascii=False)
        os.replace(name, PATH)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)
    return settings
