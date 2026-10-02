# Report tables: pilot-20261001T170632Z

432 calls.

## Accuracy per representation

| representation | READ (calls) | ACT (calls) | READ tasks correct in all repeats | ACT tasks correct in all repeats |
|---|---|---|---|---|
| raw_html | 34/45 (76%, 95% CI 61%–86%) | 15/27 (56%, 95% CI 37%–72%) | 11/15 | 5/9 |
| markdown | 21/45 (47%, 95% CI 33%–61%) | 12/27 (44%, 95% CI 28%–63%) | 7/15 | 4/9 |
| accessibility_tree | 30/45 (67%, 95% CI 52%–79%) | 18/27 (67%, 95% CI 48%–81%) | 10/15 | 6/9 |
| indexed_dom | 39/45 (87%, 95% CI 74%–94%) | 27/27 (100%, 95% CI 88%–100%) | 13/15 | 9/9 |
| stagehand_snapshot | 41/45 (91%, 95% CI 79%–96%) | 27/27 (100%, 95% CI 88%–100%) | 13/15 | 9/9 |
| screenshot | 36/45 (80%, 95% CI 66%–89%) | 21/27 (78%, 95% CI 59%–89%) | 12/15 | 7/9 |

## Accuracy by location tag (calls correct / calls)

| representation | above_fold | attribute_only | below_fold | far_below_fold | iframe_cross_site | iframe_same_origin | shadow_closed |
|---|---|---|---|---|---|---|---|
| raw_html | 21/21 | 15/15 | 6/9 | 6/6 | 0/6 | 0/6 | 1/9 |
| markdown | 15/21 | 3/15 | 9/9 | 6/6 | 0/6 | 0/6 | 0/9 |
| accessibility_tree | 21/21 | 12/15 | 9/9 | 6/6 | 0/6 | 0/6 | 0/9 |
| indexed_dom | 21/21 | 9/15 | 9/9 | 6/6 | 6/6 | 6/6 | 9/9 |
| stagehand_snapshot | 21/21 | 12/15 | 9/9 | 6/6 | 5/6 | 6/6 | 9/9 |
| screenshot | 21/21 | 12/15 | 3/9 | 0/6 | 6/6 | 6/6 | 9/9 |

## Failure reasons

- **raw_html**: not representable 15, ambiguous 3, malformed_json 3, no_answer 2
- **markdown**: not representable 30, no_answer 6, wrong_answer 3
- **accessibility_tree**: not representable 21, no_answer 3
- **indexed_dom**: no_answer 5, malformed_json 1
- **stagehand_snapshot**: no_answer 3, wrong_answer 1
- **screenshot**: no_answer 9, not representable 6

## Sensitivity (NOT the pre-registered score): docs.act.3

Pre-registered target: the `<select id=version>`. Counting an answer that resolved to its `<option>3.1</option>` as correct instead would change ACT totals as follows:

- raw_html: 15/27 → 15/27
- markdown: 12/27 → 12/27
- accessibility_tree: 18/27 → 18/27
- indexed_dom: 27/27 → 27/27
- stagehand_snapshot: 27/27 → 27/27
- screenshot: 21/27 → 21/27
