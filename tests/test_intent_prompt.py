import json

from app.modules.intent.prompts.intent_prompt import build_intent_prompt
from app.modules.intent.schemas.intent_schema import IntentExtraction, IntentRequest


def test_few_shot_outputs_are_actual_json_matching_the_strict_contract():
    system, _ = build_intent_prompt(IntentRequest(instruction='Classify this request'))
    examples = [json.loads(line) for line in system.splitlines() if line.startswith('{')]
    assert examples, 'Examples must demonstrate JSON null, not slash-separated labels.'
    results = [IntentExtraction.model_validate(example['output']) for example in examples]
    assert {item.intent for item in results} == {'CREATE_PAGE', 'MODIFY_PAGE', 'WRITING', 'OTHER', 'UNCLEAR'}
    assert {item.writingAction for item in results if item.intent == 'WRITING'} == {
        'IMPROVE', 'SHORTEN', 'EXPAND', 'SUMMARIZE', 'CONTINUE', 'TRANSLATE',
    }
    for example in examples:
        assert set(example['output']) == {'intent', 'writingAction', 'language'}


def examples() -> list[dict]:
    system, _ = build_intent_prompt(IntentRequest(instruction='x'))
    return [json.loads(line) for line in system.splitlines() if line.startswith('{')]


def test_vietnamese_examples_need_no_quotes_or_colons():
    vietnamese = [item['instruction'] for item in examples() if any(ord(char) > 127 for char in item['instruction'])]
    assert vietnamese and all('"' not in text and ':' not in text for text in vietnamese)


def test_examples_show_everyday_vietnamese_ways_of_asking():
    found = {(item['output']['intent'], item.get('hasSelection', False)) for item in examples()
             if any(ord(char) > 127 for char in item['instruction'])}
    by_intent = {}
    for item in examples():
        by_intent.setdefault(item['output']['intent'], []).append(item['instruction'])
    assert any(text.startswith(('trang mới', 'mình cần trang')) for text in by_intent['CREATE_PAGE'])
    assert any(',' in text and not text.lower().startswith(('thêm', 'ở trang')) for text in by_intent['MODIFY_PAGE'])
    assert any(text.lower().startswith('ở trang') for text in by_intent['MODIFY_PAGE'])
    assert ('WRITING', True) in found


def test_examples_are_not_evaluation_sentences():
    from evaluation.natural_vi_dev2_forms import BANK
    from evaluation.natural_vi_generator import DEV_BANK, DEV_SEED, generate
    from scripts.evaluate_natural_vi import DEV2_SEED

    sentences = {case['instruction'].casefold() for bank, seed in ((DEV_BANK, DEV_SEED), (BANK, DEV2_SEED))
                 for cases in generate(bank, seed).values() for case in cases}
    assert not {item['instruction'].casefold() for item in examples()} & sentences
