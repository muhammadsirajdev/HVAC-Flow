# RAG evaluation report

Dataset: `tests/rag/dataset_eval.json` (51 items: 40 answerable, 11 unanswerable). Chat model `gpt-4.1-mini`, judge `gpt-4.1`, embeddings `text-embedding-3-large`, top-k 6, KB_MIN_SCORE 0.2.

## Scorecard

| Metric | Score | Meaning |
|---|---|---|
| Routing: goes to the knowledge base | 98% | classifier picks intent=question |
| Retrieval: source hit@k | 100% | an expected source file is in the top-k |
| Retrieval: source recall | 98% | share of expected source files retrieved |
| Retrieval: MRR | 0.846 | 1/rank of the first relevant chunk |
| Retrieval: fact recall | 98% | must-include facts present in the passages used |
| Retrieval: nothing above threshold | 0% | lower is better |
| Answer: must-include facts | 97% | exact facts present in the answer |
| Answer: correctness (judge) | 99% | vs reference answer |
| Answer: faithfulness (judge) | 98% | no claims beyond the passages |
| Answer: false refusals | 0% | said 'not sure' although answerable; lower is better |
| Abstention: correct refusals | 100% | unanswerable items handled without inventing |
| Abstention: invented facts | 0% | lower is better |
| Latency p50 / p95 | 2959 ms / 4488 ms | classifier + search + answer |

## By category

| Group | n | hit@k | facts | correct | abstain | faithful |
|---|---|---|---|---|---|---|
| abstain | 11 | — | — | — | 100% | 100% |
| booking | 1 | 100% | 100% | 100% | — | 100% |
| contact | 3 | 100% | 100% | 100% | — | 100% |
| emergency | 1 | 100% | 100% | 100% | — | 100% |
| faq | 2 | 100% | 100% | 100% | — | 100% |
| financing | 3 | 100% | 83% | 100% | — | 100% |
| hours | 1 | 100% | 100% | 100% | — | 100% |
| pricing | 15 | 100% | 98% | 97% | — | 93% |
| product | 1 | 100% | 100% | 100% | — | 100% |
| service | 4 | 100% | 88% | 100% | — | 100% |
| service_area | 4 | 100% | 100% | 100% | — | 100% |
| troubleshooting | 1 | 100% | 100% | 100% | — | 100% |
| trust | 4 | 100% | 100% | 100% | — | 100% |

## By question style

| Group | n | hit@k | facts | correct | abstain | faithful |
|---|---|---|---|---|---|---|
| plain | 35 | 100% | 97% | 98% | 100% | 97% |
| roman_urdu | 5 | 100% | 100% | 100% | 100% | 100% |
| symptom | 2 | 100% | 100% | 100% | — | 100% |
| typo | 9 | 100% | 93% | 100% | 100% | 100% |

## Multi-chunk

| Group | n | hit@k | facts | correct | abstain | faithful |
|---|---|---|---|---|---|---|
| False | 46 | 100% | 98% | 99% | 100% | 98% |
| True | 5 | 100% | 90% | 100% | — | 100% |

## Failures (3)

### q06 · pricing · plain — What maintenance plans do you offer?

- route: `question`
- search query: What maintenance plans do you offer?
- retrieved: policy_maintenance-plan-terms_1 (0.54), plan_commercial-maintenance-agreements_1 (0.53), plan_premium-comfort-plan_1 (0.50), plan_essential-comfort-plan_1 (0.49), faq_do-you-offer-preventive-maintenance-for-commerci_1 (0.48), booking_commercial-maintenance-consultation-requests_1 (0.40)
- answer: We offer two residential maintenance plans: the Premium Comfort Plan at $279/year for one system (additional systems $175/year) with two preventive visits per year, and the Essential Comfort Plan at $179/year for one system (additional systems $150/year) with one preventive visit per year. Both include a 15-point HVAC inspection, filter and thermostat checks, condensate drain service, system performance evaluation, priority scheduling, and a 10% discount on qualifying repairs. For commercial systems, we provide customized maintenance agreements—please request a consultation via our website.
- correctness 0.5 · faithful False · missing facts ['$379'] · unsupported ['We offer two residential maintenance plans (the reference lists three)', 'Both plans include a 15-point HVAC inspection, filter and thermostat checks, condensate drain service, system performance evaluation, priority scheduling, and a 10% discount on qualifying repairs (the Elite Comfort Plan is omitted and its features are not described)']
- judge: The answer omits the Elite Comfort Plan, which is listed in the reference, and thus does not fully match the reference or passages.

### q33 · service · plain — Do you work on Daikin VRF systems?

- route: `question`
- search query: Do you work on Daikin VRF systems?
- retrieved: service_commercial-vrf-vrv-system-services_1 (0.61), faq_what-types-of-commercial-hvac-systems-do-you-ser_1 (0.51), brands_hvac-brands-serviced-and-installed_1 (0.49), overview_commercial-hvac-services-offered_1 (0.47), faq_do-you-install-energy-efficient-ac-systems_1 (0.47), service_commercial-hvac-services-overview_1 (0.44)
- answer: Yes, MD Cold Services installs, diagnoses, repairs, and maintains Daikin VRF/VRV multi-zone systems. You can call (786) 797-6193 for service or to book a visit.
- correctness 1.0 · faithful True · missing facts ['Mitsubishi']
- judge: The answer correctly states that MD Cold Services works on Daikin VRF/VRV systems, matching the reference and supported by the passages.

### q40 · financing · typo — i want a new ac in key largo can i pay monthly

- route: `question`
- search query: Can I pay monthly for a new AC installation in Key Largo? | Do you offer AC installation services in Key Largo?
- retrieved: service_ac-installation-replacement-service-overview_1 (0.60), service_ac-repair-service-coverage_1 (0.60), service_area_upper-florida-keys-service-areas_1 (0.60), faq_do-you-offer-financing-for-a-new-ac-system_1 (0.59), policy_ac-installation-financing-policy_1 (0.56), overview_business-overview_1 (0.54)
- answer: Yes, you can pay monthly for a new AC installation in Key Largo. MD Cold Services offers financing for qualified customers through Synchrony, Ygrene, and Wisetack, subject to approval. Key Largo is in the Upper Florida Keys service area. If you'd like, I can help you get started!
- correctness 1.0 · faithful True · missing facts ['free']
- judge: The answer correctly states that monthly payments (financing) are available for new AC installations in Key Largo, lists the financing partners, and confirms Key Largo is in the service area, all supported by the passages.
