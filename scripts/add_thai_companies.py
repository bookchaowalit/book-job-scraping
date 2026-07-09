#!/usr/bin/env python3
"""
Add Thai tech companies to contact_emails.json and apply_tracker.csv.
Compiled from web research of Thai tech company career pages.
"""
import json
import csv
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
CONTACT_FILE = os.path.join(BASE, '..', 'data', 'contact_emails.json')
TRACKER_FILE = os.path.join(BASE, '..', 'data', 'apply_tracker.csv')

# ── Thai tech companies with career emails ──────────────────────────
# Format: { "Company Name": { "domain": "...", "emails": [...], "source": "..." } }
THAI_COMPANIES = {
    # ── Major Tech / Platform Companies ──
    "Agoda": {
        "domain": "agoda.com",
        "emails": ["careers@agoda.com"],
        "best": "careers@agoda.com",
        "source": "careersatagoda.com",
        "urls_tried": ["careersatagoda.com", "job-boards.greenhouse.io/agoda"],
    },
    "LINE MAN Wongnai": {
        "domain": "lmwn.com",
        "emails": ["careers@lmwn.com"],
        "best": "careers@lmwn.com",
        "source": "careers.lmwn.com",
    },
    "Shopee Thailand": {
        "domain": "shopee.co.th",
        "emails": ["careers.th@shopee.com"],
        "best": "careers.th@shopee.com",
        "source": "careers.shopee.co.th",
    },
    "Grab Thailand": {
        "domain": "grab.com",
        "emails": ["careers@grab.com"],
        "best": "careers@grab.com",
        "source": "grab.careers",
    },
    "Lazada Thailand": {
        "domain": "lazada.com",
        "emails": ["careers@lazada.com"],
        "best": "careers@lazada.com",
        "source": "lazada.com/careers",
    },

    # ── Fintech / Blockchain ──
    "Bitkub Capital": {
        "domain": "bitkub.com",
        "emails": ["change.the.world@bitkub.com"],
        "best": "change.the.world@bitkub.com",
        "source": "careers.bitkub.com",
    },
    "BTSE": {
        "domain": "btse.com",
        "emails": ["careers@btse.com"],
        "best": "careers@btse.com",
        "source": "btse.com/careers",
    },

    # ── Bank Tech Arms ──
    "KBTG (Kasikorn Business-Technology Group)": {
        "domain": "kbtg.tech",
        "emails": ["recruitment@kbtg.tech"],
        "best": "recruitment@kbtg.tech",
        "source": "kbtg.tech + Bitkub careers FB post",
    },
    "SCB 10X (Siam Commercial Bank)": {
        "domain": "scb10x.com",
        "emails": ["careers@scb10x.com"],
        "best": "careers@scb10x.com",
        "source": "scb10x.com + scbx.com/career",
    },
    "Bangkok Bank (Tech Recruitment)": {
        "domain": "ttbbank.com",
        "emails": ["tech.recruitment@ttbbank.com"],
        "best": "tech.recruitment@ttbbank.com",
        "source": "Bangkok Bank Careers FB post",
    },

    # ── Software Dev Companies / Consultancies ──
    "Seven Peaks Software": {
        "domain": "sevenpeakssoftware.com",
        "emails": ["Jobs@sevenpeakssoftware.com"],
        "best": "Jobs@sevenpeakssoftware.com",
        "source": "sevenpeakssoftware.com/contact + Instagram",
    },
    "Manao Software": {
        "domain": "manaosoftware.com",
        "emails": ["hr@manaosoftware.com"],
        "best": "hr@manaosoftware.com",
        "source": "manaosoftware.com/careers",
    },
    "Softnix Technology": {
        "domain": "softnix.co.th",
        "emails": ["sales@softnix.co.th", "marketing@softnix.co.th"],
        "best": "sales@softnix.co.th",
        "source": "softnix.ai/contact-2",
    },
    "Tech Curve AI & Innovations": {
        "domain": "techcurve.co",
        "emails": ["information@techcurve.co", "nareekan_salert@techcurve.co"],
        "best": "information@techcurve.co",
        "source": "techcurve.co/contact-us + FB post",
    },
    "Nimble": {
        "domain": "nimblehq.co",
        "emails": ["careers@nimblehq.co"],
        "best": "careers@nimblehq.co",
        "source": "nimblehq.co/careers",
    },
    "GoSoft": {
        "domain": "gosoft.co.th",
        "emails": ["join@gosoft.co.th"],
        "best": "join@gosoft.co.th",
        "source": "GoSoft Instagram post",
    },
    "Siri Soft": {
        "domain": "sirisoft.co.th",
        "emails": ["info@sirisoft.co.th"],
        "best": "info@sirisoft.co.th",
        "source": "blackbabesabroad.substack.com",
    },
    "Diksha Tek": {
        "domain": "dikshatek.co.th",
        "emails": ["Jobs@dikshatek.co.th"],
        "best": "Jobs@dikshatek.co.th",
        "source": "Diksha Tek Instagram reel",
    },

    # ── Enterprise / Conglomerate Tech ──
    "True Digital Group": {
        "domain": "truedigital.com",
        "emails": ["careers@truedigital.com"],
        "best": "careers@truedigital.com",
        "source": "True Digital Group LinkedIn",
    },
    "AIS (Advanced Info Service)": {
        "domain": "ais.th",
        "emails": ["careers@ais.th"],
        "best": "careers@ais.th",
        "source": "ais.th/en/about-us/careers",
    },
    "Central Group (Digital)": {
        "domain": "centralgroup.com",
        "emails": ["careers@centralgroup.com"],
        "best": "careers@centralgroup.com",
        "source": "careers.centralgroup.com",
    },
    "Minor International (Tech)": {
        "domain": "minor.com",
        "emails": ["careers@minor.com"],
        "best": "careers@minor.com",
        "source": "careers.smartrecruiters.com/MinorInternational",
    },

    # ── Thai Startup / Mid-size Tech ──
    "Sellsuki": {
        "domain": "sellsuki.co.th",
        "emails": ["careers@sellsuki.co.th"],
        "best": "careers@sellsuki.co.th",
        "source": "sellsuki.co.th + JobsDB",
    },
    "Priceza": {
        "domain": "priceza.com",
        "emails": ["careers@priceza.com"],
        "best": "careers@priceza.com",
        "source": "priceza.com LinkedIn",
    },
    "Punspace": {
        "domain": "punspace.com",
        "emails": ["hello@punspace.com"],
        "best": "hello@punspace.com",
        "source": "Creative Chiang Mai IT Directory",
    },
    "Three Leaf Clover (Thailand)": {
        "domain": "threeleafclover.com",
        "emails": ["info@threeleafclover.com"],
        "best": "info@threeleafclover.com",
        "source": "Creative Chiang Mai IT Directory",
    },
    "Trakool Software": {
        "domain": "trakool.com",
        "emails": ["info@trakool.com"],
        "best": "info@trakool.com",
        "source": "Creative Chiang Mai IT Directory",
    },
    "Wise Solution and Consulting": {
        "domain": "wisesolution.co.th",
        "emails": ["info@wisesolution.co.th"],
        "best": "info@wisesolution.co.th",
        "source": "Creative Chiang Mai IT Directory",
    },
    "Yes I Am Innovation": {
        "domain": "yesiam.co.th",
        "emails": ["info@yesiam.co.th"],
        "best": "info@yesiam.co.th",
        "source": "Creative Chiang Mai IT Directory",
    },
    "Radarsofthouse": {
        "domain": "radarsofthouse.com",
        "emails": ["info@radarsofthouse.com"],
        "best": "info@radarsofthouse.com",
        "source": "Creative Chiang Mai IT Directory",
    },
    "ZI-Argus Industrial Automation": {
        "domain": "zi-argus.com",
        "emails": ["info@zi-argus.com"],
        "best": "info@zi-argus.com",
        "source": "Creative Chiang Mai IT Directory",
    },
    "Prosoft Web": {
        "domain": "prosoftweb.com",
        "emails": ["info@prosoftweb.com"],
        "best": "info@prosoftweb.com",
        "source": "Creative Chiang Mai IT Directory",
    },
    "Win Broadband": {
        "domain": "winbroadband.com",
        "emails": ["info@winbroadband.com"],
        "best": "info@winbroadband.com",
        "source": "Creative Chiang Mai IT Directory",
    },

    # ── Recruitment Agencies (Thai tech focus) ──
    "Personnel Consultant (Thailand)": {
        "domain": "personnelconsultant.co.th",
        "emails": ["jobs@personnelconsultant.co.th"],
        "best": "jobs@personnelconsultant.co.th",
        "source": "FB Jobs for Thai Programmers group",
    },
}


def load_json(path):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def save_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def add_to_tracker(tracker_path, companies):
    """Add companies to apply_tracker.csv if not already present."""
    existing = set()
    rows = []
    if os.path.exists(tracker_path):
        with open(tracker_path, newline='') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            for row in reader:
                rows.append(row)
                existing.add(row['company'].lower().strip())

    added = 0
    for company, data in companies.items():
        if company.lower().strip() in existing:
            continue
        # Build a tracker entry
        domain = data.get('domain', '')
        url = f"https://{domain}" if domain else ''
        row = {
            'url': url,
            'title': 'Software Developer',
            'company': company,
            'status': 'discovered',
            'note': f"Thai company — email: {data.get('best', 'N/A')}",
            'updated_at': '',
            'work_type': 'WFO',
            'visa_sponsor': '',
            'job_type': 'Full-time',
            'experience_level': '',
            'country': 'TH',
        }
        # Filter to valid fieldnames
        if fieldnames:
            filtered = {k: row.get(k, '') for k in fieldnames if k in row}
            rows.append(filtered)
        else:
            rows.append(row)
        added += 1

    if added > 0:
        fieldnames = fieldnames or ['url', 'title', 'company', 'status', 'note', 'updated_at',
                                     'work_type', 'visa_sponsor', 'job_type', 'experience_level', 'country']
        with open(tracker_path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(rows)

    return added


def main():
    # Load existing contacts
    contacts = load_json(CONTACT_FILE)
    print(f"Existing contacts: {len(contacts)}")

    # Add Thai companies
    added = 0
    for company, data in THAI_COMPANIES.items():
        if company in contacts:
            # Update existing entry if it has no emails
            existing = contacts[company]
            if not existing.get('emails') and data.get('emails'):
                contacts[company].update(data)
                added += 1
                print(f"  Updated: {company}")
            else:
                print(f"  Skip (exists): {company}")
            continue
        contacts[company] = data
        added += 1
        print(f"  Added: {company}")

    print(f"\nNew/updated contacts: {added}")
    print(f"Total contacts: {len(contacts)}")

    # Save
    save_json(CONTACT_FILE, contacts)
    print(f"Saved to {CONTACT_FILE}")

    # Add to tracker
    tracker_added = add_to_tracker(TRACKER_FILE, THAI_COMPANIES)
    print(f"Added {tracker_added} entries to tracker")

    # Count Thai companies
    thai_count = sum(1 for k in contacts if any(ind in k.lower() for ind in [
        'thailand', 'ไทย', 'thai', 'bangkok', 'bkk',
        'agoda', 'wongnai', 'shopee', 'grab', 'lazada',
        'bitkub', 'btse', 'kbtg', 'scb', 'bangkok bank',
        'seven peaks', 'manao', 'softnix', 'tech curve', 'nimble',
        'gosoft', 'siri soft', 'diksha', 'true digital', 'ais',
        'central group', 'minor', 'sellsuki', 'priceza', 'punspace',
        'trakool', 'wise solution', 'yes i am', 'radarsofthouse',
        'zi-argus', 'prosoft', 'win broadband', 'personnel consultant',
        'three leaf',
    ]))
    print(f"\nThai-related contacts in DB: {thai_count}")


if __name__ == '__main__':
    main()
