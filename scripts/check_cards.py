"""Check one completed text stage and its coverage, including prior duplicates."""
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COUNTS = (200, 600, 800, 1000, 1200, 1400, 1600, 1000)
REQUIRED = {
    'schema_version', 'id', 'locale', 'sentence', 'cloze', 'answer',
    'accepted_answers', 'lemma', 'meaning', 'part_of_speech',
}
SUPPORT = {'variety', 'mode', 'pronunciation', 'grammar', 'usage'}


def words(text):
    return len(re.findall(r"[^\W_]+(?:['’][^\W_]+)*", text))


def fits(text, word_cap, char_cap):
    return words(text) <= word_cap and sum(not c.isspace() for c in text) <= char_cap


def normalized(value):
    if isinstance(value, str):
        assert value == unicodedata.normalize('NFC', value), 'Non-NFC text'
    elif isinstance(value, dict):
        for item in value.values():
            normalized(item)
    elif isinstance(value, list):
        for item in value:
            normalized(item)


def check(stage):
    assert re.fullmatch(r'0[0-7]', stage), 'Expected stage 00–07'
    index = int(stage)
    cards = json.loads((ROOT / 'cards' / 'pt-BR' / f'{stage}.json').read_text())
    assert isinstance(cards, list) and len(cards) == COUNTS[index], 'Wrong card count'
    expected = [f'pt-{stage}-{n:04d}' for n in range(1, COUNTS[index] + 1)]
    assert [r['common']['id'] for r in cards] == expected, 'Missing or unordered IDs'
    max_words, max_chars = (12, 90) if index <= 1 else (16, 120) if index == 2 else (20, 150)
    seen_ids, seen_sentences = set(), set()
    for previous in range(index):
        path = ROOT / 'cards' / 'pt-BR' / f'{previous:02d}.json'
        for card in json.loads(path.read_text()):
            seen_ids.add(card['common']['id'])
            seen_sentences.add(card['common']['sentence'])
    for card in cards:
        assert set(card) == {'common', 'language_specific'}, 'Wrong record regions'
        c, local = card['common'], card['language_specific']
        label = c['id']
        assert REQUIRED <= set(c) <= REQUIRED | {'register', 'note'}, f'{label}: common keys'
        assert type(c['schema_version']) is int and c['schema_version'] == 2, f'{label}: schema'
        assert c['locale'] == 'pt-BR', f'{label}: locale'
        for key, value in c.items():
            if key not in {'schema_version', 'accepted_answers'}:
                assert isinstance(value, str) and value.strip(), f'{label}: {key}'
        assert isinstance(c['accepted_answers'], list), f'{label}: alternatives'
        assert isinstance(local, dict) and {'variety', 'mode'} <= set(local) <= SUPPORT, f'{label}: support keys'
        assert all(isinstance(v, str) and v.strip() for v in local.values()), f'{label}: support values'
        assert local['mode'] in {'production', 'recognition'}, f'{label}: mode'
        if local['mode'] == 'production':
            assert local['variety'] == 'pt-BR', f'{label}: production variety'
        for key in ('pronunciation', 'grammar', 'usage'):
            if key in local:
                scopes = ('Target:',) if key == 'grammar' else ('Target:', 'Sentence:')
                assert local[key].startswith(scopes), f'{label}: support scope'
        if local['mode'] == 'recognition':
            assert 'usage' in local, f'{label}: recognition support'
        normalized(card)
        assert c['cloze'] == c['answer'], f'{label}: answer mismatch'
        assert c['sentence'].count(c['cloze']) == 1, f'{label}: cloze occurrence'
        assert fits(c['sentence'], max_words, max_chars), f'{label}: sentence cap'
        assert fits(c['cloze'], 5, 40), f'{label}: cloze cap'
        for answer in c['accepted_answers']:
            assert isinstance(answer, str) and answer.strip() and fits(answer, 5, 40), f'{label}: alternative cap'
        assert label not in seen_ids, f'{label}: duplicate ID'
        assert c['sentence'] not in seen_sentences, f'{label}: duplicate sentence'
        seen_ids.add(label)
        seen_sentences.add(c['sentence'])
    coverage = (ROOT / 'coverage' / 'pt-BR' / f'{stage}.md').read_text()
    blocks_text, rows_text = coverage.split('## Cards', 1)
    rows = [line.split('|')[1:-1] for line in rows_text.splitlines() if line.startswith('| pt-')]
    rows = [[cell.strip() for cell in row] for row in rows]
    assert all(len(row) == 3 and all(row) for row in rows), 'Invalid coverage row'
    assert [row[0] for row in rows] == expected, 'Coverage IDs/count/order'
    planned = {}
    for line in blocks_text.splitlines():
        if not line.startswith('| ') or 'pt-' not in line:
            continue
        cells = [c.strip() for c in line.split('|')[1:-1]]
        assert len(cells) == 5, 'Invalid block row'
        block, _, _, count, id_range = cells
        endpoints = re.findall(r'pt-\d{2}-(\d{4})', id_range)
        assert len(endpoints) == 2, f'{block}: block ID range'
        first, last = map(int, endpoints)
        assert last - first + 1 == int(count), f'{block}: count/range mismatch'
        assert block not in planned, f'{block}: duplicate block'
        planned[block] = (int(count), first, last)
    assert planned and sum(v[0] for v in planned.values()) == len(cards), 'Block totals'
    actual = Counter(row[1] for row in rows)
    assert actual == Counter({block: v[0] for block, v in planned.items()}), 'Block allocations'
    for card_id, block, _ in rows:
        _, first, last = planned[block]
        assert first <= int(card_id[-4:]) <= last, f'{card_id}: wrong block'
    print(f'PASS: stage {stage}; content structure, exact IDs/counts, caps, coverage and duplicates.')


if __name__ == '__main__':
    check(sys.argv[1])
