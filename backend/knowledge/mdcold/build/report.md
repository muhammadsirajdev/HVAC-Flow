# Knowledge-base chunk report

## 1. Chunks per category

| Category | Chunks |
|---|---|
| booking | 6 |
| brands | 1 |
| contact | 2 |
| faq | 29 |
| hours | 5 |
| other | 3 |
| overview | 8 |
| plan | 4 |
| policy | 15 |
| pricing | 9 |
| product | 1 |
| service | 24 |
| service_area | 5 |
| trust | 6 |
| **total** | **118** |

## 2. Coverage of source facts

Every price, phone number, email, URL, license number, percentage, count and FAQ question in the source documents appears in at least one chunk, and no chunk contains a value that is not in its source document.

Source lines whose words are below 85% covered by any one chunk (usually rewording; review them):

- `00_business_overview.md` (40%): MD Cold Services offers two main service lines.
- `02_hours.md` (82%): The website advertises "Same/Next-Day Service" with "Fast dispatch". Same-day service is "available when scheduling permits". Maintenance plan members get priority scheduling (see 05_pricing.md). The website gives no guaranteed arrival time.
- `03_services/ac-installation-replacement.md` (80%): - removing the existing equipment during replacements
- `03_services/ac-installation-replacement.md` (82%): Not stated on website. Replacement estimates are free and done in the home. Elite Comfort maintenance plan members get 5% off a qualifying new HVAC system replacement, up to $500 (see 05_pricing.md).
- `03_services/ac-installation-replacement.md` (75%): The website says "Manufacturer Warranty Coverage Available on Select Systems." The website does not state warranty lengths or a separate labor/workmanship warranty.
- `03_services/ac-installation-replacement.md` (64%): Financing is available for qualified customers through Synchrony, Ygrene and Wisetack, subject to approval (see 08_booking_and_payment.md).
- `03_services/ac-installation-replacement.md` (50%): AC Installation & Replacement FAQs are in 06_faqs.md.
- `03_services/ac-repair.md` (75%): - other common HVAC failures
- `03_services/ac-repair.md` (40%): AC Repair FAQs are in 06_faqs.md.
- `03_services/attic-insulation.md` (40%): Attic Insulation FAQs are in 06_faqs.md.
- `03_services/commercial-hvac.md` (75%): - "Scheduled Preventive Maintenance Agreements"
- `03_services/commercial-hvac.md` (85%): MD Cold Services handles installation, repair, replacement and preventive maintenance of packaged systems for restaurants, retail properties, offices and warehouses.
- `03_services/commercial-hvac.md` (75%): - "Preventive Maintenance & System Inspections"
- `03_services/commercial-hvac.md` (80%): - priority service / priority response times
- `03_services/commercial-hvac.md` (75%): - detailed service and inspection reports
- `03_services/commercial-hvac.md` (40%): Commercial HVAC FAQs are in 06_faqs.md.
- `03_services/ductwork-services.md` (25%): Commercial sheet-metal ductwork is covered in commercial-hvac.md. Ductwork FAQs are in 06_faqs.md.
- `03_services/heat-pump-services.md` (80%): Heat pumps provide both cooling and heating from one HVAC system. The website says this makes heat pumps well suited to South Florida's climate. MD Cold Services services major HVAC brands and can evaluate existing equipment when repair or replacement is needed.
- `03_services/heat-pump-services.md` (40%): Heat Pump FAQs are in 06_faqs.md.
- `03_services/mini-split-systems.md` (75%): - other residential or commercial spaces
- `03_services/mini-split-systems.md` (73%): The Mini Split page does not name specific mini-split brands. Daikin and Mitsubishi appear in MD Cold Services' general brand list (see 04_products/hvac-brands.md).
- `03_services/mini-split-systems.md` (40%): Mini Split FAQs are in 06_faqs.md.
- `04_products/hvac-brands.md` (50%): The homepage and Services page show logos for "Service & Installation for Industry-Leading HVAC Brands":
- `04_products/hvac-brands.md` (83%): Not stated on website. MD Cold Services supplies equipment as part of installation and replacement jobs. The website has no product catalog, model list or equipment prices.
- `05_pricing.md` (62%): All plans are billed annually. Each price covers one residential system.
- `05_pricing.md` (75%): | Scheduling priority | Priority scheduling within one business day | Next-available priority scheduling | Highest-priority scheduling |
- `05_pricing.md` (57%): | Each additional system (same location) | $150/year | $175/year | $200/year |
- `05_pricing.md` (61%): | Best for | Homeowners wanting affordable annual maintenance and basic protection | Homeowners wanting year-round maintenance, convenience and improved reliability | Homeowners wanting the highest service level, priority scheduling, maintenance and savings |
- `05_pricing.md` (80%): **Plan terms and footnotes (from the Maintenance Plans page):**
- `05_pricing.md` (80%): Commercial maintenance agreements are customized per facility and equipment. The website lists no fixed price; customers request a consultation. See 03_services/commercial-hvac.md.
- `06_faqs.md` (6%): Note: the questions are copied exactly from the site. Some longer answers were captured as close paraphrases (see 99_coverage_report.md).
- `06_faqs.md` (75%): Service: AC Installation & Replacement (MD Cold Services)
- `06_faqs.md` (75%): Service: AC Installation & Replacement (MD Cold Services)
- `06_faqs.md` (75%): Service: AC Installation & Replacement (MD Cold Services)
- `06_faqs.md` (75%): Service: AC Installation & Replacement (MD Cold Services)
- `06_faqs.md` (50%): Service: Mini Split Systems (MD Cold Services)
- `06_faqs.md` (50%): Service: Mini Split Systems (MD Cold Services)
- `06_faqs.md` (50%): Service: Mini Split Systems (MD Cold Services)
- `06_faqs.md` (50%): Service: Mini Split Systems (MD Cold Services)
- `10_other.md` (75%): The homepage lists "Humidity Control & Filtration" under "Attic Insulation & Air Quality". The website has no dedicated page and gives no details (no dehumidifier, air purifier or UV light products are described). Customers asking about indoor air quality should call (786) 797-6193.

## 3. Chunks over 450 tokens

None.

Chunks under 40 tokens (fine if the fact really is that short):

- `hours_holiday-hours_1` (28 tokens)
- `pricing_heat-pump-service-pricing_1` (34 tokens)
- `pricing_mini-split-system-price-information_1` (37 tokens)
- `policy_cancellation-and-rescheduling-policy_1` (39 tokens)
- `policy_refund-policy_1` (22 tokens)

## 4. Chunks that may be unclear on their own

- `overview_information-not-stated-on-website_1`: This chunk only lists what is missing from the website and may be unclear without context.
- `other_humidity-control-and-filtration-information_1`: Mentions a homepage category but lacks detail; unclear what services are actually offered.

## 5. Retrieval test questions

| # | Question | Expected chunk(s) |
|---|---|---|
| 1 | What areas do you serve for HVAC services? | `service_area_service-area-overview_1` |
| 2 | Do you offer 24/7 emergency AC repair? | `hours_emergency-and-after-hours-availability_1`, `faq_do-you-provide-emergency-ac-repair_1` |
| 3 | How much does an AC repair diagnostic cost? | `pricing_ac-repair-diagnostic-price_1`, `faq_how-much-is-an-ac-diagnostic-service-call_1` |
| 4 | What brands of AC do you service and install? | `brands_hvac-brands-serviced-and-installed_1`, `faq_do-you-service-all-major-ac-brands_1` |
| 5 | How can I book a service appointment? | `booking_how-to-book-a-service_1` |
| 6 | Do you offer financing for new AC systems? | `policy_ac-installation-financing-policy_1`, `faq_do-you-offer-financing-for-a-new-ac-system_1`, `policy_financing-options-overview_1` |
| 7 | What is included in your maintenance plans? | `plan_essential-comfort-plan_1`, `plan_premium-comfort-plan_1`, `plan_elite-comfort-plan_1`, `service_15-point-hvac-inspection-in-maintenance-plans_1` |
| 8 | What are your regular business hours? | `hours_regular-business-hours_1` |
| 9 | How do I contact you for urgent service? | `contact_contact-details_1` |
| 10 | Do you provide commercial HVAC services? | `overview_commercial-hvac-services-offered_1`, `service_commercial-hvac-services-overview_1`, `faq_do-you-provide-commercial-hvac-repair-and-replac_1` |
| 11 | Can you repair ductwork or does it need to be replaced? | `faq_can-ductwork-be-repaired-or-does-it-have-to-be-r_1` |
| 12 | Do you install ductless mini split systems? | `service_ductless-mini-split-systems-service-overview_1`, `faq_what-is-a-ductless-mini-split-system_1` |
| 13 | What is your satisfaction guarantee? | `policy_satisfaction-guarantee_1` |
| 14 | How do I know if my AC needs repair? | `faq_how-do-i-know-if-my-ac-needs-repair_1` |
| 15 | Do you offer attic insulation services? | `overview_attic-insulation-and-air-quality-services_1`, `service_attic-insulation-service-overview_1` |
| 16 | What payment methods do you accept? | `booking_accepted-payment-methods_1` |
| 17 | How do I get a free estimate for a new AC? | `booking_free-estimates_1`, `pricing_ac-installation-replacement-price_1` |
| 18 | Are there extra charges for after-hours or emergency service? | `hours_after-hours-and-emergency-service-charges_1`, `pricing_ac-repair-diagnostic-price_1` |
| 19 | What is your warranty policy for new AC installations? | `policy_ac-installation-warranty-policy_1`, `policy_warranty-on-equipment-and-work_1` |
| 20 | Do you offer preventive maintenance for commercial HVAC? | `plan_commercial-maintenance-agreements_1`, `faq_do-you-offer-preventive-maintenance-for-commerci_1` |
