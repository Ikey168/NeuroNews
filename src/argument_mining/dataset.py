"""
Dataset utilities for argument mining models.

Loads labelled data from the #109 Parquet dataset when available,
or returns a synthetic bootstrap set for initial training.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional, Tuple

from services.ingest.common.document_model import Document

# Stance label ordering is stable — index == model label id.
STANCE_LABELS = ["supportive", "critical", "neutral", "ambiguous"]
STANCE2ID = {s: i for i, s in enumerate(STANCE_LABELS)}
ID2STANCE = {i: s for s, i in STANCE2ID.items()}


# ---------------------------------------------------------------------------
# Sentence splitting
# ---------------------------------------------------------------------------

def sentences_from_document(doc: Document) -> List[str]:
    """Split a Document's content into individual sentences."""
    text = doc.content or doc.title or ""
    if not text.strip():
        return []
    parts = re.split(r"(?<=[.!?])\s+|\n{2,}", text.strip())
    return [p.strip() for p in parts if len(p.strip()) >= 20]


# ---------------------------------------------------------------------------
# Bootstrap training data
# ---------------------------------------------------------------------------

# (text, is_claim, source_type)
_CLAIM_EXAMPLES: List[Tuple[str, int, str]] = [
    # --- news: factual claims ---
    ("The unemployment rate fell to 3.8% in March, the lowest level in two decades.", 1, "news"),
    ("Researchers at MIT published findings showing a 40% reduction in carbon emissions.", 1, "news"),
    ("The company reported quarterly revenue of $4.2 billion, up 12% year-on-year.", 1, "news"),
    ("Three people were killed and eleven injured in the attack on Tuesday.", 1, "news"),
    ("Parliament passed the Climate Emergency Act by a margin of 312 to 189.", 1, "news"),
    ("Global average temperatures have risen by 1.1°C since pre-industrial times.", 1, "news"),
    ("The central bank raised interest rates by 25 basis points to 5.25%.", 1, "news"),
    ("Scientists identified a new protein linked to early-onset Alzheimer's disease.", 1, "news"),
    ("The court ruled the legislation unconstitutional in a 5-4 decision.", 1, "news"),
    ("Exports fell by 8% in the second quarter due to weakening demand in Asia.", 1, "news"),
    ("The study found that 62% of participants reported improved sleep quality.", 1, "news"),
    ("The bridge collapsed at 6:14 am local time, trapping several vehicles.", 1, "news"),
    ("CEO John Smith resigned following the board's vote of no confidence.", 1, "news"),
    ("The treaty was signed by representatives of 47 countries in Geneva.", 1, "news"),
    ("Housing starts declined 5.3% last month as mortgage rates climbed above 7%.", 1, "news"),
    ("The vaccine demonstrated 94% efficacy against severe disease in phase 3 trials.", 1, "news"),
    ("Production volumes reached 2.3 million units in the third quarter.", 1, "news"),
    ("The election is scheduled to take place on 15 November.", 1, "news"),
    ("Average house prices rose 3.1% in the 12 months to June.", 1, "news"),
    ("The bill was approved by the Senate 68 votes to 32.", 1, "news"),
    # --- news: non-claims ---
    ("This development is deeply troubling and demands an immediate response.", 0, "news"),
    ("Many people believe the situation will improve in the coming months.", 0, "news"),
    ("It remains to be seen whether the policy will have the intended effect.", 0, "news"),
    ("Critics argue that the government has not done enough to address the crisis.", 0, "news"),
    ("The question of whether this approach is sustainable is still open.", 0, "news"),
    ("In my view, this represents a missed opportunity for meaningful reform.", 0, "news"),
    ("Some observers worry that the consequences could be severe.", 0, "news"),
    ("The long-term implications of this decision are difficult to predict.", 0, "news"),
    ("Analysts have mixed opinions about the prospects for recovery.", 0, "news"),
    ("There is growing concern about the impact on vulnerable communities.", 0, "news"),
    ("Perhaps the most surprising aspect is how little attention it has received.", 0, "news"),
    ("One might argue that the real issue lies elsewhere entirely.", 0, "news"),
    ("Depending on how you look at it, this could be seen as progress or regression.", 0, "news"),
    ("How the situation unfolds over the next few months remains unclear.", 0, "news"),
    ("Will the economy recover in time for the next election?", 0, "news"),
    ("For many families, the uncertainty is the hardest part to bear.", 0, "news"),
    ("We must act decisively before it is too late.", 0, "news"),
    ("The debate has been going on for years without resolution.", 0, "news"),
    ("It is hoped that the new measures will ease the pressure on households.", 0, "news"),
    ("Whether this proves effective remains an open question.", 0, "news"),
    # --- blog: factual claims ---
    ("After tracking engagement daily for 18 months, I confirmed a 37% drop after the platform update.", 1, "blog"),
    ("The battery lasted exactly 6 hours 22 minutes under continuous load in my benchmarks.", 1, "blog"),
    ("My A/B test across 500 subscribers showed a 28% higher open rate for subject lines under 50 characters.", 1, "blog"),
    ("I documented three separate incidents where the build pipeline silently discarded test results.", 1, "blog"),
    ("The library added async support in version 3.2.0, released on 4 April 2024.", 1, "blog"),
    ("My traffic data shows that 74% of readers arrive from search, not social, on this topic.", 1, "blog"),
    # --- blog: non-claims ---
    ("In my opinion, this is the most overrated framework released in the past decade.", 0, "blog"),
    ("I believe we're at an inflection point that could change everything about remote work.", 0, "blog"),
    ("To me, the real problem isn't the technology itself but how organisations choose to deploy it.", 0, "blog"),
    ("Perhaps the biggest mistake teams make is assuming that more tooling means more productivity.", 0, "blog"),
    # --- paper: factual claims ---
    ("Our analysis reveals a statistically significant correlation between sleep duration and cognitive performance (r = 0.74, p < 0.001).", 1, "paper"),
    ("The cohort comprised 3,247 participants aged 18–65 recruited across six clinical sites between 2020 and 2023.", 1, "paper"),
    ("Gene expression analysis identified 142 differentially expressed genes, of which 89 were upregulated.", 1, "paper"),
    ("The intervention group showed a 41% reduction in symptom severity versus placebo (95% CI: 38–44%).", 1, "paper"),
    ("Results replicated across all three independent validation cohorts (N = 812, 1,104, and 963).", 1, "paper"),
    ("Sensitivity analysis excluding outliers did not materially change the point estimate (OR = 1.34, 95% CI: 1.18–1.53).", 1, "paper"),
    # --- paper: non-claims ---
    ("It is possible that unmeasured confounders may have influenced the observed association.", 0, "paper"),
    ("Future research should examine whether these findings generalise to non-Western populations.", 0, "paper"),
    ("One limitation of this study is the reliance on self-reported dietary intake.", 0, "paper"),
    ("Whether the effect persists beyond the 12-month follow-up period remains to be determined.", 0, "paper"),
    # --- transcript: factual claims ---
    ("What we reported to the board was a 30% reduction in operating costs across all four divisions last year.", 1, "transcript"),
    ("The minister confirmed that 14,000 new homes had been completed under the programme as of last month.", 1, "transcript"),
    ("He stated, and I quote, 'We will not be renewing the contract when it expires in March.'", 1, "transcript"),
    ("The committee chair confirmed the vote passed by nine votes to three at last Wednesday's session.", 1, "transcript"),
    ("Our data shows the programme enrolled 8,400 participants in its first year of operation.", 1, "transcript"),
    # --- transcript: non-claims ---
    ("I think what we're seeing is a fundamental shift in how communities engage with these institutions.", 0, "transcript"),
    ("Could you explain why the projections were revised downward so significantly after Q2?", 0, "transcript"),
    ("Many of our members feel that the proposed changes simply do not go far enough.", 0, "transcript"),
    # --- book: factual claims ---
    ("By 1943 the city had lost more than a third of its pre-war population to evacuation and displacement.", 1, "book"),
    ("The company was incorporated in 1887 in a small workshop on the outskirts of Manchester.", 1, "book"),
    ("Annual harvest exceeded one million tonnes for the first time in 1952, according to Ministry records.", 1, "book"),
    ("The treaty signed on 11 June 1919 transferred sovereignty over the territory to the newly formed republic.", 1, "book"),
    ("By the end of the decade, four of the original seven founding members had withdrawn from the alliance.", 1, "book"),
    # --- book: non-claims ---
    ("One might argue that the turning point came not with the armistice but with the collapse of civilian morale.", 0, "book"),
    ("Looking back, it is tempting to see the outcome as inevitable, yet contemporaries experienced profound uncertainty.", 0, "book"),
    ("Whether this represented a strategic masterstroke or a catastrophic miscalculation remains a matter of debate.", 0, "book"),
    # --- note: factual claims ---
    ("Board approved budget of $2.4M on 14 June; finance confirmed wire transfer completed same day.", 1, "note"),
    ("Vendor confirmed delivery of 200 units by 30 June; PO #4471 raised on 15 June.", 1, "note"),
    ("Security audit completed 10 June — 3 critical findings, all remediated and signed off by 12 June.", 1, "note"),
    ("Call completed at 14:00 on Thursday; client approved revised scope and new go-live date of 1 September.", 1, "note"),
    # --- note: non-claims ---
    ("Need to follow up with legal on the contract terms before signing — not clear on indemnity clause.", 0, "note"),
    ("Not sure if the proposed timeline is realistic given current team capacity and the pending holiday period.", 0, "note"),
]

# (text, topic, stance, source_type)
_STANCE_EXAMPLES: List[Tuple[str, str, str, str]] = [
    # --- news: supportive ---
    ("The renewable energy transition is creating thousands of new jobs and driving economic growth.", "renewable energy", "supportive", "news"),
    ("This landmark legislation finally gives workers the protections they deserve.", "labor rights", "supportive", "news"),
    ("The new drug has shown remarkable results and could transform treatment for millions of patients.", "healthcare", "supportive", "news"),
    ("Increased investment in infrastructure will pay dividends for decades to come.", "infrastructure", "supportive", "news"),
    ("The trade agreement opens up vital new markets for domestic manufacturers.", "trade", "supportive", "news"),
    ("Evidence strongly supports the effectiveness of early childhood education programmes.", "education", "supportive", "news"),
    ("The reform significantly improves access to justice for ordinary citizens.", "justice", "supportive", "news"),
    ("This policy has delivered measurable improvements in air quality across the region.", "environment", "supportive", "news"),
    # --- news: critical ---
    ("The policy has done nothing to address the root causes of poverty and inequality.", "social policy", "critical", "news"),
    ("This reckless spending will saddle future generations with unsustainable debt.", "fiscal policy", "critical", "news"),
    ("The regulation imposes an unacceptable burden on small businesses already struggling to survive.", "regulation", "critical", "news"),
    ("The agreement sacrifices domestic jobs in exchange for corporate profits.", "trade", "critical", "news"),
    ("The government's response to the crisis has been woefully inadequate.", "government response", "critical", "news"),
    ("These cuts will devastate essential services that millions of people depend on.", "public spending", "critical", "news"),
    ("The legislation fails to address the systemic issues at the heart of the problem.", "legislation", "critical", "news"),
    ("The plan prioritises corporate interests over the welfare of ordinary citizens.", "policy", "critical", "news"),
    # --- news: neutral ---
    ("The bill was introduced to the Senate on Monday and will go to committee next week.", "legislation", "neutral", "news"),
    ("The company's share price rose 3% following the announcement of the merger.", "markets", "neutral", "news"),
    ("Representatives from both parties met for three hours of talks yesterday.", "politics", "neutral", "news"),
    ("The report found that average temperatures in the region increased by 0.8°C over the decade.", "climate", "neutral", "news"),
    ("Production volumes reached 2.3 million units in the third quarter.", "manufacturing", "neutral", "news"),
    ("The election is scheduled to take place on 15 November.", "elections", "neutral", "news"),
    ("The central bank kept rates unchanged at its monthly meeting.", "monetary policy", "neutral", "news"),
    ("The study enrolled 4,500 participants across 12 countries over three years.", "research", "neutral", "news"),
    # --- news: ambiguous ---
    ("While the initiative has shown some promise, its long-term viability is uncertain.", "initiative", "ambiguous", "news"),
    ("The results are mixed: some communities have benefited while others have not.", "policy", "ambiguous", "news"),
    ("Supporters point to job creation figures, but critics note rising inequality.", "economy", "ambiguous", "news"),
    ("The reform is welcome in principle, though implementation has been uneven.", "reform", "ambiguous", "news"),
    ("The data suggests improvement in some areas but deterioration in others.", "performance", "ambiguous", "news"),
    ("It is difficult to draw firm conclusions from the available evidence.", "research", "ambiguous", "news"),
    ("The agreement has both strengths and significant weaknesses that must be addressed.", "agreement", "ambiguous", "news"),
    ("Opinion is divided on whether the benefits outweigh the costs.", "policy", "ambiguous", "news"),
    # --- blog ---
    ("I've watched this policy fail communities for years — it's time to scrap it entirely.", "social policy", "critical", "blog"),
    ("The data I've collected consistently backs what advocates have been saying: early intervention works.", "education", "supportive", "blog"),
    ("My readers are split: some see this as progress, others as window-dressing with no real substance.", "policy", "ambiguous", "blog"),
    ("Last Tuesday the government published revised figures showing a 12% drop in waiting times.", "healthcare", "neutral", "blog"),
    # --- paper ---
    ("These findings provide robust evidence that the proposed intervention significantly reduces recidivism rates.", "criminal justice", "supportive", "paper"),
    ("The data reveal substantial methodological limitations in prior studies, casting doubt on prior conclusions.", "research methods", "critical", "paper"),
    ("Results were inconclusive, with some subgroups showing benefit and others showing no measurable effect.", "clinical trial", "ambiguous", "paper"),
    ("Table 2 presents the baseline characteristics of the 4,821 participants enrolled in the study.", "research", "neutral", "paper"),
    # --- transcript ---
    ("This initiative is exactly what communities have been demanding and it delivers real, measurable results.", "community program", "supportive", "transcript"),
    ("The proposal as written would increase costs without delivering any of the promised improvements.", "policy proposal", "critical", "transcript"),
    ("I see valid points on both sides and I'm not sure we have enough evidence to draw firm conclusions yet.", "policy", "ambiguous", "transcript"),
    ("The chair confirmed the vote will take place at the next scheduled meeting on the 18th.", "governance", "neutral", "transcript"),
    # --- book ---
    ("The reforms dramatically improved living standards for the working poor and stand as one of the era's great achievements.", "social reform", "supportive", "book"),
    ("The policy proved disastrously short-sighted, triggering the very economic crisis it had been designed to prevent.", "economic policy", "critical", "book"),
    ("Historians have interpreted the decision variously as visionary pragmatism and reckless opportunism.", "historical decision", "ambiguous", "book"),
    ("Parliament debated the measure for three sessions before passing it into law on 14 March 1906.", "legislation", "neutral", "book"),
    # --- note ---
    ("Great outcome — client confirmed they're happy to proceed with the full scope as proposed.", "project", "supportive", "note"),
    ("Vendor missed the deadline again; third time this quarter, immediate escalation required.", "vendor management", "critical", "note"),
    ("Legal flagged two issues with the indemnity clause; may affect timeline and overall budget.", "contract", "ambiguous", "note"),
    ("Call scheduled for Thursday 14:00; agenda items and dial-in details attached below.", "meeting", "neutral", "note"),
]


def load_claim_dataset(
    data_dir: Optional[Path] = None,
) -> List[Tuple[str, int, str]]:
    """Load claim detection examples as (text, is_claim, source_type) triples.

    Reads from ``data_dir/claims.parquet`` when available (produced by #109),
    otherwise returns the synthetic bootstrap set.
    """
    if data_dir:
        parquet_path = Path(data_dir) / "claims.parquet"
        if parquet_path.exists():
            import pandas as pd
            df = pd.read_parquet(parquet_path)
            source_types = (
                df["source_type"].tolist()
                if "source_type" in df.columns
                else ["news"] * len(df)
            )
            return list(zip(
                df["text"].tolist(),
                df["is_claim"].astype(int).tolist(),
                source_types,
            ))

    return list(_CLAIM_EXAMPLES)


def load_stance_dataset(
    data_dir: Optional[Path] = None,
) -> List[Tuple[str, str, str, str]]:
    """Load stance classification examples as (text, topic, stance, source_type) 4-tuples.

    Reads from ``data_dir/stance.parquet`` when available (produced by #109),
    otherwise returns the synthetic bootstrap set.
    """
    if data_dir:
        parquet_path = Path(data_dir) / "stance.parquet"
        if parquet_path.exists():
            import pandas as pd
            df = pd.read_parquet(parquet_path)
            source_types = (
                df["source_type"].tolist()
                if "source_type" in df.columns
                else ["news"] * len(df)
            )
            return list(zip(
                df["text"].tolist(),
                df["topic"].tolist(),
                df["stance"].tolist(),
                source_types,
            ))

    return list(_STANCE_EXAMPLES)


# ---------------------------------------------------------------------------
# Frame label constants (multi-label; a document can carry multiple frames)
# ---------------------------------------------------------------------------

FRAME_LABELS = ["economic", "security", "humanitarian", "legal", "political", "scientific", "other"]
FRAME2ID = {f: i for i, f in enumerate(FRAME_LABELS)}
ID2FRAME = {i: f for f, i in FRAME2ID.items()}


# ---------------------------------------------------------------------------
# Frame classification bootstrap data
# (text, source_type, active_frames)
# ---------------------------------------------------------------------------

_FRAME_EXAMPLES: List[Tuple[str, str, List[str]]] = [
    # --- economic ---
    ("Markets fell sharply as inflation data showed consumer prices rose 4.1% last month.", "news", ["economic"]),
    ("The central bank raised rates by 50bp, its largest single hike in two decades, to combat inflation.", "news", ["economic"]),
    ("GDP contracted 0.3% in Q2 as higher borrowing costs weighed on consumer spending and investment.", "news", ["economic"]),
    ("The trade deficit widened to a record $98bn as import costs outpaced export revenues.", "news", ["economic"]),
    ("After breaking down the company's Q3 earnings, margin compression is brutal — down to 8% from 14%.", "blog", ["economic"]),
    ("Our economic model forecasts a 2.3% contraction under the proposed tariff regime.", "paper", ["economic", "scientific"]),
    ("The CFO confirmed revenue came in at $4.2 billion, up 12% year-on-year, beating analyst consensus.", "transcript", ["economic"]),
    ("By 1932, the unemployment rate had reached 25%, devastating household incomes across the industrial north.", "book", ["economic", "humanitarian"]),
    ("Budget approved at $2.4M — finance team to liaise with legal on procurement compliance.", "note", ["economic", "legal"]),
    # --- security ---
    ("Military forces launched a coordinated strike against extremist infrastructure in the region.", "news", ["security"]),
    ("The government confirmed a sophisticated cyberattack breached critical infrastructure networks.", "news", ["security"]),
    ("Pentagon officials briefed Congress on escalating nuclear weapons development programmes in the region.", "news", ["security", "political"]),
    ("My analysis of the leaked documents suggests coordinated disinformation targeting swing districts.", "blog", ["security", "political"]),
    ("The general briefed lawmakers on escalating threats along the northern border and troop deployments.", "transcript", ["security", "political"]),
    ("The battle of November 1943 cost the division more than half its combat strength in three days.", "book", ["security"]),
    ("Security audit confirmed: 3 critical vulnerabilities found in the authentication module.", "note", ["security"]),
    # --- humanitarian ---
    ("Aid agencies warned that 2.4 million civilians face acute food insecurity following the harvest failure.", "news", ["humanitarian"]),
    ("The UN reported a record 110 million people are now forcibly displaced worldwide.", "news", ["humanitarian"]),
    ("Rights groups documented systematic abuse of asylum seekers held in overcrowded detention facilities.", "news", ["humanitarian", "legal"]),
    ("The earthquake left 80,000 people without shelter as temperatures dropped below freezing overnight.", "news", ["humanitarian"]),
    ("The intervention group showed a 41% reduction in child malnutrition indicators over 18 months.", "paper", ["humanitarian", "scientific"]),
    ("The famine of 1932–33 killed an estimated 3.5 to 7 million people across the affected regions.", "book", ["humanitarian"]),
    # --- legal ---
    ("The Supreme Court ruled 5-4 that the regulation was unconstitutional, blocking its implementation.", "news", ["legal", "political"]),
    ("A federal judge issued an injunction blocking the new immigration rules pending a full hearing.", "news", ["legal"]),
    ("The company agreed to a $4.5bn settlement to resolve antitrust litigation brought by the regulator.", "news", ["legal", "economic"]),
    ("Compliance with the new GDPR amendment requires firms to appoint a data-protection officer by March.", "blog", ["legal"]),
    ("The court held that the defendant's liability was limited by the force-majeure clause in the contract.", "paper", ["legal"]),
    ("The senator confirmed that the bill would be brought to the floor for a vote after the recess.", "transcript", ["legal", "political"]),
    ("The landmark ruling in 1954 reshaped the legal landscape for civil rights for the next half-century.", "book", ["legal", "political", "humanitarian"]),
    ("Legal confirmed the NDA has been signed; escalate to compliance team for onboarding clearance.", "note", ["legal"]),
    # --- political ---
    ("The governing coalition collapsed after junior partners withdrew following the budget vote.", "news", ["political", "economic"]),
    ("Election officials projected the incumbent would win with 54% of the popular vote.", "news", ["political"]),
    ("The foreign minister's visit is seen as a diplomatic overture ahead of bilateral trade negotiations.", "news", ["political", "economic"]),
    ("The administration's immigration reform stalled in the Senate after three moderate Democrats defected.", "news", ["political"]),
    ("I tracked every parliamentary vote on this bill — party discipline held in 94% of cases.", "blog", ["political"]),
    ("The prime minister's party lost its majority at the election, forcing an immediate confidence vote.", "transcript", ["political"]),
    ("The congress of 1848 redistributed power between the federal government and the newly formed states.", "book", ["political"]),
    # --- scientific ---
    ("Researchers published findings showing a novel compound reduced tumour size by 47% in clinical trials.", "news", ["scientific"]),
    ("The peer-reviewed study, published in Nature, identified a genetic marker linked to early-onset dementia.", "news", ["scientific"]),
    ("Our randomised controlled trial (n = 4,200) demonstrates statistically significant efficacy (p < 0.001).", "paper", ["scientific"]),
    ("The cohort study found a strong correlation (r = 0.82) between sleep duration and cognitive performance.", "paper", ["scientific"]),
    ("Gene expression analysis across 142 differentially expressed genes confirmed the hypothesised pathway.", "paper", ["scientific"]),
    ("The model correctly classified 91% of samples in the held-out test set using a random-forest ensemble.", "paper", ["scientific"]),
    ("Our simulation results replicate the observed temperature anomaly with an RMSE of 0.14°C.", "paper", ["scientific"]),
    ("The algorithm processes 50,000 tokens per second on a single A100 GPU with 4-bit quantisation.", "blog", ["scientific"]),
    # --- multi-frame ---
    ("The Pentagon's $850bn budget request faces opposition from fiscal hawks in Congress.", "news", ["economic", "security", "political"]),
    ("Sanctions imposed on the central bank triggered a currency collapse, pushing millions into poverty.", "news", ["economic", "political", "humanitarian"]),
    ("The regulation forces pharmaceutical firms to publish clinical-trial data within 12 months of completion.", "news", ["legal", "scientific"]),
    ("Aid spending rose 18% to $212bn globally, driven by conflicts in three regions.", "news", ["humanitarian", "economic"]),
    ("The court upheld the deportation order despite medical evidence of the applicant's deteriorating condition.", "news", ["legal", "humanitarian"]),
    # --- other ---
    ("The festival drew an estimated 85,000 visitors over the three-day weekend.", "news", ["other"]),
    ("My personal rule: never deploy on a Friday unless you enjoy weekend on-call shifts.", "blog", ["other"]),
    ("The tournament concluded with the home side winning 3–1 in front of a sell-out crowd.", "transcript", ["other"]),
    ("Chapter four describes the protagonist's childhood in a small farming community.", "book", ["other"]),
]


def load_frame_dataset(
    data_dir: Optional[Path] = None,
) -> List[Tuple[str, str, List[str]]]:
    """Load frame classification examples as (text, source_type, frames) triples.

    Reads from ``data_dir/frames.parquet`` when available (produced by #109),
    otherwise returns the synthetic bootstrap set.
    """
    if data_dir:
        parquet_path = Path(data_dir) / "frames.parquet"
        if parquet_path.exists():
            import json
            import pandas as pd
            df = pd.read_parquet(parquet_path)
            source_types = (
                df["source_type"].tolist()
                if "source_type" in df.columns
                else ["news"] * len(df)
            )
            frames_col = (
                [json.loads(f) if isinstance(f, str) else list(f) for f in df["frames"].tolist()]
                if "frames" in df.columns
                else [["other"]] * len(df)
            )
            return list(zip(df["text"].tolist(), source_types, frames_col))

    return list(_FRAME_EXAMPLES)
