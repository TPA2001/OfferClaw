# Agent 自动化评测报告

- 生成时间: 2026-08-31 19:42:45
- 数据集: 1 个类别 / 20 条用例
- 整体工具准确率: **35.00%**
- 闸门阈值: 85%  →  **❌ FAIL**

## 按类别
| 类别 | 用例数 | 正确数 | 准确率 |
|---|---:|---:|---:|
| 岗位推荐 | 20 | 7 | 35.0% |

## 用例明细
| ID | 类别 | 期望工具 | 实际工具 | 结果 | 延迟(ms) |
|---|---|---|---|---|---|
| jobrec_01 | 岗位推荐 | `evaluate_job` | evaluate_job | ✅ | 36 |
| jobrec_02 | 岗位推荐 | `evaluate_job` | evaluate_job | ✅ | 4088 |
| jobrec_03 | 岗位推荐 | `verify_job_authenticity` | verify_job_authenticity | ✅ | 2298 |
| jobrec_04 | 岗位推荐 | `verify_job_authenticity` | verify_job_authenticity | ✅ | 9 |
| jobrec_05 | 岗位推荐 | `score_job_match` | get_profile | ❌ | 6 |
| jobrec_06 | 岗位推荐 | `score_job_match` | get_dashboard_stats | ❌ | 14 |
| jobrec_07 | 岗位推荐 | `evaluate_job` | evaluate_job | ✅ | 7 |
| jobrec_08 | 岗位推荐 | `search_applications` | query_applications | ❌ | 13 |
| jobrec_09 | 岗位推荐 | `get_followups` | (无) | ❌ | 4 |
| jobrec_10 | 岗位推荐 | `research_company` | (无) | ❌ | 4 |
| jobrec_11 | 岗位推荐 | `generate_resume` | get_dashboard_stats | ❌ | 8 |
| jobrec_12 | 岗位推荐 | `generate_cover_letter` | (无) | ❌ | 4 |
| jobrec_13 | 岗位推荐 | `get_timeline_stats` | evaluate_job | ❌ | 5 |
| jobrec_14 | 岗位推荐 | `verify_job_authenticity` | (无) | ❌ | 4 |
| jobrec_15 | 岗位推荐 | `evaluate_job` | evaluate_job | ✅ | 3 |
| jobrec_16 | 岗位推荐 | `get_company_stats` | get_dashboard_stats | ❌ | 2 |
| jobrec_17 | 岗位推荐 | `score_job_match` | (无) | ❌ | 2 |
| jobrec_18 | 岗位推荐 | `evaluate_job` | evaluate_job | ✅ | 2 |
| jobrec_19 | 岗位推荐 | `extract_job_description` | (无) | ❌ | 1 |
| jobrec_20 | 岗位推荐 | `get_application_advice` | (无) | ❌ | 2 |
