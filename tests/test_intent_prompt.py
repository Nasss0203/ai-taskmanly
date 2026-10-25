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
