import pytest
from ocrbench.metrics import quality, application, match_regions, edit_distance

def region(text, x=0, y=0, confidence=.9, language="en", ignore=False):
    return {"text":text,"polygon":[[x,y],[x+10,y],[x+10,y+10],[x,y+10]],"confidence":confidence,"language":language,"ignore":ignore}

def ann(*regions):
    return {"reviewed":True,"complete":True,"regions":list(regions)}

def test_perfect_unicode():
    q=quality(ann(region('電話 68%')), [region('電話 68%')])
    assert q['cer']==0 and q['e2e']['f1']==1 and q['screen_exact']

def test_draft_and_partial_have_no_accuracy():
    assert quality({**ann(region('a')),'reviewed':False},[region('a')]) is None
    assert quality({**ann(region('a')),'complete':False},[region('a')]) is None

def test_wrong_position_and_duplicate_predictions():
    q=quality(ann(region('68%')), [region('68%',100),region('68%',200)])
    assert q['detection']['recall']==0 and q['e2e']['f1']==0 and q['cer']==3
    q=quality(ann(region('68%')), [region('68%'),region('68%')])
    assert q['detection']['recall']==1 and q['detection']['precision']==.5

def test_substitution_omission_insertion():
    assert quality(ann(region('68%')),[region('69%')])['cer']==pytest.approx(1/3)
    assert quality(ann(region('68%')),[])['cer']==1
    assert quality(ann(region('1')),[region('1111')])['cer']==3

def test_empty_reference_has_negative_metrics():
    q=quality(ann(),[region('invented')])
    assert q['cer'] is None and q['negative_input'] and q['false_text_regions']==1 and q['e2e']['f1']==0

def test_ignored_regions():
    q=quality(ann(region('text'),region('unreadable',50,ignore=True)),[region('text'),region('garbage',50)])
    assert q['e2e']['f1']==1

def test_combining_marks_preserved():
    q=quality(ann(region('é')),[region('e\u0301')])
    assert q['cer']==2 and q['grapheme_error_rate']==1

def test_matching_maximizes_cardinality_before_overlap():
    # r0 overlaps both, r1 overlaps only p0 at threshold .3.
    refs=[region('a'),region('b',6)]
    preds=[region('a',2),region('b',-4)]
    assert len(match_regions(refs,preds,.3))==2

def test_label_region_and_numeric_identity():
    a={"labels":[{"text":"68%","present":True,"polygon":region('x')['polygon']}],"fields":[]}
    assert application(a,[region('68%',100)])['labels'][0]['state']=='absent'
    assert application(a,[region('69%')])['labels'][0]['correct'] is False

def test_uncertain_confidence_and_correct_negative_denominators():
    a={"labels":[{"text":"PHONE","present":True,"min_confidence":.95},{"text":"NO","present":False}]}
    out=application(a,[region('PHONE',confidence=None),region('NO')])
    assert out['uncertain']==1 and out['false_pass_rate']==1 and out['false_fail_rate']==0 and out['correct_query_coverage']==0

def test_field_preserves_raw_and_locale():
    field={"name":"value","polygon":region('x')['polygon'],"expected":"7,3%","parser":"number","decimal_separator":","}
    out=application({"fields":[field]},[region('7,3%')])['fields'][0]
    assert out['value']=='7,3' and out['unit']=='%' and out['raw']=='7,3%' and out['correct']
    out=application({"fields":[field]},[region('7.3%')])['fields'][0]
    assert out['parse_error'] and not out['correct']

def test_edit_distance_empty():
    assert edit_distance('','abc')==3 and edit_distance('abc','')==3
