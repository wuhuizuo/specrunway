#!/usr/bin/env python3
"""Check the initial handoff structure, not product behavior or post-archive CI."""
from pathlib import Path
import json, re, sys

root = Path(__file__).resolve().parents[1]
active = sorted((root/'openspec/changes').glob('[0-9][0-9]-*'))
archived = sorted((root/'openspec/changes/archive').glob('*-[0-9][0-9]-*'))
changes = active + archived
expected = {'01','02','03','04','05'}
covered = set()
for change in changes:
    found = re.findall(r'(?:^|-)(\d{2})-', change.name)
    covered.update(value for value in found if value in expected)
assert covered == expected, f'Implementation change coverage incomplete: {sorted(covered)}'
seen = set()
requirements = scenarios = task_count = 0
for change in changes:
    required = ['proposal.md','design.md','tasks.md']
    if change in active:
        required.insert(0, '.openspec.yaml')
    for filename in required:
        assert (change/filename).is_file(), f'Missing {change.name}/{filename}'
    task_text = (change/'tasks.md').read_text()
    tasks = re.findall(r'^- \[([ xX])\] (\d+\.\d+) \[(L\d{2})\] (.+)$',task_text,re.M)
    assert tasks, f'No tracked source-linked tasks in {change.name}'
    assert len({t[1] for t in tasks}) == len(tasks), 'Duplicate task checkbox IDs'
    for marker,checkbox,source,description in tasks:
        seen.add(source); task_count += 1
        assert re.search(r'\bverify\b',description,re.I), f'No verification in {source}/{checkbox}'
    declared = set(re.findall(r'^- `([a-z0-9-]+)`: ',(change/'proposal.md').read_text(),re.M))
    specs = list((change/'specs').glob('*/spec.md'))
    assert declared == {p.parent.name for p in specs}, 'Proposal/spec capability mismatch'
    for spec in specs:
        text = spec.read_text()
        purpose = re.search(r'^## Purpose\s+(.+?)(?=^## )',text,re.M|re.S)
        assert purpose and len(purpose.group(1).strip())>=50, f'Short purpose in {spec}'
        blocks = re.split(r'^### Requirement: ',text,flags=re.M)[1:]
        assert blocks
        for block in blocks:
            head,body = block.split('\n',1)
            description = body.split('#### Scenario:',1)[0].strip()
            assert re.search(r'\b(SHALL|MUST)\b',description), f'Non-normative requirement: {head}'
            assert len(description)<=500, f'Overlong requirement: {head}'
            parts = re.split(r'^#### Scenario: ',body,flags=re.M)[1:]
            assert parts, f'No scenario: {head}'
            for part in parts:
                assert '- **WHEN** ' in part and '- **THEN** ' in part
            requirements += 1; scenarios += len(parts)
assert seen == {f'L{i:02d}' for i in range(1,16)}, f'Incorrect required source IDs: {seen}'
for p in root.rglob('*'):
    if not p.is_file() or any(x in p.parts for x in ['node_modules','.venv','.git']): continue
    if p.suffix in ['.md','.yaml','.json','.sh','.py']:
        assert not re.search(r'[\u3400-\u9fff]',p.read_text()), f'Non-English content in {p}'
print(json.dumps({'changes':len(changes),'active':len(active),'archived':len(archived),
                  'source_tasks':len(seen),'checkbox_tasks':task_count,
                  'requirements':requirements,'scenarios':scenarios,'result':'passed'}))
