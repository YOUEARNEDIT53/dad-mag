#!/usr/bin/env python3
"""
Dad Mag — Fitness Edition Generator (v3)
7-voice Writer's Room: Coach Dave, Dr. Ortho, Nutritionist, Coach Jim, Dr. Chen, Sloane, Average Dad
Health & fitness magazine for dads. Like Men's Health with personality.

Usage:
  python3 generate_edition.py                  # Generate from digest
  python3 generate_edition.py --stories 3      # Override story count
  python3 generate_edition.py --fresh           # Re-scrape RSS first
  python3 generate_edition.py --theme "Thanksgiving"   # Holiday/theme for every writer
"""

import json
import os
import re
import sys
import argparse
import subprocess
from datetime import datetime

try:
    import anthropic
except ImportError:
    print("ERROR: anthropic package not installed. Run: pip install anthropic")
    sys.exit(1)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
DIGEST_PATH = os.path.join(PROJECT_DIR, 'weekly_digest.json')
EDITIONS_DIR = os.path.join(PROJECT_DIR, 'editions')
AGENTS_DIR = os.path.join(PROJECT_DIR, 'agents')
CONFIG_DIR = os.path.join(PROJECT_DIR, 'config')
USED_STORIES_PATH = os.path.join(PROJECT_DIR, 'used_stories.json')
# Cover-story titles from every past edition; used to block repeat topics, not just repeat links.
USED_TOPICS_PATH = os.path.join(PROJECT_DIR, 'used_topics.json')

MODEL = "claude-sonnet-4-6"

# Set from --theme in __main__; appended to every writer's instructions.
THEME = ""
# Filled with this week's source list in __main__ so writers stay on the sources.
GROUNDING = ""

STOPWORDS = set("""the a an and or of to in on for with from by at as is are was be this that your you
new study says may can how why what more than into after about over just like its their it his her
could would should will dads dad men man year years""".split())


def load_file(path):
    with open(path) as f:
        return f.read()


def load_json(path):
    with open(path) as f:
        return json.load(f)


def get_client():
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        env_path = os.path.join(PROJECT_DIR, '.env')
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if line.startswith('ANTHROPIC_API_KEY='):
                        api_key = line.strip().split('=', 1)[1].strip('"').strip("'")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not found in environment or .env")
        sys.exit(1)
    return anthropic.Anthropic(api_key=api_key)


def load_used_stories():
    if os.path.exists(USED_STORIES_PATH):
        with open(USED_STORIES_PATH) as f:
            return set(json.load(f))
    return set()


def save_used_stories(used_ids):
    ids_list = list(used_ids)[-500:]
    with open(USED_STORIES_PATH, 'w') as f:
        json.dump(ids_list, f, indent=2)


def keywords(text):
    words = re.findall(r"[a-z][a-z'-]{3,}", text.lower())
    return {w for w in words if w not in STOPWORDS}


def load_used_topics():
    """Past cover-story titles. Seeded from the editions folder the first time."""
    if os.path.exists(USED_TOPICS_PATH):
        with open(USED_TOPICS_PATH) as f:
            return json.load(f)
    topics = []
    if os.path.exists(EDITIONS_DIR):
        for name in sorted(os.listdir(EDITIONS_DIR)):
            if name.startswith('edition_') and name.endswith('.md'):
                with open(os.path.join(EDITIONS_DIR, name)) as f:
                    for line in f:
                        m = re.match(r'###\s+\d+\.\s+(.+)', line)
                        if m:
                            topics.append(m.group(1).strip())
    return list(dict.fromkeys(topics))


def save_used_topics(topics):
    with open(USED_TOPICS_PATH, 'w') as f:
        json.dump(topics, f, indent=2)


def is_recycled(story, past_topics):
    """True if the story covers the same ground as a past cover story (shared keywords)."""
    kw = keywords(story['title'])
    for past in past_topics:
        pkw = keywords(past)
        overlap = kw & pkw
        if len(overlap) >= 3 or (pkw and len(overlap) / len(kw | pkw) >= 0.4):
            return True
    return False


def pick_stories(client, digest, count=3):
    """Pick cover stories only from this week's sources, never repeating a past topic.

    Never falls back to recycled stories: if the scrape is thin, the edition runs fewer covers.
    """
    stories = digest.get('stories', [])
    used = load_used_stories()
    past_topics = load_used_topics()
    fresh = [s for s in stories if s.get('id') not in used and not is_recycled(s, past_topics)]
    print(f"  {len(stories)} scraped, {len(fresh)} not previously covered")
    if not fresh:
        print("ERROR: no fresh stories in this week's sources. Not publishing a recycled edition.")
        sys.exit(1)

    # Let an editor pick on-beat health/fitness stories (feeds include off-topic noise).
    listing = "\n".join(f"{i}. [{s.get('category','')}] {s['title']} ({s['source']}): {s.get('summary','')[:160]}"
                        for i, s in enumerate(fresh))
    theme_line = f"\nThis edition's theme: {THEME}. Prefer stories a writer can tie to it naturally." if THEME else ""
    prompt = f"""You are the managing editor of Dad Mag, a health & fitness magazine for dads aged 35-50.
Pick the {count} best cover stories from this week's sources below. Rules:
- Must be about health, fitness, training, nutrition, sleep, or mental health. Skip business, tech, and celebrity news.
- The {count} picks must cover {count} clearly different topics.
- Prefer stories with real evidence (a study, trial, or data) and a practical takeaway for dads.{theme_line}

STORIES:
{listing}

Reply with only the numbers of your picks, comma-separated, best first."""
    response = client.messages.create(model=MODEL, max_tokens=50,
                                      messages=[{"role": "user", "content": prompt}])
    nums = [int(n) for n in re.findall(r"\d+", response.content[0].text)]
    picks = []
    for n in nums:
        if 0 <= n < len(fresh) and fresh[n] not in picks:
            picks.append(fresh[n])
    if not picks:
        picks = fresh[:count]
    return picks[:count]


def run_agent(client, agent_name, system_prompt, user_prompt, max_tokens=1000):
    print(f"  Running [{agent_name}]...", end=" ", flush=True)
    if GROUNDING:
        system_prompt = system_prompt + "\n\n" + GROUNDING
    response = client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}]
    )
    result = response.content[0].text
    print(f"OK ({len(result)} chars)")
    return result


# === THE 7 FITNESS VOICES ===

def run_coach_dave_letter(client, stories):
    system = load_file(os.path.join(AGENTS_DIR, 'coach_dave.md'))
    titles = "\n".join(f"- {s['title']} ({s['source']}): {s.get('summary','')[:100]}" for s in stories)
    prompt = f"""Write the Editor's Letter for this week's Dad Mag (150-200 words).

THIS WEEK'S COVER STORIES:
{titles}

This is a fitness & health magazine for dads. Set the tone. Find the thread that connects these health stories to fatherhood, training, or showing up. Write in your voice. End with a line that makes the reader want to keep going."""
    return run_agent(client, "Coach Dave (Letter)", system, prompt, max_tokens=500)


def run_dr_ortho(client, stories):
    system = load_file(os.path.join(AGENTS_DIR, 'dr_ortho.md'))
    assessments = []
    for story in stories:
        prompt = f"""Write your Tactical Assessment (200 words max) of this health/fitness story.

STORY:
Title: {story['title']}
Source: {story['source']}
Date: {story['date']}
Summary: {story['summary']}
Link: {story['link']}

Analyze the clinical evidence. What's the mechanism? Is the study design solid? What's actionable for a 35-50 year old dad?
Structure: Mechanism -> Evidence -> Protocol -> Field Verdict (DEPLOY / STAND DOWN / WAIT)"""
        assessment = run_agent(client, "Dr. Ortho", system, prompt, max_tokens=500)
        assessments.append(assessment)
    return assessments


def run_nutritionist(client, stories, ortho_assessments):
    system = load_file(os.path.join(AGENTS_DIR, 'nutritionist.md'))
    takes = []
    for i, story in enumerate(stories):
        ortho = ortho_assessments[i] if i < len(ortho_assessments) else ""
        prompt = f"""Write your take (150-200 words) on the nutrition/supplementation angle of this story.

STORY:
Title: {story['title']}
Source: {story['source']}
Summary: {story['summary']}

DR. ORTHO'S ASSESSMENT:
{ortho}

What does this mean for diet, nutrition, or supplementation? Give specific quantities, foods, or doses. Fact-check any supplement claims. Be practical — what should a dad buy or eat? What should he skip?"""
        take = run_agent(client, "Nutritionist", system, prompt, max_tokens=500)
        takes.append(take)
    return takes


def run_coach_jim(client, stories, ortho_assessments):
    system = load_file(os.path.join(AGENTS_DIR, 'coach_jim.md'))
    takes = []
    for i, story in enumerate(stories):
        ortho = ortho_assessments[i] if i < len(ortho_assessments) else ""
        prompt = f"""React to this story (50-100 words). How does it apply to training? What would you change in programming?

STORY: {story['title']}
Summary: {story['summary']}

DR. ORTHO SAID:
{ortho}

Keep it short. Bring it back to the rack."""
        take = run_agent(client, "Coach Jim", system, prompt, max_tokens=300)
        takes.append(take)
    return takes


def run_dr_chen(client, stories, ortho_assessments):
    system = load_file(os.path.join(AGENTS_DIR, 'dr_chen.md'))
    takes = []
    for i, story in enumerate(stories):
        ortho = ortho_assessments[i] if i < len(ortho_assessments) else ""
        prompt = f"""Write your take (150-200 words) on the mental/psychological angle of this story.

STORY: {story['title']}
Source: {story['source']}
Summary: {story['summary']}

DR. ORTHO'S ASSESSMENT:
{ortho}

What's the mental game here? Why do dads struggle with this? What's the psychological barrier or opportunity? End with a reframe or one insight that sticks."""
        take = run_agent(client, "Dr. Chen", system, prompt, max_tokens=500)
        takes.append(take)
    return takes


def run_sloane(client, stories, ortho_assessments):
    system = load_file(os.path.join(AGENTS_DIR, 'sloane.md'))
    takes = []
    for i, story in enumerate(stories):
        ortho = ortho_assessments[i] if i < len(ortho_assessments) else ""
        prompt = f"""Give your take (100-150 words) on this story. What's trending? What products are moving? What's the aesthetic/cultural angle in wellness right now?

STORY: {story['title']}
Source: {story['source']}
Summary: {story['summary']}

DR. ORTHO SAID:
{ortho}

Find the trend underneath the data. Comment on branding, products, and what your audience would care about. Be yourself."""
        take = run_agent(client, "Sloane", system, prompt, max_tokens=400)
        takes.append(take)
    return takes


def run_average_dad(client, stories, ortho_assessments, nutritionist_takes, sloane_takes):
    system = load_file(os.path.join(AGENTS_DIR, 'average_dad.md'))
    rebuttals = []
    for i, story in enumerate(stories):
        ortho = ortho_assessments[i] if i < len(ortho_assessments) else ""
        nutri = nutritionist_takes[i] if i < len(nutritionist_takes) else ""
        sloane = sloane_takes[i] if i < len(sloane_takes) else ""
        prompt = f"""Write your Rebuttal (100-150 words).

STORY: {story['title']}
Summary: {story['summary']}

DR. ORTHO SAID: {ortho[:200]}
NUTRITIONIST SAID: {nutri[:200]}
SLOANE SAID: {sloane[:200]}

React to everyone. How much does this cost vs your 4Runner maintenance? Is this real or is this wellness nonsense? Reference a movie. End with a household grievance."""
        rebuttal = run_agent(client, "Average Dad", system, prompt, max_tokens=400)
        rebuttals.append(rebuttal)
    return rebuttals


def run_average_dad_column(client, stories):
    system = load_file(os.path.join(AGENTS_DIR, 'average_dad.md'))
    story = stories[0]
    prompt = f"""Write your standalone column (200-300 words). You encountered this week's health/fitness topic in real life.

THIS WEEK'S LEAD STORY: {story['title']}
Summary: {story['summary']}

Maybe you went to a wellness pop-up. Maybe someone at the gym told you about a supplement. Maybe your wife sent you an article. Write the rant. Quote Happy Gilmore. End with a grievance about your house or your 4Runner."""
    return run_agent(client, "Average Dad (Column)", system, prompt, max_tokens=600)


def run_coach_jim_programming(client):
    system = load_file(os.path.join(AGENTS_DIR, 'coach_jim.md'))
    week_date = datetime.now().strftime("%B %d, %Y")
    prompt = f"""Write this week's 3-Day Father's Rack programming (week of {week_date}).

Three days. Forty-five minutes. No machines. No cables. No excuses. You need: a barbell, a rack, plates, and a pull-up bar.

Write the full program:
- MONDAY (Push or Full Body)
- WEDNESDAY (Pull or Full Body)
- FRIDAY (Legs & Carry)

Include: exercise name, sets x reps, rest periods. Add a progression scheme. Keep it simple. The rack doesn't negotiate."""
    return run_agent(client, "Coach Jim (Programming)", system, prompt, max_tokens=800)


def run_coach_dave_essay(client, stories):
    system = load_file(os.path.join(AGENTS_DIR, 'coach_dave.md'))
    story = stories[0]
    prompt = f"""Write the Back Page essay (200-300 words). Personal. Specific. Earned.

THIS WEEK'S LEAD STORY: {story['title']}

Don't write about the story directly. Find the human thread underneath: a specific, new moment from this week, not an image you have used before. Connect it to the project of staying strong for the people who need you. Title it something simple. End with an image that lingers."""
    return run_agent(client, "Coach Dave (Essay)", system, prompt, max_tokens=600)


def run_chief(client, edition_draft, style_guide):
    system = load_file(os.path.join(AGENTS_DIR, 'chief.md'))
    banned = json.dumps(style_guide.get('banned_phrases', []))
    prompt = f"""Final editorial review of this Dad Mag fitness edition.

BANNED PHRASES (remove ALL):
{banned}

DRAFT EDITION:
{edition_draft}

Clean this edition:
1. Strip every banned phrase
2. Active voice throughout
3. Verify each voice is distinct: Dr. Ortho is clinical-blunt, Nutritionist is precise, Coach Jim is minimal, Dr. Chen is warm, Sloane is trendy, Average Dad is skeptical, Coach Dave is stoic
4. This is a FITNESS magazine — every section should connect to health, training, nutrition, or wellness
5. Output the final clean Markdown. Keep ALL section headers and voice tags."""
    return run_agent(client, "Chief", system, prompt, max_tokens=10000)


def compile_edition(edition_num, date, stories, editor_letter, ortho_assessments,
                    nutritionist_takes, coach_jim_takes, dr_chen_takes, sloane_takes,
                    dad_rebuttals, dad_column, jim_programming, dave_essay):
    md = []
    md.append(f"# Dad Mag: Sunday Edition #{edition_num:03d}")
    md.append(f"## The Independent Fitness Weekly for Men Who Show Up")
    md.append(f"**{date}**\n")
    md.append("---\n")

    md.append("**MASTHEAD**\n")
    md.append("*Editor-at-Large:* Coach Dave | *Clinical Director:* Dr. Ortho | *Nutrition Editor:* The Nutritionist | *Strength Editor:* Coach Jim | *Sports Psych:* Dr. Chen | *Trends & Culture:* Sloane | *Reader Ombudsman:* The Average Dad\n")
    md.append("*59-Source Intelligence Feed | No sponsors. No AI-slop. No tapestries.*\n")
    md.append("---\n")

    # I. Editor's Letter
    md.append("## I. Editor's Letter\n")
    md.append("**By Coach Dave**\n")
    md.append(editor_letter)
    md.append("\n---\n")

    # II. Cover Stories — all voices debate
    md.append("## II. Cover Stories\n")
    for i, story in enumerate(stories):
        md.append(f"### {i+1}. {story['title']}")
        md.append(f"*Source: {story['source']} | {story['date']}*\n")

        if i < len(ortho_assessments):
            md.append("**[Dr. Ortho -- Tactical Assessment]**")
            md.append(ortho_assessments[i])
            md.append("")

        if i < len(nutritionist_takes):
            md.append("**[The Nutritionist -- The Mechanism]**")
            md.append(nutritionist_takes[i])
            md.append("")

        if i < len(dr_chen_takes):
            md.append("**[Dr. Chen -- The Mind Game]**")
            md.append(dr_chen_takes[i])
            md.append("")

        if i < len(coach_jim_takes):
            md.append("**[Coach Jim -- Application]**")
            md.append(coach_jim_takes[i])
            md.append("")

        if i < len(sloane_takes):
            md.append("**[Sloane -- The Take]**")
            md.append(sloane_takes[i])
            md.append("")

        if i < len(dad_rebuttals):
            md.append("**[The Average Dad -- The Rebuttal]**")
            md.append(dad_rebuttals[i])
            md.append("")

        md.append("---\n")

    # III. Coach Jim's Programming
    md.append("## III. Coach Jim's Programming: The 3-Day Father's Rack\n")
    md.append(jim_programming)
    md.append("\n---\n")

    # IV. Average Dad Column
    md.append("## IV. The Average Dad Column\n")
    md.append(dad_column)
    md.append("\n---\n")

    # V. Back Page Essay
    md.append("## V. Back Page Essay -- Coach Dave\n")
    md.append(dave_essay)
    md.append("\n---\n")

    md.append("*Dad Mag is written by seven agents who argue over real health data.*")
    md.append("*No AI-slop was left in this edition.*")
    md.append(f"*Edition #{edition_num:03d} | {date}*")
    md.append('*"No sponsors. No tapestries. Just the rack and the truth."*')

    return "\n".join(md)


def save_edition(content, edition_num):
    os.makedirs(EDITIONS_DIR, exist_ok=True)
    filename = f"edition_{edition_num:03d}_{datetime.now().strftime('%Y-%m-%d')}.md"
    filepath = os.path.join(EDITIONS_DIR, filename)
    with open(filepath, 'w') as f:
        f.write(content)
    return filepath


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dad Mag Fitness Edition Generator")
    parser.add_argument('--stories', type=int, default=3, help='Number of cover stories')
    parser.add_argument('--skip-chief', action='store_true', help='Skip editorial polish')
    parser.add_argument('--fresh', action='store_true', help='Re-scrape RSS feeds before generating')
    parser.add_argument('--theme', default='', help='Theme every writer works in, e.g. "Thanksgiving"')
    args = parser.parse_args()
    THEME = args.theme

    print("=" * 60)
    print("DAD MAG -- WRITER'S ROOM (v3: 7 Fitness Voices)")
    print("=" * 60)

    if args.fresh:
        print("\n[PRE-FLIGHT] Scraping fresh health & fitness RSS feeds...")
        sync_script = os.path.join(PROJECT_DIR, 'newsroom_sync.py')
        result = subprocess.run([sys.executable, sync_script], cwd=PROJECT_DIR)
        if result.returncode != 0:
            print("WARNING: Feed scrape had errors, continuing with available data")
        print()

    digest = load_json(DIGEST_PATH)
    style_guide = load_json(os.path.join(CONFIG_DIR, 'style_guide.json'))

    client = get_client()

    stories = pick_stories(client, digest, args.stories)
    print(f"\nCover Stories Selected:")
    for i, s in enumerate(stories, 1):
        print(f"  {i}. {s['title']} ({s['source']}) [{s['category']}]")

    past_topics = load_used_topics()
    sources = "\n".join(f"- {s['title']} ({s['source']}, {s.get('date','')}): {s.get('summary','')[:300]}"
                        for s in stories)
    recent_past = "\n".join(f"- {t}" for t in past_topics[-40:]) or "- (none)"
    GROUNDING = f"""EDITION RULES (apply to everything you write):
- Draw your material from THIS WEEK'S SOURCES below. Do not bring in studies, products, or news that are not in them, and do not invent statistics.
- Do not repeat topics, stories, anecdotes, or signature images from past editions. Past cover topics:
{recent_past}
- Find something new to say; vary your openings and examples from week to week.

THIS WEEK'S SOURCES:
{sources}"""
    if THEME:
        GROUNDING += f"""

THEME: This edition goes out {datetime.now().strftime('%A, %B %d, %Y')}. Theme: {THEME}. Tie your piece to it in your own voice (the holiday, the food, family, travel, the long weekend) while staying grounded in the sources above. Keep it natural, not gimmicky."""

    # === THE 7-VOICE FITNESS DEBATE ===
    print("\n--- THE WRITER'S ROOM ---")

    print("\nStep 1: Coach Dave's Editor's Letter")
    editor_letter = run_coach_dave_letter(client, stories)

    print("\nStep 2: Dr. Ortho's clinical assessments")
    ortho_assessments = run_dr_ortho(client, stories)

    print("\nStep 3: Nutritionist's analysis")
    nutritionist_takes = run_nutritionist(client, stories, ortho_assessments)

    print("\nStep 4: Coach Jim's training application")
    coach_jim_takes = run_coach_jim(client, stories, ortho_assessments)

    print("\nStep 5: Dr. Chen's mental game")
    dr_chen_takes = run_dr_chen(client, stories, ortho_assessments)

    print("\nStep 6: Sloane's trend takes")
    sloane_takes = run_sloane(client, stories, ortho_assessments)

    print("\nStep 7: Average Dad's rebuttals")
    dad_rebuttals = run_average_dad(client, stories, ortho_assessments, nutritionist_takes, sloane_takes)

    print("\nStep 8: Average Dad's standalone column")
    dad_column = run_average_dad_column(client, stories)

    print("\nStep 9: Coach Jim's weekly programming")
    jim_programming = run_coach_jim_programming(client)

    print("\nStep 10: Coach Dave's Back Page essay")
    dave_essay = run_coach_dave_essay(client, stories)

    # Compile
    existing = [f for f in os.listdir(EDITIONS_DIR)] if os.path.exists(EDITIONS_DIR) else []
    edition_num = len([f for f in existing if f.startswith('edition_')]) + 1
    date = datetime.now().strftime("%B %d, %Y")

    draft = compile_edition(edition_num, date, stories, editor_letter, ortho_assessments,
                            nutritionist_takes, coach_jim_takes, dr_chen_takes, sloane_takes,
                            dad_rebuttals, dad_column, jim_programming, dave_essay)

    if not args.skip_chief:
        print("\nStep 11: Chief editorial polish")
        final = run_chief(client, draft, style_guide)
    else:
        final = draft

    # Chief sometimes appends its QA checklist and writers use H1s; neither belongs in the email.
    final = re.split(r'\n-*\s*\n?## Editorial Quality Check', final)[0].rstrip() + '\n'
    final_lines = final.split('\n')
    final = '\n'.join(final_lines[:1] + [re.sub(r'^# ', '#### ', l) for l in final_lines[1:]])
    if THEME:
        final = final.replace('Sunday Edition', f'{args.theme.split(" (")[0]} Special Edition', 1)

    filepath = save_edition(final, edition_num)

    used = load_used_stories()
    for s in stories:
        used.add(s['id'])
    save_used_stories(used)
    save_used_topics(past_topics + [s['title'] for s in stories if s['title'] not in past_topics])

    print(f"\n{'=' * 60}")
    print(f"EDITION PUBLISHED: {filepath}")
    print(f"Used stories tracked: {len(used)} total")
    print(f"{'=' * 60}")
