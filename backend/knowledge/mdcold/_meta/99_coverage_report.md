---
title: Coverage Report – mdcoldservices.com Knowledge Base
category: other
source_urls: [https://mdcoldservices.com/sitemap_index.xml, https://mdcoldservices.com/page-sitemap.xml, https://mdcoldservices.com/post-sitemap.xml, https://mdcoldservices.com/robots.txt]
last_scraped: 2026-10-14
---

# Coverage Report – mdcoldservices.com

## 1. How pages were discovered
- robots.txt (Yoast): allows everything. It points to /sitemap_index.xml.
- sitemap_index.xml points to page-sitemap.xml (21 URLs) and post-sitemap.xml (1 URL).
- Internal links were collected from the nav, dropdowns, footer and in-page buttons. These found 1 extra URL (/florida-keys-monroe/) and 2 footer links without addresses (Privacy Policy, Terms of Service).

## 2. Every URL crawled and where its content went
| URL | Status | Went into |
|---|---|---|
| https://mdcoldservices.com/ | OK | 00, 01, 04_products/hvac-brands, 05, 08, 09 |
| /about/ | OK | 00, 02, 07, 09 |
| /services/ | OK | 00, 04_products/hvac-brands |
| /services/residential-hvac/ | OK | 03_services/* (summaries), 05 |
| /services/residential-hvac/ac-repair/ | OK | 03_services/ac-repair, 02, 05, 06, 10 |
| /services/residential-hvac/ac-installation-replacement/ | OK | 03_services/ac-installation-replacement, 06, 07 |
| /services/residential-hvac/ductwork-services/ | OK | 03_services/ductwork-services, 06 |
| /services/residential-hvac/mini-split-systems/ | OK | 03_services/mini-split-systems, 06 |
| /services/residential-hvac/heat-pump-services/ | OK | 03_services/heat-pump-services, 06 |
| /services/residential-hvac/attic-insulation/ | OK | 03_services/attic-insulation, 06 |
| /services/commercial-hvac/ | OK | 03_services/commercial-hvac, 05, 06 |
| /maintenance-plans/ | OK | 05, 07, 03_services/commercial-hvac |
| /financing/ | OK | 08 |
| /service-areas/ | OK | 01 |
| /miami-dade-county/ | OK | 01 |
| /broward-county/ | OK | 01 |
| /upper-florida-keys/ | OK | 01 |
| /reviews/ | OK | 09 |
| /gallery/ | OK (failed on first try, loaded on retry) | 09 |
| /contact/ | OK | 01, 08 |
| /service-request-thank-you/ | OK | 08 |
| /hello-world/ | OK, default WordPress placeholder post ("Hello world!", 5 Aug 2026), no business content | not used |
| /florida-keys-monroe/ | FAILED (error on 3 tries) | — |
| Privacy Policy (footer) | NOT FOUND: link has no URL; /privacy-policy/ errors | — |
| Terms of Service (footer) | NOT FOUND: link has no URL; /terms-of-service/ errors | — |

**External links noted (not crawled as site content):**
- Housecall Pro booking: https://book.housecallpro.com/book/MD-Cold-Services/40f25dd932f94ff4bbe5c0b1277c4c04?v2=true. The page renders by JavaScript and its content could not be read.
- Synchrony application: https://www.synchrony.com/mmc/S6244611107?sitecode=acewel401
- Ygrene: https://ygrene.com/
- Google listing: https://share.google/ipCDZMg7jM0AeuilK
- Facebook, Instagram and TikTok: "MD Air Conditioning" profiles (see 01).

## 3. Pages or content that could not be read
- **/florida-keys-monroe/**: the footer "Key Largo & Islamorada" link and the Service Areas page's "Upper Florida Keys" link both point here, and it fails to load. The nav uses /upper-florida-keys/, which works. **This is likely a broken link on the client's site.**
- **Privacy Policy and Terms of Service**: shown in the footer but with no working link. Their content is missing from the knowledge base.
- **Contact form**: the Contact page refers to a contact form, but its fields could not be read. It is likely rendered by a script or not present.
- **Housecall Pro booking page**: JavaScript-only, so its booking services, slots and policies are unknown.
- **Homepage stat counters**: "Years of Experience", "Counties Served", "Average Google Rating" and "Satisfaction Guarantee" all render as "0". These are animated counters, and the real values could not be read. The values were taken from the About page instead (16+, 5.0, 100%). "Counties served" is likely 3.
- **Google reviews**: loaded live from Google, so no review text was captured.
- **Accuracy note**: the extraction tool returns long passages as close paraphrases rather than verbatim text. Every number, price, phone number, email, license, plan benefit, list item and FAQ question is exact. Some longer FAQ answers and descriptions in 06_faqs.md are faithful paraphrases. Spot-check against the live pages if word-for-word answers matter.

## 4. Information customers will ask about that is NOT on the website
- Regular business hours, weekend hours and holiday hours (only "24/7 emergency" is stated)
- Amount of the after-hours, emergency or weekend surcharge
- Prices for repairs, new AC systems, mini-splits, heat pumps, ductwork and attic insulation
- Accepted payment methods
- Financing APR, terms, minimums and credit requirements
- Warranty lengths and any labor/workmanship warranty
- What the "100% Satisfaction Guarantee" covers
- Cancellation, rescheduling and refund policies
- Maintenance plan contract length, auto-renewal and cancellation
- End date of the $99 "Limited-Time Offer"
- Guaranteed arrival or response times, and the response time for contact-form requests
- Street address (only "Miami, FL 33176")
- Trip fees for the Keys or far areas
- ZIP codes served
- Team or owner names, founding year
- Number of Google reviews
- Details of "Humidity Control & Filtration" or indoor air quality products

## 5. Contradictions and inconsistencies found
1. **Upper Florida Keys page URL:** the nav links to /upper-florida-keys/ (works), while the footer and Service Areas page link to /florida-keys-monroe/ (broken).
2. **Thermostat wording in maintenance plans:** the homepage plan teaser says "thermostat calibration". The Maintenance Plans page says "thermostat operation check". The knowledge base uses the Maintenance Plans page wording. Sources: https://mdcoldservices.com/ and https://mdcoldservices.com/maintenance-plans/
3. **Attic insulation, residential or commercial:** the Attic Insulation page says the service is for "residential properties", but its "Why Choose" list says "Residential & Commercial". Source: /services/residential-hvac/attic-insulation/
4. **AC Repair "Limited-Time Offer":** the $99 price is labelled a limited-time offer with $129 struck through. The Residential HVAC page and the AC Repair FAQ state $99 with no time limit. Sources: /services/residential-hvac/ac-repair/ and /services/residential-hvac/
5. **Brand name:** the website brand is "MD Cold Services", but the social profiles and the Facebook publisher tag use "MD Air Conditioning".
6. **Marathon listed under "Upper Florida Keys":** geographically Marathon is in the Middle Keys. This is not a site contradiction, just a note.
7. **Different service-area lists:** the Service Areas page lists fewer cities than the county pages. For example, the Service Areas page names 5 Broward cities, while the Broward page names 11. These lists are not contradictory; the county pages are the fuller lists.

## 6. Recommended chatbot fallback (not website content)
When a fact is "Not stated on website", the chatbot should say so and offer the 24/7 line (786) 797-6193, online booking, or email mdcoldservices@gmail.com. For emergency signs (no cooling, water leaking, burning smell, electrical issues), the chatbot should tell the customer to call (786) 797-6193 immediately.

## 7. Thirty customer test questions for retrieval evaluation
| # | Question | Correct answer | Source doc |
|---|---|---|---|
| 1 | What's your phone number? | (786) 797-6193 (24/7 line) | 01_contact_and_locations.md |
| 2 | Do you have an email? | mdcoldservices@gmail.com | 01_contact_and_locations.md |
| 3 | Are you open 24/7? | Emergency HVAC service is 24/7. Regular business hours are not stated. | 02_hours.md |
| 4 | How much is it for someone to come look at my AC? | $99 residential AC diagnostic, waived if you complete the repair with MD Cold. After-hours/emergency charges may apply. | 03_services/ac-repair.md, 05_pricing.md |
| 5 | Is the diagnostic fee refunded if I do the repair? | Yes, the $99 diagnostic fee is waived if the recommended repair is completed with MD Cold Services. | 03_services/ac-repair.md |
| 6 | Do you charge extra at night or on weekends? | Additional charges may apply for after-hours/emergency service. After-hours and weekend pricing applies. Amounts not stated. | 02_hours.md |
| 7 | Do you service Pembroke Pines? | Yes (Broward County). | 01_contact_and_locations.md |
| 8 | Do you come to Key Largo? | Yes (Upper Florida Keys). | 01_contact_and_locations.md |
| 9 | Do you serve Boca Raton? | Not listed. Call (786) 797-6193 to confirm. | 01_contact_and_locations.md |
| 10 | What's your license number? | Florida State License #CAC1824837, licensed and insured. | 00_business_overview.md, 07_policies.md |
| 11 | How long have you been in business? | 16+ years of HVAC experience. | 00_business_overview.md |
| 12 | What maintenance plans do you have? | Essential $179/yr, Premium $279/yr (most popular), Elite $379/yr. | 05_pricing.md |
| 13 | How many visits does the Premium plan include? | 2 per year (spring and fall). | 05_pricing.md |
| 14 | What discount do Elite members get on repairs? | 15% on qualifying parts and labor. | 05_pricing.md |
| 15 | I have two AC units, how much for the Essential plan? | $179/year for the first plus $150/year for the second (same location) = $329/year. | 05_pricing.md |
| 16 | Does the Elite plan include filters? | Yes, standard disposable filters only. Specialty, media, electronic and UV filters are excluded. | 05_pricing.md |
| 17 | What does the 15-point inspection check? | Blower motor, electrical connections, capacitor, contactor, voltage/amperage, filter, temperature differential, evaporator coil, condenser coil, condensate drain, thermostat, compressor, refrigerant pressures, performance evaluation, safety controls. | 05_pricing.md |
| 18 | Do you offer financing? | Yes: Synchrony (primary), Ygrene (PACE) and Wisetack, subject to approval. | 08_booking_and_payment.md |
| 19 | How long can Ygrene financing last? | Up to 20 years, repaid through an assessment on the property. | 08_booking_and_payment.md |
| 20 | What's the interest rate on financing? | Not stated on website. | 08_booking_and_payment.md |
| 21 | Is the estimate for a new AC free? | Yes, free in-home replacement estimates. | 03_services/ac-installation-replacement.md |
| 22 | How much does a new AC system cost? | Not stated. Free in-home estimate. Elite members get 5% off up to $500. | 05_pricing.md |
| 23 | Which brands do you work with? | Rheem, Lennox, Trane, Daikin, Carrier, Goodman, Mitsubishi, and others. | 04_products/hvac-brands.md |
| 24 | Do you install mini splits in garages? | Yes. Mini-splits suit additions, garages, individual rooms and offices. | 03_services/mini-split-systems.md, 06_faqs.md |
| 25 | What's the difference between single-zone and multi-zone? | Single-zone: one indoor unit for one area. Multi-zone: multiple indoor units for several areas. | 06_faqs.md |
| 26 | How do I know my ducts are leaking? | Weak airflow, uneven temperatures, excess dust, visible damage, high bills, trouble staying comfortable. | 06_faqs.md |
| 27 | Do you work on rooftop units for restaurants? | Yes. RTU diagnostics, repair, economizer service, replacement with crane coordination, maintenance. | 03_services/commercial-hvac.md |
| 28 | Do you service VRF systems? | Yes, VRF/VRV including Daikin and Mitsubishi. | 03_services/commercial-hvac.md |
| 29 | How much is a commercial service call? | Varies by equipment type and scope. Pricing confirmed before dispatch. | 03_services/commercial-hvac.md |
| 30 | What's your cancellation policy? | Not stated on website. Contact (786) 797-6193. | 07_policies.md |

## 8. Final check
Each page was re-checked against the documents. All services are covered:
- 6 residential services
- 4 commercial categories plus commercial maintenance agreements
- 3 maintenance plans with all benefits, footnotes and add-on prices
- the $99/$129 diagnostic
- 3 financing partners and the 4 financing steps
- 29 FAQs (5 AC repair, 4 installation, 4 ductwork, 4 mini-split, 4 heat pump, 4 attic insulation, 4 commercial)
- all contact details: phone, email, ZIP, socials, booking link, license
- 36 named service-area cities (21 Miami-Dade, 11 Broward, 4 Keys)

The gaps are limited to the unreadable items in section 3.
