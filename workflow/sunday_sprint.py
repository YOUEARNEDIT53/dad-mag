#!/usr/bin/env python3
"""
Dad Mag — Sunday Sprint Workflow
The full pipeline: digest → debate → polish → publish.

Usage:
  python3 sunday_sprint.py                    # Full run from live feeds
  python3 sunday_sprint.py --from-digest      # Use existing weekly_digest.json
  python3 sunday_sprint.py --test             # Generate test edition (no API needed)
"""

import json
import os
import sys
import argparse
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
DIGEST_PATH = os.path.join(PROJECT_DIR, 'weekly_digest.json')
EDITIONS_DIR = os.path.join(PROJECT_DIR, 'editions')
AGENTS_DIR = os.path.join(PROJECT_DIR, 'agents')
CONFIG_DIR = os.path.join(PROJECT_DIR, 'config')


def load_digest():
    """Load the weekly digest JSON."""
    if not os.path.exists(DIGEST_PATH):
        print("ERROR: weekly_digest.json not found. Run newsroom_sync.py first.")
        sys.exit(1)
    with open(DIGEST_PATH) as f:
        return json.load(f)


def load_style_guide():
    """Load the style guide config."""
    path = os.path.join(CONFIG_DIR, 'style_guide.json')
    with open(path) as f:
        return json.load(f)


def load_agent_prompt(agent_name):
    """Load an agent's system prompt from markdown file."""
    path = os.path.join(AGENTS_DIR, f'{agent_name}.md')
    with open(path) as f:
        return f.read()


def pick_cover_stories(digest, count=3):
    """
    Select the top N stories for cover treatment.
    Prioritize: category diversity + recency + title quality.
    """
    stories = digest.get('stories', [])
    if not stories:
        return []

    # Group by category
    by_category = {}
    for story in stories:
        cat = story.get('category', 'general')
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(story)

    # Pick one from each category first for diversity
    picks = []
    categories = list(by_category.keys())
    for cat in categories:
        if len(picks) >= count:
            break
        if by_category[cat]:
            picks.append(by_category[cat][0])

    # Fill remaining from top stories
    while len(picks) < count and len(picks) < len(stories):
        candidate = stories[len(picks)]
        if candidate not in picks:
            picks.append(candidate)

    return picks[:count]


def generate_edition_number():
    """Generate edition number based on existing editions."""
    if not os.path.exists(EDITIONS_DIR):
        os.makedirs(EDITIONS_DIR)
    existing = [f for f in os.listdir(EDITIONS_DIR) if f.startswith('edition_')]
    return len(existing) + 1


def strip_banned_phrases(text, banned_phrases):
    """Remove all banned AI-slop phrases from text."""
    cleaned = text
    for phrase in banned_phrases:
        # Case-insensitive replacement
        import re
        pattern = re.compile(re.escape(phrase), re.IGNORECASE)
        cleaned = pattern.sub('', cleaned)
    # Clean up double spaces
    cleaned = re.sub(r'  +', ' ', cleaned)
    cleaned = re.sub(r'\n\n\n+', '\n\n', cleaned)
    return cleaned.strip()


def format_sunday_edition(edition_num, date, cover_stories, spec_op_briefs,
                          professor_insights, in_law_rebuttals, gear_section,
                          back_page, style_guide):
    """Compile the final Sunday Edition markdown."""

    banned = style_guide.get('banned_phrases', [])

    md = []
    md.append(f"# Dad Mag: Sunday Edition #{edition_num:03d}")
    md.append(f"**{date}**\n")
    md.append("---\n")

    # Cover Stories with Spec-Op briefs
    md.append("## Cover Stories\n")
    for i, story in enumerate(cover_stories):
        brief = spec_op_briefs[i] if i < len(spec_op_briefs) else ""
        insight = professor_insights[i] if i < len(professor_insights) else ""
        rebuttal = in_law_rebuttals[i] if i < len(in_law_rebuttals) else ""

        md.append(f"### {i+1}. {story['title']}")
        md.append(f"*Source: {story['source']} | {story['date']}*\n")

        if brief:
            md.append("**[Spec-Op — Tactical Brief]**")
            md.append(strip_banned_phrases(brief, banned))
            md.append("")

        if insight:
            md.append("**[The Professor — The Insight]**")
            md.append(strip_banned_phrases(insight, banned))
            md.append("")

        if rebuttal:
            md.append("**[The In-Law — The Rebuttal]**")
            md.append(strip_banned_phrases(rebuttal, banned))
            md.append("")

        md.append("---\n")

    # Gear & Logistics
    if gear_section:
        md.append("## Gear & Logistics\n")
        md.append(strip_banned_phrases(gear_section, banned))
        md.append("\n---\n")

    # Back Page Humor
    if back_page:
        md.append("## Back Page Humor\n")
        md.append(strip_banned_phrases(back_page, banned))
        md.append("\n---\n")

    # Footer
    md.append("*Dad Mag is written by agents who argue over real data.*")
    md.append("*No AI slop was left in this edition.*")
    md.append(f"*Edition #{edition_num:03d} | {date}*")

    return "\n".join(md)


def run_test_edition():
    """Generate a test edition without hitting any APIs."""

    edition_num = generate_edition_number()
    date = datetime.now().strftime("%B %d, %Y")
    style_guide = load_style_guide()

    # Test cover stories (hardcoded for immediate output)
    cover_stories = [
        {
            'title': 'Warehouse Robotics See 20% Growth in Q4',
            'source': 'Supply Chain Dive',
            'category': 'logistics_tech',
            'date': '2026-01-30',
            'summary': 'Warehouse automation deployments grew 20% in Q4 2025, driven by labor shortages and same-day delivery pressure.',
            'link': 'https://www.supplychaindive.com/news/warehouse-robotics-growth-q4'
        },
        {
            'title': 'Smart Tires with Integrated Wear Sensors Hit Consumer Market',
            'source': 'IEEE Spectrum',
            'category': 'logistics_tech',
            'date': '2026-01-29',
            'summary': 'Continental and Michelin ship embedded RFID/pressure sensors in consumer tires. Fleet ROI claimed at 18 months.',
            'link': 'https://spectrum.ieee.org/smart-tires-wear-sensors'
        },
        {
            'title': 'CRISPR Gene Therapy Approved for Sickle Cell in Under-18 Patients',
            'source': 'Nature',
            'category': 'science_research',
            'date': '2026-01-28',
            'summary': 'FDA expands CRISPR-based sickle cell treatment to pediatric patients after Phase III trials show 94% efficacy.',
            'link': 'https://www.nature.com/articles/crispr-sickle-cell-pediatric'
        }
    ]

    # Spec-Op Briefs
    spec_op_briefs = [
        """Situation. Warehouse robotics deployments hit 20% growth in Q4. Primary drivers: labor cost inflation (up 8% YoY in warehouse sector) and same-day delivery mandates from Amazon, Walmart, and Target. Key players: Locus Robotics, 6 River Systems, Fetch Robotics.

Assessment. The growth is real but front-loaded. Most deployments are pick-and-pack AMRs (Autonomous Mobile Robots), not full palletizing systems. The hard problem—mixed-SKU depalletizing—remains unsolved at scale. Unit economics work at 500+ picks/hour; most facilities are running 320. The labor savings are there, but integration costs eat 40% of Year 1 ROI.

Verdict: GO, with caveats. AMR pick-assist is proven. Full automation is still 3-5 years out for mid-size operations. Don't overbuy.

BLUF: The robots work. The math works at scale. But if your warehouse runs fewer than 10,000 SKUs, a forklift and a good WMS still wins.""",

        """Situation. Continental and Michelin shipping embedded MEMS pressure + NTC thermistor sensors in consumer and fleet tires. Retail price delta: $40-60 per tire. Fleet analytics via cloud SaaS (pricing undisclosed). Consumer app: free, but data goes to OEM.

Assessment. Sensor hardware is commodity. Value is in the predictive analytics layer—blowout prevention, optimal replacement scheduling. Continental claims 34% blowout reduction in fleet trials. Problem: no offline fallback if the cloud API drops. No cross-brand interoperability. You're locked into one vendor's tire ecosystem.

Verdict: WAIT. Hardware is solid. Software stack is immature. No ISO standard for tire telemetry means vendor lock-in within 24 months.

BLUF: Good sensor, bad business model. Wait for the open standard or you're buying a subscription for your tires.""",

        """Situation. FDA greenlights CRISPR-based Casgevy (exagamglogene autotemcel) for sickle cell disease in patients under 18. Phase III data: 94% of pediatric patients achieved sustained fetal hemoglobin production at 12-month follow-up. Treatment cost: ~$2.2M per patient.

Assessment. Clinically, this is as close to a cure as it gets. Logistically, it's a nightmare. Treatment requires myeloablative conditioning (chemo to wipe bone marrow), 30+ days inpatient, and only 8 certified treatment centers in the US. Wait times are already 6-9 months for adults. Adding pediatric patients will stress an already thin pipeline. Insurance coverage remains inconsistent.

Verdict: GO from a science standpoint. NO-GO from an access standpoint for most families right now.

BLUF: The science works. The delivery system doesn't scale. Eight centers for 100,000 US patients is a bottleneck, not a breakthrough."""
    ]

    # Professor Insights
    professor_insights = [
        """We are witnessing a quiet revolution in the architecture of labor. The warehouse—once a cathedral of human sweat, of forklifts driven by men who knew every aisle by muscle memory—is becoming a ballet of silicon and precision. A Locus Robotics AMR does not take smoke breaks. It does not call in sick. It does not negotiate. And therein lies both the efficiency and the loss. What we gain in throughput, we surrender in the particular dignity of physical work that generations of men defined themselves by. The question is not whether robots will replace the warehouse worker. They will. The question is what story we tell the worker's son about what "hard work" means when the hardest labor is now performed by something that charges in a dock.""",

        """There is a profound loss of intuition happening in the modern garage. We used to check our tires with a penny and a prayer—a tactile ritual of car ownership. You pressed Lincoln's head into the groove, and if the rubber swallowed him to the ears, you had another season. Now, a sensor in the rubber communicates directly with the cloud. We are trading the "human check" for an automated notification. Continental's 34% blowout reduction is real, and it will save lives. But it further detaches us from the machines we rely on. We no longer listen to the car; we wait for the car to text us. This is not nostalgia for its own sake. The question is whether we are building a generation of drivers who cannot diagnose a shimmy at 60 mph because the dashboard never taught them to pay attention.""",

        """A cure is supposed to feel like liberation. Casgevy delivers on that promise biologically—94% of children in the trial produced enough fetal hemoglobin to break the cycle of sickle cell crises. But a $2.2 million treatment available at eight centers in a country of 330 million people is not liberation. It is a velvet rope. The families who need this most—disproportionately Black, disproportionately underinsured—face a system that has historically made them wait longest for what they need most. The science has arrived. The infrastructure has not. We are left with a familiar American paradox: we can edit a gene but we cannot build enough clinics to deliver the edit."""
    ]

    # In-Law Rebuttals
    in_law_rebuttals = [
        """Listen, Gary. A "ballet of precision"? My foot. It's a giant Roomba that's going to get stuck on a loose floorboard. The Professor over here is writing poetry about a machine that picks up boxes. You know what picks up boxes great? A guy named Doug with a bad knee and a good attitude. At least Doug knows where the 10mm socket is. Spec-Op says the "math works at scale." You know what else works at scale? A warehouse full of people who actually spend their paychecks at the businesses in their town. In the '80s, we moved freight with three guys and a truck. Nobody needed a "cloud analytics layer." These robots don't have grit. They have lithium batteries that'll explode the second someone spills a Gatorade. Meanwhile, my garage door opener has been broken for two months and nobody's deploying a robot for THAT.""",

        """Listen, Gary. I don't need my tires to "talk" to me. I have enough people talking to me. I have a wife, I have a daughter, I have a dog that won't stop barking at the mailman. Now my front-left Michelin wants to start a group chat because I hit a pothole?

The Professor is crying about "losing intuition." Intuition? It's a tire, not a Zen garden. You look at it. If it's flat, you pump it. If it's bald, you buy a new one. In the '80s, we didn't need Lincoln's head—we had eyeballs.

And Spec-Op says "wait for the ISO standard." You know what my ISO standard is? I kick the tire. If my foot hurts, the tire's fine. It's like Happy Gilmore said—the ball just wants to go home. My tire just wants to roll. Stop making it complicated. And while we're at it, my TV remote needs four buttons, not forty-seven. Fix THAT first.""",

        """Listen, Gary. Two point two MILLION dollars. Per kid. You know what I could do with $2.2 million? I could fix every pothole between here and Tallahassee. The Professor says we can "edit a gene but can't build enough clinics." Yeah, no kidding. It's like Step Brothers—there's so much room for activities, but nobody can agree on who gets the top bunk.

Spec-Op calls it a "bottleneck." Where I come from, we call that a line. And in the '80s, if there was a line, you waited in it, and you didn't need eight certified centers—you needed one doctor who answered his phone.

I'm not saying the science is bad. I'm saying somebody needs to figure out the parking lot before they open the mall. You know what also needs $2.2 million in upgrades? The sprinkler system in my front yard. It waters the sidewalk. The SIDEWALK, Gary."""
    ]

    # Gear & Logistics Section
    gear_section = """**Spec-Op's Pick: The Milwaukee M18 FUEL Compact Router**
Price: $199 (tool only) | Weight: 4.6 lbs | Battery: M18 RedLithium

This is not a "smart" tool. It does not connect to Wi-Fi. It does not have an app. It routes wood. The variable speed dial goes from 10,000 to 31,000 RPM, and the brushless motor means it won't burn out mid-dado.

TCO analysis: Comparable to the DeWalt DCW600B at $199, but the M18 battery ecosystem gives it an edge if you're already invested in Milwaukee. Dust collection port actually works—tested at 80% debris capture with the included attachment.

Verdict: GO. If you need a cordless router that doesn't try to be your friend, this is it.

*Source: Popular Mechanics tool test, January 2026*"""

    # Back Page Humor
    back_page = """### THE IN-LAW'S GARAGE REPORT

**This Week's Complaint: The Thermostat**

Listen, I'm not a complicated man. I want two things from my house: cold beer and warm rooms. Apparently, this is too much to ask.

My daughter bought me one of those "smart" thermostats for Christmas. The Nest. Or the Hive. Or whatever it's called—it looks like a hockey puck glued to my wall. She says it "learns my preferences." It's been six weeks. It has learned NOTHING.

Tuesday night, 2 AM, I wake up and it's 82 degrees in the bedroom. The thermostat decided I "prefer" tropical conditions because I cooked pasta at 7 PM and the kitchen got warm. That's not learning. That's stalking.

In the '80s, you had a dial. You turned it to 68. It stayed at 68. Nobody was "learning" anything. The furnace didn't have opinions.

You want to know what happened to that hockey puck? It's in the junk drawer now. Right next to the three remotes that don't work, the Allen wrenches from IKEA, and my dignity.

I put the old dial thermostat back up. It took four screws and zero apps. Problem solved.

Until next week, Gary.

*— The In-Law*"""

    # Compile edition
    edition_md = format_sunday_edition(
        edition_num=edition_num,
        date=date,
        cover_stories=cover_stories,
        spec_op_briefs=spec_op_briefs,
        professor_insights=professor_insights,
        in_law_rebuttals=in_law_rebuttals,
        gear_section=gear_section,
        back_page=back_page,
        style_guide=style_guide
    )

    # Save
    filename = f"edition_{edition_num:03d}_{datetime.now().strftime('%Y-%m-%d')}.md"
    filepath = os.path.join(EDITIONS_DIR, filename)
    os.makedirs(EDITIONS_DIR, exist_ok=True)
    with open(filepath, 'w') as f:
        f.write(edition_md)

    print(f"\nTest edition saved: {filepath}")
    print(f"Edition #{edition_num:03d} — {date}")
    return filepath


def run_full_sprint():
    """
    Full Sunday Sprint:
    1. Load digest
    2. Pick cover stories
    3. Run each agent (requires Claude API)
    4. Polish and publish
    """
    digest = load_digest()
    style_guide = load_style_guide()
    cover_stories = pick_cover_stories(digest, count=3)

    if not cover_stories:
        print("ERROR: No cover stories found in digest.")
        sys.exit(1)

    print(f"Selected {len(cover_stories)} cover stories:")
    for i, story in enumerate(cover_stories, 1):
        print(f"  {i}. [{story['category']}] {story['title']}")
        print(f"     Source: {story['source']} | {story['date']}")

    print("\n--- AGENT PROMPTS READY ---")
    print("Feed these stories to your agents via Claude Code:")
    print()
    print('claude "Read weekly_digest.json. Have [Spec-Op] pick the 3 most impactful')
    print('logistics stories. Have [Professor] write an MFA-style intro for each.')
    print('Then have [The-In-Law] write a 1-paragraph rebuttal for each using his')
    print("'Father-in-Law' persona. Output the final 'Dad Mag: Sunday Edition' in Markdown.\"")
    print()

    # Output the selected stories for agent consumption
    brief_path = os.path.join(PROJECT_DIR, 'cover_brief.json')
    with open(brief_path, 'w') as f:
        json.dump({
            'edition_date': datetime.now().strftime("%Y-%m-%d"),
            'cover_stories': cover_stories,
            'trending_themes': digest.get('trending_themes', [])[:5],
            'style_guide': style_guide
        }, f, indent=2)

    print(f"Cover brief saved: {brief_path}")
    return cover_stories


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dad Mag Sunday Sprint")
    parser.add_argument('--test', action='store_true', help='Generate test edition')
    parser.add_argument('--from-digest', action='store_true', help='Use existing digest')
    args = parser.parse_args()

    if args.test:
        run_test_edition()
    elif args.from_digest:
        run_full_sprint()
    else:
        # Full pipeline: scrape then sprint
        print("Running full pipeline: scrape → sprint\n")
        sys.path.insert(0, PROJECT_DIR)
        from newsroom_sync import load_sources, scrape_feeds, rank_stories, generate_theme_suggestions
        sources = load_sources(OPML_PATH)
        raw_digest, errors = scrape_feeds(sources)
        ranked = rank_stories(raw_digest)
        themes = generate_theme_suggestions(ranked)

        output = {
            'metadata': {
                'scraped_at': datetime.now().isoformat(),
                'sources_attempted': len(sources),
                'stories_collected': len(ranked)
            },
            'trending_themes': themes,
            'stories': ranked,
            'errors': errors
        }
        with open(DIGEST_PATH, 'w') as f:
            json.dump(output, f, indent=2)

        print(f"\nDigest ready: {len(ranked)} stories")
        run_full_sprint()
