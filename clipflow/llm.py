"""Refinamento opcional com LLM: melhor inicio/fim, titulo e nota. So roda em candidatos."""
import json
import logging
import re
import math

from . import config as C
from .transcribe import Word

log = logging.getLogger("llm")
MIN_LEN, MAX_LEN = 15.0, 55.0


def default_decision(duration: float, peak_offset: float) -> dict:
    return {"start": 0.0, "end": min(duration, MAX_LEN), "title": "Momento da live",
            "score": 50, "publish": True}


def _clamp(d: dict, duration: float, min_len=MIN_LEN, max_len=MAX_LEN) -> dict:
    s, e = float(d['start']), float(d['end'])
    if not math.isfinite(s) or not math.isfinite(e) or s < 0 or e > duration or e <= s:
        raise ValueError('Intervalo invalido retornado pela IA')
    if e - s < min_len:
        e = min(duration, s + min_len)
        s = max(0.0, e - min_len)
    if e - s > max_len:
        e = s + max_len
    d.update(start=s, end=e)
    return d


def pause_decision(words: list[Word], duration: float, peak_offset: float, min_len: float, max_len: float) -> dict:
    """Aproxima as bordas de pausas, buscando manter contexto ao redor do pico."""
    min_len = min(min_len, duration)
    max_len = min(max_len, duration)
    target_start = max(0.0, peak_offset - min(25.0, max_len * .7))
    target_end = min(duration, max(peak_offset + 10.0, target_start + min_len))
    boundaries = [0.0, duration]
    for a, b in zip(words, words[1:]):
        if b.start - a.end >= .35:
            boundaries.append((a.end + b.start) / 2)
    peak = max(0.0, min(peak_offset, duration))
    starts = [x for x in boundaries if max(0.0, peak - max_len) <= x <= peak]
    start = min(starts, key=lambda x: abs(x - target_start)) if starts else max(0.0, peak - min(25.0, max_len * .7))
    ends = [x for x in boundaries if x >= max(start + min_len, min(peak_offset, duration)) and x <= start + max_len]
    end = min(ends, key=lambda x: abs(x - target_end)) if ends else min(duration, start + max_len)
    if end - start < min_len:
        start = max(0.0, end - min_len)
    return {'start': start, 'end': end, 'title': 'Momento da live', 'score': 50,
            'publish': True, 'method': 'pausas'}


def refine(words: list[Word], duration: float, peak_offset: float, min_len=MIN_LEN, max_len=MAX_LEN,
           provider='openai') -> dict:
    fallback = pause_decision(words, duration, peak_offset, min_len, max_len)
    key = C.OPENAI_API_KEY if provider == 'openai' else C.ANTHROPIC_API_KEY
    if not key or not words:
        log.warning('IA %s indisponivel: chave ou transcricao ausente; usando pausas', provider)
        return fallback
    try:
        lines, buf = [], []
        for w in words:
            if not buf:
                t0 = w.start
            buf.append(w.text)
            if len(buf) >= 6:
                lines.append(f"[{t0:.1f}s] {' '.join(buf)}")
                buf = []
        if buf:
            lines.append(f"[{t0:.1f}s] {' '.join(buf)}")
        prompt = (
            f"Voce edita cortes verticais (Shorts) de lives de games. Abaixo esta a transcricao de um "
            f"trecho de {duration:.0f}s. Um pico de chat ocorreu em t~{peak_offset:.0f}s (o lance "
            f"costuma acontecer alguns segundos antes).\n"
            f"Escolha o melhor inicio e fim ({min_len:.0f} a {max_len:.0f}s de duracao): comece num gancho, "
            f"termine numa conclusao natural e nunca corte uma frase no meio.\n"
            f"Sua tarefa principal e avaliar o potencial editorial de engajamento e compartilhamento do trecho "
            f"como video curto para um publico que nao acompanhou a live. Avalie SOMENTE a transcricao; "
            f"o pico e apenas um sinal de interesse local e nao comprova que o trecho viralizara. "
            f"Nao veja nem invente elementos visuais, expressoes, efeitos, desempenho anterior ou metricas. "
            f"Atribua 0 a 25 pontos inteiros a cada criterio: gancho (prende nos primeiros segundos); "
            f"emocao (humor, surpresa, tensao ou reacao evidente no texto); compartilhamento "
            f"(vontade plausivel de comentar ou compartilhar); autonomia (contexto e conclusao compreensiveis "
            f"fora da live). Use a escala inteira: 0-5 ausente, 6-12 fraco, 13-19 razoavel, 20-25 forte, "
            f"com base em evidencias do texto, evitando notas altas por padrao. "
            f"A soma e um indicador subjetivo, nao uma probabilidade estatistica ou promessa de viralizacao. "
            f"Recomende publicar apenas quando houver elementos concretos de interesse. "
            f"Justifique em portugues com o que favorece o engajamento e o que limita a avaliacao; "
            f"se a transcricao for insuficiente, reconheca a incerteza e seja conservador. "
            f"Responda SOMENTE com JSON: "
            f'{{"start": numero, "end": numero, "title": "titulo curto em portugues", '
            f'"criteria": {{"gancho": 0-25, "emocao": 0-25, "compartilhamento": 0-25, "autonomia": 0-25}}, '
            f'"reason": "justificativa curta", "publish": true ou false}}\n\nTranscricao:\n' + "\n".join(lines)
        )
        if provider == 'openai':
            from openai import OpenAI
            client = OpenAI(api_key=key, timeout=60, max_retries=1)
            response = client.responses.create(model=C.OPENAI_MODEL, input=prompt, max_output_tokens=2500,
                                               reasoning={'effort': 'low'},
                                               text={'format': {'type': 'json_object'}}, store=False)
            if response.status != 'completed':
                raise ValueError('Resposta OpenAI incompleta')
            text = response.output_text
            model = C.OPENAI_MODEL
        elif provider == 'anthropic':
            import anthropic
            client = anthropic.Anthropic(api_key=key, timeout=60, max_retries=1)
            msg = client.messages.create(model=C.LLM_MODEL, max_tokens=1000,
                                         messages=[{"role": "user", "content": prompt}])
            text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
            model = C.LLM_MODEL
        else:
            raise ValueError('Provedor de IA invalido')
        d = json.loads(re.search(r"\{.*\}", text, re.DOTALL).group(0))
        if not isinstance(d.get('title'), str) or not d['title'].strip() or len(d['title']) > 160:
            raise ValueError('Titulo invalido')
        if type(d.get('publish')) is not bool:
            raise ValueError('Indicacao de publicacao invalida')
        criteria = d.get('criteria')
        if not isinstance(criteria, dict) or set(criteria) != {'gancho', 'emocao', 'compartilhamento', 'autonomia'}:
            raise ValueError('Criterios incompletos')
        if any(type(value) is not int or not 0 <= value <= 25 for value in criteria.values()):
            raise ValueError('Pontuacao de criterio invalida')
        if not isinstance(d.get('reason'), str) or not d['reason'].strip() or len(d['reason']) > 1000:
            raise ValueError('Justificativa invalida')
        d['score'] = sum(criteria.values())
        d['rubric_version'] = 2
        d['suggested_start'], d['suggested_end'] = float(d['start']), float(d['end'])
        d['method'] = 'ia'
        d['provider'] = provider
        d['model'] = model
        return _clamp(d, duration, min_len, max_len)
    except Exception as e:
        log.warning("Analise %s falhou (%s); usando pausas", provider, type(e).__name__)
        return fallback
