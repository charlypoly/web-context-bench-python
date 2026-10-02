# Report tables: full-20261002T073411Z

1440 calls.

## Accuracy per representation

| representation | READ (calls) | ACT (calls) | READ tasks correct in all repeats | ACT tasks correct in all repeats |
|---|---|---|---|---|
| raw_html | 138/150 (92%, 95% CI 87%–95%) | 71/90 (79%, 95% CI 69%–86%) | 46/50 | 23/30 |
| markdown | 120/150 (80%, 95% CI 73%–86%) | 63/90 (70%, 95% CI 60%–78%) | 40/50 | 21/30 |
| accessibility_tree | 132/150 (88%, 95% CI 82%–92%) | 75/90 (83%, 95% CI 74%–90%) | 44/50 | 25/30 |
| indexed_dom | 129/150 (86%, 95% CI 80%–91%) | 87/90 (97%, 95% CI 91%–99%) | 43/50 | 29/30 |
| stagehand_snapshot | 144/150 (96%, 95% CI 92%–98%) | 87/90 (97%, 95% CI 91%–99%) | 48/50 | 29/30 |
| screenshot | 108/150 (72%, 95% CI 64%–79%) | 66/90 (73%, 95% CI 63%–81%) | 36/50 | 22/30 |

## Accuracy by location tag (calls correct / calls)

| representation | above_fold | attribute_only | below_fold | far_below_fold | iframe_cross_site | iframe_same_origin | shadow_closed |
|---|---|---|---|---|---|---|---|
| raw_html | 125/129 | 24/24 | 33/39 | 27/27 | 0/6 | 0/6 | 0/9 |
| markdown | 111/129 | 6/24 | 39/39 | 27/27 | 0/6 | 0/6 | 0/9 |
| accessibility_tree | 123/129 | 18/24 | 39/39 | 27/27 | 0/6 | 0/6 | 0/9 |
| indexed_dom | 126/129 | 9/24 | 36/39 | 24/27 | 6/6 | 6/6 | 9/9 |
| stagehand_snapshot | 126/129 | 18/24 | 39/39 | 27/27 | 6/6 | 6/6 | 9/9 |
| screenshot | 129/129 | 21/24 | 3/39 | 0/27 | 6/6 | 6/6 | 9/9 |

## Failure reasons

- **raw_html**: not representable 15, malformed_json 7, wrong_element 3, ambiguous 3, invalid_selector 2, no_answer 1
- **markdown**: not representable 33, no_answer 18, wrong_element 3, wrong_answer 3
- **accessibility_tree**: not representable 24, no_answer 6, wrong_element 3
- **indexed_dom**: no_answer 15, not representable 3, wrong_element 3, malformed_json 3
- **stagehand_snapshot**: no_answer 6, wrong_element 3
- **screenshot**: no_answer 42, not representable 24

## Sensitivity (NOT the pre-registered score): docs.act.3

Pre-registered target: the `<select id=version>`. Counting an answer that resolved to its `<option>3.1</option>` as correct instead would change ACT totals as follows:

- raw_html: 71/90 → 74/90
- markdown: 63/90 → 66/90
- accessibility_tree: 75/90 → 78/90
- indexed_dom: 87/90 → 87/90
- stagehand_snapshot: 87/90 → 90/90
- screenshot: 66/90 → 66/90
