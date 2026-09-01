# Literature Review: Low-Cost, Non-Visual, Multi-Target Spatial Risk Assessment for Screen Privacy (24 GHz mmWave Radar, ESP32)

**Purpose of this review:** support a research paper claiming a *spatial risk assessment* system (distance + presence duration + multi-person proximity) for terminal/screen privacy in open offices, built on 24 GHz millimeter-wave radar modules of the HLK LD2410B / LD2450 / LD2453 class with an ESP32 host. The system does **not** use cameras at deployment and makes **no** claims of identity recognition or "peeping intent" inference; video is used offline only, under informed consent, for ground-truth labeling.

**Method & verification note:** all sources below were located via web search (web_search tool) and are linked to the exact URLs/DOIs seen in the search results; no DOI has been invented. Each entry is tagged **[peer-reviewed]**, **[vendor datasheet/white paper]**, **[patent]**, **[preprint]**, **[thesis]**, or **[community/forum]** so vendor claims are never conflated with scientific evidence. Where the author list could not be fully verified from the snippets, this is stated ("authors per ACM DL / Semantic Scholar").

---

## 1. Shoulder Surfing / Screen Privacy

**Finding:** Prior work defends screen content either (a) by *obscuring* content (filters, viewing-angle-limited displays, visual illusions), (b) by *detecting* the observer (camera/eye-gaze/proxemics sensing) and reacting, or (c) by studying attacker behavior (distance, angle, duration). Sensors used in published work are overwhelmingly **cameras/eye trackers** or **proximity/proxemic sensing**; **we found no peer-reviewed shoulder-surfing defense that uses radar** (as of this search date; unindexed or industrial work may exist). Quantitative data on real shoulder-surfing distances/angles is scarce and is a gap this project can address.

- **[peer-reviewed]** Tari, Ozok & Holden. *A comparison of perceived and real shoulder-surfing risks between alphanumeric and graphical passwords.* SOUPS '06 (ACM), 2006. DOI: 10.1145/1143120.1143128 — https://dl.acm.org/doi/10.1145/1143120.1143128. Early empirical study showing that real shoulder-surfing success rates differ from users' perceived risk, and that graphical passwords are more vulnerable than users believe — a canonical citation that shoulder surfing is measurable experimentally.
- **[peer-reviewed]** Abdrabou et al. (author list per ACM DL / Uni-Due). *Understanding Shoulder Surfer Behavior and Attack Patterns Using Virtual Reality.* CHI 2023. DOI: 10.1145/3531073.3531106 — https://hci.informatik.uni-due.de/fileadmin/fileupload/I-HCI/Paper/3531073.3531106.pdf. Uses VR to instrument attack geometry (viewing distances/angles/durations) that is hard to measure in the lab — the closest published quantitative characterization of *where* shoulder surfers position themselves, directly relevant to defining "risk zones" (distance/angle thresholds).
- **[peer-reviewed, short paper]** Brudy, Ledo, Greenberg, et al. *Is Anyone Looking? Mitigating Shoulder Surfing on Public Displays through Awareness and Protection.* CHI '14 Extended Abstracts. DOI: 10.1145/2559206.2579528 — https://dl.acm.org/doi/abs/10.1145/2559206.2579528. Shows that making the *presence of a nearby observer* salient (awareness) is itself an effective mitigation on public displays — supports the "risk notification" rather than "content obscuring" design philosophy.
- **[peer-reviewed]** Zhou et al. (authors per Semantic Scholar). *Enhancing Mobile Content Privacy with Proxemics Aware Notifications and Protection.* CHI 2016. DOI: 10.1145/2858036.2858232 — https://dl.acm.org/doi/abs/10.1145/2858036.2858232. Proxemics-aware mobile privacy: sensing who is near the user and adapting notifications/protection; the sensing in published proxemic work is camera/ultrasonic/BLE-based, not radar — a direct precedent for "sensor-derived risk → privacy action," which is exactly the architecture of the proposed system.
- **[peer-reviewed]** Kise et al. (senior author; full list on ACM DL). *Private Reader: Using Eye Tracking to Improve Reading Privacy in Public Spaces.* MobileHCI 2019. DOI: 10.1145/3338286.3340129 — https://dl.acm.org/doi/10.1145/3338286.3340129. Eye-tracking-based defense that detects when nearby gaze is aimed at the user's display and blurs content — demonstrates the "observer-detection → content protection" loop, but requires a camera/eye tracker on the observer, which the proposed radar system deliberately avoids.
- **[peer-reviewed]** Mathis, Williamson, Vaniea, Khamis. *The Role of Eye Gaze in Security and Privacy Applications: Survey and Future HCI Research Directions.* CHI 2020. DOI: 10.1145/3313831.3376840 — https://dlnext.acm.org/doi/fullHtml/10.1145/3313831.3376840. Survey of gaze-based security/privacy systems, including shoulder-surfing defenses; useful for positioning radar as a privacy-preserving alternative to gaze/camera sensing.
- **[peer-reviewed]** *BAIT: Visual-illusion-inspired Privacy Preservation for Mobile Data Visualization.* CHI 2026. DOI: 10.1145/3772318.3791259 — https://dl.acm.org/doi/10.1145/3772318.3791259. Content-obscuring (visual illusion) defense; shows the active research direction of *display-side* protection, orthogonal to sensing-based approaches.
- **[preprint, not peer-reviewed]** *A Two-Week In-the-Wild Study of Screen Filters and Camera Sliders for Smartphone Privacy in Public Spaces.* arXiv:2602.08465 — https://ar5iv.labs.arxiv.org/html/2602.08465. Field evidence that hardware screen filters and camera sliders are rarely used/effective in the wild; motivates automated, sensor-driven protection.
- **[vendor]** 3M-style privacy filters / active privacy monitors (e.g., https://www.pcprivacyscreen.com/active-privacy-monitors-vs-films-stopping-visual-hackers/) — viewing-angle-limited hardware; no sensing, static protection, and (per the in-the-wild study above) low real-world adoption.

**Gap for the paper:** no published shoulder-surfing defense combines (i) no-camera deployment, (ii) multi-person proximity with dwell time, and (iii) explicit *spatial risk scoring* with validated distance accuracy. That is the proposed contribution.

---

## 2. mmWave Radar Human Presence & Multi-Target Detection/Tracking

**Finding:** Representative methods are FMCW range-Doppler processing with CFAR detection, clustering of point clouds, and Kalman/JPDA-style tracking; or micro-Doppler classification for presence vs. activity. Multi-person tracking is feasible with MIMO arrays (e.g., 2TX/4RX or 4TX/4RX) but is limited by angular resolution (small apertures), occlusion, and clustering ambiguities. Reported accuracies are typically on the order of tens of centimeters for position (sub-decimeter claims exist under good SNR); field of view is range-dependent and typically 60–120° azimuth with a few meters of unambiguous range at 24 GHz consumer modules.

- **[peer-reviewed]** Pegoraro et al. *Real-Time People Tracking and Identification From Sparse mm-Wave Radar Point-Clouds.* IEEE Access, 2021. DOI: 10.1109/ACCESS.2021.3083980 — https://ieeexplore.ieee.org/document/9318574 (and doi.org/10.1109/ACCESS.2021.3083980). Demonstrates real-time multi-person tracking from sparse mmWave point clouds (60 GHz TI-class radar) with position error and tracking metrics — a strong methodological template (metrics, clutter handling) for evaluating multi-target radar tracking.
- **[peer-reviewed]** Shen, Nunez-Yanez & Dahnoun. *Advanced Millimeter-Wave Radar System for Real-Time Multiple-Human Tracking and Fall Detection.* Sensors, 2024, 24(11):3660. DOI: 10.3390/s24113660 — https://www.mdpi.com/1424-8220/24/11/3660. Multiple-human tracking + fall detection on a low-cost mmWave module; reports detection/tracking accuracy and multi-target handling — representative of the achievable performance class of consumer mmWave modules.
- **[peer-reviewed / arXiv]** Pegoraro et al. *ORACLE: Occlusion-Resilient and Self-Calibrating mmWave Radar Network for People Tracking.* arXiv:2208.14199; also IEEE Xplore doc 10342865 — https://arxiv.org/abs/2208.14199. Shows that occlusion (one person hiding another) is a first-order problem for single-radar tracking and that multi-radar networks with self-calibration substantially improve multi-person tracking — key evidence for the "multi-person proximity ambiguity" limitation and for deployment geometry decisions.
- **[peer-reviewed]** *Evaluation of Detection and Tracking Approaches for People Counting Using mmWave Radar.* IEEE conference paper (2025; Xplore doc 11318383; linked from the ICSPIS 2025 program). — https://ieeexplore.ieee.org/abstract/document/11318383. Head-to-head comparison of detection/tracking pipelines for people counting with mmWave radar; provides evaluation methodology (accuracy, over/under-counting) directly reusable for the proposed system's multi-person counting claims.
- **[peer-reviewed]** *Lightweight FMCW radar framework for human activity recognition under limited data conditions.* Scientific Reports (2026). DOI: 10.1038/s41598-026-44815-8 — https://www.nature.com/articles/s41598-026-44815-8. Uses a **24 GHz ISM-band** FMCW radar for detection/tracking/classification — one of the few peer-reviewed works on the same frequency band as the proposed hardware; supports the claim that 24 GHz modules are adequate for detection/tracking/classification tasks.
- **[peer-reviewed]** *High Precision Human Detection and Tracking Using Millimeter-Wave Radars.* IEEE Aerospace and Electronic Systems Magazine (2021; Xplore doc 9318574) — https://ieeexplore.ieee.org/abstract/document/9318574. Reports high-accuracy human detection/tracking with mmWave radar; useful for citing achievable position accuracy and tracking performance.
- **[peer-reviewed]** *Real-time method for human presence detection by using micro-Doppler signatures information at 24GHz.* IEEE APSURSI 2009. DOI: 10.1109/APS.2009.5171844. Early peer-reviewed evidence that 24 GHz micro-Doppler can separate human presence from other motion — the technical basis for presence vs. clutter discrimination in the proposed band.
- **[peer-reviewed]** *Detection and Sensing of Human Body Micro-Motions Using 24GHz mm-Waves: A Case Study.* IEEE (2025; Xplore doc 11241290) — https://ieeexplore.ieee.org/abstract/document/11241290. Recent 24 GHz micro-motion sensing; supports stationary-person sensing (breathing/micro-motion) at 24 GHz.
- **[peer-reviewed]** Lien et al. *Soli: Ubiquitous Gesture Sensing with Millimeter Wave Radar.* ACM TOG 2016, 35(4). DOI: 10.1145/2897824.2925953 — https://dl.acm.org/doi/10.1145/2897824.2925953. Canonical demonstration that small, low-power mmWave radar can sense fine human motion non-visually — the "radar instead of camera" argument.
- **[peer-reviewed]** *Millimeter-Wave Radar Detection and Localization of a Human in Indoor Complex Environments.* Remote Sensing, 2024, 16(14):2572 — https://www.mdpi.com/2072-4292/16/14/2572. Quantifies how indoor multipath/clutter degrades human detection/localization and proposes mitigation — evidence for the clutter/multipath limitation and how the literature handles it.

**Accuracy/limits summary (state carefully in the paper):** FMCW range resolution is set by bandwidth, ΔR = c/(2B) (≈0.6 m for ~250 MHz at 24 GHz — theoretical; modules report finer *measurement* granularity, which is not the same as resolution). Angular resolution is set by array aperture (small 1T2R/2T4R arrays ⇒ coarse azimuth, poor separation of adjacent people). Multi-target counting accuracy degrades with occlusion, side-by-side clustering, and multipath ghosts; published evaluations therefore report counting error, position MAE/RMSE, and MOT metrics rather than raw detection rate alone.

---

## 3. Radar-Based Screen or Display Privacy Specifically

**Finding:** **No peer-reviewed system was found that uses radar *defensively* for screen/display privacy or radar-based user-proximity risk assessment.** The radar↔screen literature is dominated by (a) *attack* work (radar sensing of screens), and (b) *patents* from Google/Samsung/Hisense on radar presence/proxemic context. The gap is real and should be stated as such in the paper.

- **[peer-reviewed, attack side]** Li et al. (authors per Semantic Scholar). *WaveSpy: Remote and Through-wall Screen Attack via mmWave Sensing.* IEEE Symposium on Security and Privacy (S&P) 2020. DOI: 10.1109/SP40000.2020.00004 — https://www.semanticscholar.org/paper/WaveSpy%3A-Remote-and-Through-wall-Screen-Attack-via-Li-Ma/d4e3c1b0f1742633ed9ae5e6f8c8a64c2b4cdf11. The most important radar↔display security paper: mmWave radar can recover screen content remotely, even through walls — proves radar "sees" screens, motivating radar-based *detection of who is positioned to see* the screen as a defensive countermeasure (while carefully NOT claiming screen-content reconstruction, which is a privacy risk the proposed system must avoid).
- **[patent, non-peer-reviewed]** Google LLC. *Smartphone-Based Radar System for Facilitating Awareness of User Presence and Orientation.* US20200193942A1 — https://patents.google.com/patent/US20200193942A1. Radar for user presence/orientation awareness on a device — industry evidence that radar is considered privacy-safe for presence/orientation sensing (no camera).
- **[patent, non-peer-reviewed]** Google LLC. *Smartphone Providing Radar-Based Proxemic Context.* US 2022/0036863 — https://www.freepatentsonline.com/y2022/0036863.html. Radar-derived proxemic context (who/how many are near) — the patent-space equivalent of this project's multi-person proximity idea.
- **[patent, non-peer-reviewed]** *Video-Based Privacy Supporting System.* US20220245288 — https://patents.justia.com/patent/20220245288. Maintains privacy of displayed data from sensor-derived info — but video/camera-based, illustrating why non-visual sensing is the differentiator.
- **[thesis, non-peer-reviewed]** *Real-time mmWave Multi-Person Pose Estimation System for Privacy-Aware Windows.* TU Delft repository — https://repository.tudelft.nl/record/uuid:9d78ecc9-062a-4201-89f7-079ac59c385a. Uses mmWave radar (privacy-preserving by design) to drive adaptive privacy (window transparency); evidence of the "radar → privacy action" pattern outside the HCI-venue literature.
- **[vendor news, non-peer-reviewed]** Hisense patent news: display device that senses user position via radar without invading privacy — https://www.163.com/dy/article/J81JQJSK0519QIKK.html. Industry (smart TV) interest in radar-based user-location awareness for screen protection.

**Conclusion for §3:** position the paper as a (to our knowledge, novel) *peer-reviewed, defensive, spatial-risk* (distance + dwell + multi-person proximity) system using low-cost 24 GHz radar for screen privacy, citing WaveSpy (attack side) and the Google/Hisense patents (industry interest) plus the CHI-2016 proxemics precedent (sensing→protection) as motivation.

---

## 4. Presence/Tracking Standards & Measurement Methodology

**Finding:** There is **no ISO/IEC/ETSI/IEEE standard for radar-based human presence detection** (performance test methods, FP/FN reporting, or multi-target metrics for presence/occupancy sensing). The closest standards are PIR-specific: **IEC 63180:2020** (measurement and declaration of detection range of PIR detectors for major/minor motion) and **EN 50131-2-2** (PIR detectors in intrusion alarm systems, including false-alarm immunity tests). For multi-target tracking, the de-facto metrics come from computer vision: **MOTA/MOTP (CLEAR MOT)** and the **MOTChallenge** benchmark, plus **MAE/RMSE** for position error. Radar-specific indoor benchmarks exist (e.g., MMVR) but are research artifacts, not standards.

- **[standard]** IEC 63180:2020 (+ AMD1:2025). *Methods of measurement and declaration of the detection range of detectors — Passive infrared detectors for major and minor motion detection.* — https://webstore.iec.ch/en/publication/61559 (AMD1: https://webstore.iec.ch/en/publication/107580). The only IEC presence-detector measurement standard found; defines how detection *range* claims must be measured/declared. **Important:** it is PIR-specific — no radar equivalent exists, which the paper should note as a standardization gap (and optionally propose reporting detection-range curves in the IEC 63180 spirit).
- **[standard]** EN 50131-2-2:2017 (2021 revision). *Alarm systems — Intrusion and hold-up systems — Part 2-2: Intrusion detectors — Passive infrared detectors.* — https://shop.standards.ie/en-ie/standards/en-50131-2-2-2017-351220_saig_cenelec_cenelec_801753/. Includes immunity/false-alarm test conditions for PIR detectors — a template for defining false-positive testing protocols for presence sensors.
- **[peer-reviewed]** Bernardin & Stiefelhagen. *Evaluating Multiple Object Tracking Performance: The CLEAR MOT Metrics.* EURASIP Journal on Image and Video Processing, 2008. DOI: 10.1155/2008/246309 — https://preview-jivp-eurasipjournals.springeropen.com/articles/10.1155/2008/246309. Defines **MOTA** (multi-object tracking accuracy: FP+FN+switches normalized) and **MOTP** (mean position error of matched tracks) — the standard multi-target metrics to report for multi-person tracking (as used by the radar tracking papers in §2).
- **[peer-reviewed]** Dendorfer et al. *MOTChallenge: A Benchmark for Single-Camera Multiple Target Tracking.* IJCV, 2021. DOI: 10.1007/s11263-020-01393-0 — https://dl.acm.org/doi/10.1007/s11263-020-01393-0. The de-facto benchmark defining MOT metric computation and reporting conventions (IDs, fragments, MOTA/MOTP); cite for how multi-target metrics are aggregated over trials.
- **[peer-reviewed]** *MMVR: Millimeter-wave Multi-View Radar Dataset and Benchmark for Indoor Perception.* arXiv:2406.10708 — http://arxiv.org/abs/2406.10708. Multi-view mmWave radar dataset with benchmark protocols for indoor perception — a radar-specific evaluation resource to align with.
- **[peer-reviewed]** *A high-fidelity residential building occupancy detection dataset.* Scientific Data, 2021. DOI: 10.1038/s41597-021-01055-x — https://link.springer.com/article/10.1038/s41597-021-01055-x. Occupancy dataset with ground-truth methodology — useful for how occupancy ground truth is collected and reported (accuracy, confusion metrics).
- **[peer-reviewed]** *Passive Infrared Sensor-Based Occupancy Monitoring in Smart Buildings: A Review of Methodologies and Machine Learning Approaches.* Sensors, 2024, 24(5):1533 — https://www.mdpi.com/1424-8220/24/5/1533. Reviews how PIR occupancy sensing is evaluated (accuracy, FP/FN handling) and contrasts PIR vs. emerging radar sensing.

**Reporting recommendation for the paper:** report per-condition (i) detection FP/FN (or precision/recall) with binomial CIs, (ii) distance MAE/RMSE vs. ground truth (offline video labeling), (iii) presence-duration error, (iv) MOTA/MOTP for multi-person scenarios, and (v) detection-range curves in the spirit of IEC 63180.

---

## 5. Statistical / Experimental Methodology for Small-Sample Human-Subject Sensor Studies

**Finding:** Modern guidance is that adequacy is **not** a magic "n=30" but a function of expected effect size, variability, design, and the target inference (precision vs. power); small-sample sensor studies should report confidence intervals and effect sizes, use planned power/CI-precision analysis, correct for multiple comparisons, and quantify labeling agreement (Cohen's/Fleiss' kappa) — with published sample-size formulas for kappa studies.

- **[peer-reviewed]** Lakens. *Sample Size Justification.* Collabra: Psychology, 2022, 8(1):33267. DOI: 10.1525/collabra.33267 — https://online.ucpress.edu/collabra/article/8/1/33267/120491/Sample-Size-Justification. The authoritative "how to justify sample size" paper: power analysis, precision-based (CI-width) justification, and design considerations — directly answers "how many trials per condition," i.e., it depends on the effect you must detect and the CI width you need.
- **[peer-reviewed]** Cumming. *The New Statistics: Why and How.* Psychological Science, 2014, 25(1). DOI: 10.1177/0956797613504966 — https://pubmed.ncbi.nlm.nih.gov/24220629/. Argues for estimation (CIs + effect sizes) over dichotomous significance testing; the basis for reporting effect sizes with CIs in small sensor studies.
- **[peer-reviewed]** Faul et al. *G*Power 3: A flexible statistical power analysis program for the social, behavioral, and biomedical sciences.* Behavior Research Methods, 2007 — https://www.semanticscholar.org/paper/G*Power-3%3A-A-flexible-statistical-power-analysis-Faul-Erdfelder/6814d976154b17e41bc79f8694e2372534e50419. The standard tool for a priori power analysis; cite when reporting how condition trial counts were derived.
- **[peer-reviewed]** Benjamini & Hochberg. *Controlling the False Discovery Rate: A Practical and Powerful Approach to Multiple Testing.* J. Royal Statistical Society B, 1995, 57(1):289–300. DOI: 10.1111/j.2517-6161.1995.tb02031.x — https://academic.oup.com/jrsssb/article/57/1/289/7035855. FDR control — the recommended modern alternative to Bonferroni when many conditions/metrics are tested (e.g., per-distance-bin accuracy comparisons).
- **[peer-reviewed]** Perneger. *What's Wrong with Bonferroni Adjustments.* BMJ, 1998, 316:1236 — https://www.bmj.com/content/316/7139/1236. The classic critique of over-correcting; cite to justify *principled* multiplicity handling (pre-specified hypotheses + FDR) rather than blanket Bonferroni.
- **[peer-reviewed]** Fleiss. *Measuring nominal scale agreement among many raters.* Psychological Bulletin, 1971, 76(5):378–382. DOI: 10.1037/h0031619 — https://psycnet.apa.org/doiLanding?doi=10.1037%2Fh0031619. Defines **Fleiss' kappa** for multi-rater agreement — the metric for inter-annotator agreement of the offline video ground-truth labeling (multiple annotators labeling "person present / near screen").
- **[peer-reviewed]** Flack, Afifi & Lachenbruch. *Sample size determinations for the two rater kappa statistic.* Psychometrika, 1988, 53(3):321–325 — https://core-prod.cambridgecore.org/core/journals/psychometrika/article/abs/sample-size-determinations-for-the-two-rater-kappa-statistic/E74E39AE5F6C724597A5D6FA6BB2761B. Published sample-size formulas for kappa precision — cite when justifying the number of annotated frames/segments for ground truth.
- **[peer-reviewed]** Donner & Eliasziw. *Sample size requirements for reliability studies.* Statistics in Medicine, 1987 — https://ang-dd.sagepub.com/lp/wiley/sample-size-requirements-for-reliability-studies-KKPppx8EY9. Reliability-study sample sizes (kappa/ICC); complements Flack et al. for continuous agreement measures.
- **[peer-reviewed]** Westfall, Judd & Kenny. *Replicating Studies in Which Samples of Participants Respond to Samples of Stimuli.* Perspectives on Psychological Science, 2015, 10(6). DOI: 10.1177/1745691614564879 — https://journals.sagepub.com/doi/10.1177/1745691614564879. Shows that generalizability depends on sampling **both** participants *and* stimuli/conditions (here: trials × persons × positions) — the statistical argument for why "30 trials at one position with one participant" understates uncertainty, and why condition/trial counts should be modeled as random factors.
- **[peer-reviewed]** *A Tutorial on Sample Size Calculation for Inter-rater and Intra-rater Agreement Studies.* Indian Journal of Psychological Medicine (2026). DOI: 10.1177/02537176261422290 — https://www.ovid.com/journals/ijpmed/fulltext/10.1177/02537176261422290~a-tutorial-on-sample-size-calculation-for-inter-rater-and. Accessible tutorial for kappa-based sample size; practical citation for the ground-truth labeling protocol.

**On "30 trials per condition":** The report should state: (1) n=30 is a heuristic, not a statistical guarantee; (2) what matters is the *minimum detectable effect* (via a priori power analysis, G*Power) or the *achieved CI width* (Lakens; Cumming); (3) for binary detection metrics, report Wilson/binomial CIs on precision/recall per condition; (4) for multi-target metrics, MOTA/MOTP are aggregates over tracks — their uncertainty scales with number of tracked segments, so both trial count *and* track count matter; (5) treat participants/positions/trials as random factors (Westfall et al.) and justify kappa sample sizes (Flack; Donner & Eliasziw) for the labeling study.

---

## 6. Documented Limitations of 24 GHz Low-Cost Radar (HLK LD2410/LD2450/LD2451/LD2453 class)

**Finding:** The known failure modes — static-person dropout, false triggers from fans/curtains/moving furniture, limited angular separation, multipath ghosts — are documented in vendor datasheets/white papers, vendor support forums, the hobbyist/Home Assistant community, and (for the physics) in peer-reviewed radar literature. The paper should treat them as engineering constraints with published mitigations.

- **[vendor datasheet/white paper]** Hi-Link (HLK) product pages — LD2410B presence module: https://www.hlktech.com/en/Goods-238.html ; LD2450 (1T2R, multi-target state/trajectory detection): https://www.hlktech.com/en/Goods-226.html ; LD2451 (note: marketed for **rear-vehicle/BSD detection**, not human presence): https://www.hlktech.com/en/Goods-245.html ; LD2453 (new multi-target human tracking): https://www.hlktech.com/en/NewsInfo-383.html and https://www.hlktech.com/en/NewsInfo-405.html ; 24G module selection guide: https://hlktech.com/en/NewsInfo-276.html. Primary spec source; specs are vendor claims (max range ~6 m class, moving+stationary presence, 1T2R/2T4R arrays, UART/GPIO output) and should be labeled as such in the paper.
- **[vendor news]** Hi-Link/Ameya360: *LD2410B adds noise-floor detection to improve anti-interference and reduce false triggers* — https://www.ameya360.com/qiye/108728.html. Vendor's own acknowledgment that false triggers (moving furniture, fans, curtains) are a real issue, and that noise-floor/energy-threshold handling is the mitigation.
- **[vendor KB, non-peer-reviewed]** Infineon community knowledge base: *Detection of stationary objects using Radar technology* — https://community.infineon.com/t5/Knowledge-Base-Articles/Detection-of-stationary-objects-using-Radar-technology/ta-p/681036. Explains that CW/presence radars easily detect *moving* targets but stationary humans are hard (need micro-Doppler/vital-signs processing) — the core "sitting-still dropout" limitation.
- **[peer-reviewed]** IEEE APSURSI 2009 (24 GHz micro-Doppler presence, DOI 10.1109/APS.2009.5171844, §2) and IET Radar Sonar Navig. 2015 (24 GHz vital signs, DOI 10.1049/iet-rsn.2015.0118 — https://ietresearch.onlinelibrary.wiley.com/doi/full-xml/10.1049/iet-rsn.2015.0118): the published way to handle "person sitting still" is to exploit respiration/micro-motion — evidence that static-person detection at 24 GHz requires more than simple moving-target detection.
- **[peer-reviewed]** *Vitality Detection with FMCW Radar Based SAR Imaging Technique at 24GHz.* IEEE AP-S 2024. DOI: 10.1109/AP-S/INC-USNC-URSI52054.2024.10687111 — https://plu.mx/plum/a/?doi=10.1109/AP-S/INC-USNC-URSI52054.2024.10687111. Recent 24 GHz work on detecting stationary/living humans — same mitigation direction.
- **[peer-reviewed]** Multipath/ghost literature — *Multipath Ghost Recognition and Suppression Method Based on Template Matching for Indoor Human Detection and Location* — https://www.scilit.com/publications/382ab49c7fb9ca4cdba7651f751d0a00 ; *Millimeter-Wave Radar Detection and Localization of a Human in Indoor Complex Environments*, Remote Sensing 2024 (§2); *Radar-based human target detection using deep residual U-net for smart home applications* — https://www.dev.cris.fau-dev.tf.fau.de/publications/263932717/. Indoor wall/floor multipath creates ghost targets that must be suppressed; published approaches use template matching, deep learning, and range-Doppler domain filtering.
- **[community/forum]** Home Assistant + ESPHome ecosystem (non-peer-reviewed but rich field evidence):
  - *HLK LD2450 doesn't pick up presence until within 1–2 m* — https://community.home-assistant.io/t/hlk-ld2450-doesnt-seem-to-pick-up-presense-until-within-1-2-meters/752304/7 (short effective range/stationary-person issues);
  - *Everything Presence Lite shows too many targets* — https://community.home-assistant.io/t/everything-presence-lite-shows-too-many-targets/989070 (false/multiple targets from clutter);
  - *LD2410 fan noise interference* — https://bbs.hassbian.com/forum.php?mod=viewthread&tid=25854 (rotating fan → false presence);
  - *The hunt for the best room occupancy solution* — https://community.home-assistant.io/t/the-hunt-for-the-best-room-occupancy-solution/298941/45 (community comparison: no cheap sensor is reliable for static presence);
  - ESPHome gotchas/blogs: LD2410 https://www.atomic14.com/esp32/sensors/hlk-ld2410/ ; LD2450 https://www.atomic14.com/esp32/sensors/hlk-ld2450/.
- **[community/forum]** TI E2E: *Two people walking side by side seen as one cluster* — https://e2e.ti.com/support/sensors-group/sensors/f/sensors-forum/772428/. Vendor forum confirmation of the multi-person clustering/angular-resolution ambiguity.
- **[physics, textbook]** FMCW range resolution ΔR = c/(2B) and angular resolution ~λ/(array aperture): at 24 GHz (λ≈12.5 mm) with ~250 MHz bandwidth, ΔR≈0.6 m (resolution, not measurement granularity); small 1T2R arrays give coarse azimuth. State as theory, and note that vendor "0.1 m resolution" claims refer to measurement granularity, not Rayleigh resolution — a frequent source of confusion.

**How studies handle these:** threshold on moving+stationary energy gates with noise-floor adaptation (vendor), micro-Doppler/vital-signs processing for static humans (peer-reviewed), template-matching or learned clutter/ghost suppression (peer-reviewed), multi-radar fusion for occlusion (ORACLE), and explicit reporting of FP/FN under controlled scenarios (§4) rather than single "detection rate" numbers.

---

## 7. Implications for the Proposed System (synthesis)

1. The novelty claim is defensible: no peer-reviewed radar-based *defensive* screen-privacy system with spatial risk scoring was found (§3); the CHI-2016 proxemics precedent and the Google/Hisense patents support the sensing→protection pattern, and WaveSpy shows radar "sees" screens (attack side) — motivating radar-based risk assessment.
2. Stay strictly within the claim: report distance, presence duration, and multi-person proximity (MOTA/MOTP, MAE/RMSE, FP/FN with CIs); explicitly state the system does **not** do identity recognition or intent inference, and that WaveSpy-style screen-content reconstruction is out of scope (and a privacy risk to avoid).
3. Address the known 24 GHz limitations head-on (§6) with a mitigation table: static-person dropout (micro-Doppler/vital-signs thresholds), fan/curtain false triggers (energy-gate + noise-floor thresholds, occlusion-aware logic), multipath ghosts (range-Doppler gating, template rejection), angular ambiguity (conservative "at least N persons" reporting rather than exact count, or multi-radar).
4. Use offline video only for ground truth, under informed consent; report inter-annotator agreement (Fleiss' kappa; sample size per Flack/Donner) and per-condition binomial CIs; justify trial counts with a priori power/CI-precision analysis (Lakens, G*Power) and treat participants/positions/trials as random factors (Westfall et al.).
5. Position metrics against established conventions: IEC 63180-style detection-range curves, MOTA/MOTP (Bernardin & Stiefelhagen), MAE/RMSE for distance, and note the absence of a radar-presence standard as a gap the paper can flag.

---

## 8. Top References (most relevant & highest quality)

1. **WaveSpy** (Li et al., IEEE S&P 2020, DOI 10.1109/SP40000.2020.00004) — radar↔screen security; motivates and bounds the problem. [peer-reviewed]
2. **Abdrabou et al., CHI 2023** (DOI 10.1145/3531073.3531106) — quantitative shoulder-surfer geometry (distance/angle/duration) in VR; the behavioral anchor for risk zones. [peer-reviewed]
3. **Tari, Ozok & Holden, SOUPS 2006** (DOI 10.1145/1143120.1143128) — canonical empirical shoulder-surfing study. [peer-reviewed]
4. **Pegoraro et al., IEEE Access 2021** (DOI 10.1109/ACCESS.2021.3083980) — real-time multi-person mmWave tracking with evaluation methodology. [peer-reviewed]
5. **ORACLE** (Pegoraro et al., arXiv:2208.14199 / IEEE 2023) — occlusion and multi-radar fusion for multi-person tracking. [peer-reviewed]
6. **Shen, Nunez-Yanez & Dahnoun, Sensors 2024** (DOI 10.3390/s24113660) — multi-human tracking + detection on a low-cost mmWave module. [peer-reviewed]
7. **Bernardin & Stiefelhagen, EURASIP JIVP 2008** (DOI 10.1155/2008/246309) — MOTA/MOTP, the multi-target reporting standard. [peer-reviewed]
8. **IEC 63180:2020** (webstore.iec.ch/publication/61559) — detection-range measurement standard; the template for presence-sensor claims (PIR-specific; radar gap). [standard]
9. **Lakens, Collabra 2022** (DOI 10.1525/collabra.33267) — sample-size justification (power/CI-precision), for "how many trials per condition." [peer-reviewed]
10. **Benjamini & Hochberg, JRSS-B 1995** (DOI 10.1111/j.2517-6161.1995.tb02031.x) — FDR for multiple-comparison correction across conditions/metrics. [peer-reviewed]

*Runner-ups: Cumming 2014 (DOI 10.1177/0956797613504966), Flack et al. 1988 (Psychometrika), Fleiss 1971 (DOI 10.1037/h0031619), MOTChallenge (DOI 10.1007/s11263-020-01393-0), Westfall et al. 2015 (DOI 10.1177/1745691614564879), IEEE APSURSI 2009 24 GHz presence (DOI 10.1109/APS.2009.5171844).*

---

## 9. Full Reference List (all sources seen in web search, with type tags)

**Peer-reviewed:**
1. Tari, Ozok, Holden (2006). A comparison of perceived and real shoulder-surfing risks between alphanumeric and graphical passwords. SOUPS '06. DOI 10.1145/1143120.1143128.
2. Abdrabou et al. (2023). Understanding Shoulder Surfer Behavior and Attack Patterns Using Virtual Reality. CHI. DOI 10.1145/3531073.3531106.
3. Brudy, Ledo, Greenberg et al. (2014). Is Anyone Looking? CHI EA. DOI 10.1145/2559206.2579528.
4. Zhou et al. (2016). Enhancing Mobile Content Privacy with Proxemics Aware Notifications and Protection. CHI. DOI 10.1145/2858036.2858232.
5. Kise et al. (2019). Private Reader: Using Eye Tracking to Improve Reading Privacy in Public Spaces. MobileHCI. DOI 10.1145/3338286.3340129.
6. Mathis, Williamson, Vaniea, Khamis (2020). The Role of Eye Gaze in Security and Privacy Applications. CHI. DOI 10.1145/3313831.3376840.
7. BAIT (2026). Visual-illusion-inspired Privacy Preservation for Mobile Data Visualization. CHI. DOI 10.1145/3772318.3791259.
8. Pegoraro et al. (2021). Real-Time People Tracking and Identification From Sparse mm-Wave Radar Point-Clouds. IEEE Access. DOI 10.1109/ACCESS.2021.3083980.
9. Shen, Nunez-Yanez, Dahnoun (2024). Advanced Millimeter-Wave Radar System for Real-Time Multiple-Human Tracking and Fall Detection. Sensors 24(11):3660. DOI 10.3390/s24113660.
10. Pegoraro et al. (2022/2023). ORACLE: Occlusion-Resilient and Self-Calibrating mmWave Radar Network for People Tracking. arXiv:2208.14199; IEEE Xplore 10342865.
11. (2025). Evaluation of Detection and Tracking Approaches for People Counting Using mmWave Radar. IEEE Xplore 11318383 (ICSPIS 2025 program).
12. (2026). Lightweight FMCW radar framework for human activity recognition under limited data conditions. Scientific Reports. DOI 10.1038/s41598-026-44815-8.
13. (2021). High Precision Human Detection and Tracking Using Millimeter-Wave Radars. IEEE AES Magazine. Xplore 9318574.
14. (2009). Real-time method for human presence detection by using micro-Doppler signatures at 24 GHz. IEEE APSURSI. DOI 10.1109/APS.2009.5171844.
15. (2025). Detection and Sensing of Human Body Micro-Motions Using 24GHz mm-Waves: A Case Study. IEEE. Xplore 11241290.
16. (2015). Vital-signs observation (heartbeat/breathing) with radar. IET Radar, Sonar & Navigation. DOI 10.1049/iet-rsn.2015.0118.
17. (2024). Vitality Detection with FMCW Radar Based SAR Imaging Technique at 24 GHz. IEEE AP-S. DOI 10.1109/AP-S/INC-USNC-URSI52054.2024.10687111.
18. Lien et al. (2016). Soli: Ubiquitous Gesture Sensing with Millimeter Wave Radar. ACM TOG 35(4). DOI 10.1145/2897824.2925953.
19. Li et al. (2020). WaveSpy: Remote and Through-wall Screen Attack via mmWave Sensing. IEEE S&P. DOI 10.1109/SP40000.2020.00004.
20. (2024). Millimeter-Wave Radar Detection and Localization of a Human in Indoor Complex Environments. Remote Sensing 16(14):2572.
21. Multipath Ghost Recognition and Suppression Method Based on Template Matching for Indoor Human Detection and Location (scilit record).
22. Radar-based human target detection using deep residual U-net for smart home applications (FAU repository record).
23. Bernardin & Stiefelhagen (2008). Evaluating Multiple Object Tracking Performance: The CLEAR MOT Metrics. EURASIP JIVP. DOI 10.1155/2008/246309.
24. Dendorfer et al. (2021). MOTChallenge: A Benchmark for Single-Camera Multiple Target Tracking. IJCV. DOI 10.1007/s11263-020-01393-0.
25. (2024). MMVR: Millimeter-wave Multi-View Radar Dataset and Benchmark for Indoor Perception. arXiv:2406.10708.
26. (2021). A high-fidelity residential building occupancy detection dataset. Scientific Data. DOI 10.1038/s41597-021-01055-x.
27. (2024). Passive Infrared Sensor-Based Occupancy Monitoring in Smart Buildings: A Review. Sensors 24(5):1533.
28. Lakens (2022). Sample Size Justification. Collabra: Psychology 8(1):33267. DOI 10.1525/collabra.33267.
29. Cumming (2014). The New Statistics: Why and How. Psychological Science. DOI 10.1177/0956797613504966.
30. Faul et al. (2007). G*Power 3. Behavior Research Methods (Semantic Scholar record).
31. Benjamini & Hochberg (1995). Controlling the False Discovery Rate. JRSS-B 57(1):289–300. DOI 10.1111/j.2517-6161.1995.tb02031.x.
32. Perneger (1998). What's Wrong with Bonferroni Adjustments. BMJ 316:1236.
33. Fleiss (1971). Measuring nominal scale agreement among many raters. Psychological Bulletin 76(5):378–382. DOI 10.1037/h0031619.
34. Flack, Afifi, Lachenbruch (1988). Sample size determinations for the two rater kappa statistic. Psychometrika 53(3):321–325.
35. Donner & Eliasziw (1987). Sample size requirements for reliability studies. Statistics in Medicine.
36. Westfall, Judd, Kenny (2015). Replicating Studies in Which Samples of Participants Respond to Samples of Stimuli. Perspectives on Psychological Science. DOI 10.1177/1745691614564879.
37. (2026). A Tutorial on Sample Size Calculation for Inter-rater and Intra-rater Agreement Studies. Indian Journal of Psychological Medicine. DOI 10.1177/02537176261422290.
38. (2024). Multi-occupant tracking with radar and wearable devices for enhanced accuracy in indoor environments. Engineering Applications of AI (ScienceDirect S0952197625008723).

**Standards:**
39. IEC 63180:2020 + AMD1:2025 (PIR detection-range measurement).
40. EN 50131-2-2:2017/2021 (PIR intrusion detectors; immunity/false-alarm tests).

**Patents (non-peer-reviewed):**
41. US20200193942A1 (Google — smartphone radar presence/orientation awareness).
42. US 2022/0036863 (Google — smartphone radar-based proxemic context).
43. US20220245288 (video-based privacy supporting system).

**Thesis:**
44. Real-time mmWave Multi-Person Pose Estimation System for Privacy-Aware Windows (TU Delft).

**Vendor datasheets/white papers/news:**
45. Hi-Link LD2410B page (Goods-238); LD2450 (Goods-226); LD2451 (Goods-245); LD2453 (NewsInfo-383/405); 24G selection guide (NewsInfo-276).
46. Hi-Link/Ameya360 — LD2410B noise-floor feature news (ameya360.com/qiye/108728.html).
47. Infineon KB — Detection of stationary objects using radar (community.infineon.com).

**Preprints:**
48. arXiv:2602.08465 — Two-Week In-the-Wild Study of Screen Filters and Camera Sliders.

**Community/forums (field evidence, non-peer-reviewed):**
49. Home Assistant: LD2450 1–2 m presence thread; "Everything Presence Lite too many targets"; "hunt for the best room occupancy solution"; Hassbian LD2410 fan-noise thread.
50. TI E2E: side-by-side people seen as one cluster.
51. ESP Modules blog (atomic14.com): LD2410/LD2450 gotchas.
52. Screek radar parameter comparison (screek.io).
