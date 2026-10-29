"""Position-based adapter for the two observed weekly layouts, not general OCR.

All assembled strings derive from actual OCR words. Original evidence is linked
by word IDs and retained separately. No replacement of recognized numbers.
"""
import json
import re
from pathlib import Path
from flyer_parser import parse, TIME


def bounds(words):
    left = min(w['bbox'][0] for w in words)
    top = min(w['bbox'][1] for w in words)
    return [left, top, max(w['bbox'][0]+w['bbox'][2] for w in words)-left,
            max(w['bbox'][1]+w['bbox'][3] for w in words)-top]


def adapt(ocr):
    width, height = ocr['width'], ocr['height']
    groups = {}
    for line in ocr['lines']:
        for i, word in enumerate(line['words']):
            word = dict(word, evidence_id=f"{line['id']}:word-{i}")
            x, y, w, h = word['bbox']
            cx, cy = (x+w/2)/width, (y+h/2)/height
            if cy < .12:
                region = 'header'
            elif .13 < cy < .375:
                region = ('top_left' if cx < .35 else 'top_middle' if cx < .66 else 'top_right')
            elif .55 < cy < .68:
                region = 'sunday_block' if cx < .5 else 'weekday_block'
            elif .68 <= cy < .73:
                region = 'shiurim'
            elif cy >= .73:
                region = 'unstructured_lower_left' if cx < .35 else 'unstructured_lower_middle' if cx < .67 else 'unstructured_lower_right'
            else:
                region = 'other'
            groups.setdefault(region, []).append(word)
    assembled = []
    for region, words in groups.items():
        rows = []
        for word in sorted(words, key=lambda w: w['bbox'][1]+w['bbox'][3]/2):
            cy = word['bbox'][1]+word['bbox'][3]/2
            if not rows or abs(cy-rows[-1][0]) > .007 * height:
                rows.append((cy, [word]))
            else:
                rows[-1][1].append(word)
        region_lines = []
        for _, row in rows:
            row.sort(key=lambda w: w['bbox'][0])
            text = ' '.join(w['text'] for w in row)
            # The observed Hilchot label wraps above its time. Only join this
            # exact label and a following time-only row in the same region.
            if (region_lines and re.fullmatch(r'\s*\d{1,2}:\d{2}\s*[AP]M\s*', text)
                    and region_lines[-1]['text'].upper() == 'HILCHOT SHABBAT'):
                prior = region_lines[-1]
                row = prior.pop('_words') + row
                text = prior['text'] + ' ' + text
                region_lines.pop()
            region_lines.append({'id': f'layout-{len(assembled)}-{len(region_lines)}', 'region': region,
                                 'text': text, 'bbox': bounds(row), '_words': row,
                                 'source_word_ids': [w['evidence_id'] for w in row]})
        assembled.extend(region_lines)
    for line in assembled:
        line.pop('_words')
    doc = {'document_id': ocr['source_sha256'], 'input_kind': 'local_ocr', 'lines': assembled}
    result = parse(doc)
    result['layout_provenance'] = {'adapter': 'observed_weekly_normalized_regions_v1',
                                 'coordinate_space': ocr['coordinate_space'],
                                 'source_sha256': ocr['source_sha256'], 'width': width, 'height': height,
                                 'engine': ocr['engine'], 'language': ocr['language'],
                                 'limitations': ['regions fitted to two examples', 'lower shiurim not fully structured', 'all outputs require review']}
    return doc, result


if __name__ == '__main__':
    import sys
    folder = Path(sys.argv[1])
    for path in sorted(folder.glob('*.ocr.json')):
        doc, result = adapt(json.loads(path.read_text(encoding='utf-8')))
        path.with_suffix('.layout.json').write_text(json.dumps(doc, indent=2), encoding='utf-8')
        path.with_suffix('.extraction.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(path.name, result['classification'], len(result['entries']), 'entries')
