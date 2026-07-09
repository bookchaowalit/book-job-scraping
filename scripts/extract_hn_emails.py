#!/usr/bin/env python3
"""Extract company-email pairs from HN Who is Hiring threads."""

import json
import re
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CONTACTS_FILE = DATA_DIR / "contact_emails.json"

# Known email patterns from HN July 2026 thread
JULY_2026_EMAILS = {
    "Grace AI Control": "david.young@graceaicontrol.com",
    "L'Occitane en Provence": "gabriel.rocha@loccitane.com",
    "Pango": "Steve@pango.ai",
    "CoreConnect": "andreas.kull@ventureone.ae",
    "Connie Health": "huan.lai@conniehealth.com",
    "Walmart Global Tech": "gaurav.sharma0@walmart.com",
    "Quantum Rise": "julian.berman@quantumrise.com",
    "ChainSecurity": "jobs@chainsecurity.com",
    "Delta AI": "hiring@learndelta.ai",
    "Estuary": "careers@estuary.dev",
    "Pineapple": "Devin@PineappleHi.com",
    "Furtim Modus": "agency@furtimmodus.com",
    "Aurelius Systems": "alfredo@aureliussystems.us",
    "Playit.gg": "apply@playit.gg",
    "ProxyBase": "atjobs@proxybase.xyz",
    "SurgeHQ": "careers@surgehq.ai",
    "St. Jude": "clay.mcleod@stjude.org",
    "Tetherline": "contact@tetherline.dev",
    "Symetra": "elliot.wargo@symetra.com",
    "Electric Twin": "harry.smith@electrictwin.com",
    "Soni Bel Instruments": "hooman@sonibelinstruments.com",
    "Axo Ventures": "jlyman@axoventures.co",
    "Dr. Swarm": "jobs@drswarm.com",
    "Kinelo": "jobs@kinelo.com",
    "Podo": "josef@podosai.com",
    "Ontix": "l33t@ontix.io",
    "Wirescreen": "leo.green@wirescreen.ai",
    "Breakfast Studio": "lipton@breakfaststudio.com",
    "Rivio": "llarrere@rivio.ai",
    "IPInfo": "matt@ipinfo.io",
    "Kinx": "mercedes@kinxshn.com",
    "Vertex": "paul.chung@vertexinc.com",
    "Albert": "recruiting@albert.com",
    "Starbridge": "recruiting@starbridge.ai",
    "Vitalize Care": "ryan@vitalize.care",
    "Logen": "shvilesh@logen.io",
    "Kanary": "steven@kanary.com",
    "WME Group": "tkuhl@wmegrp.com",
}

# Known email patterns from HN June 2026 thread
JUNE_2026_EMAILS = {
    "VBCheers": "Eastman@VBCheers.com",
    "SpaceX": "Joshua.Johnson@spacex.com",
    "Neuralk AI": "aaron.stillwell@neuralk-ai.com",
    "OHR": "ai@ohr.xyz",
    "Northstar Security": "alex@northstar.security",
    "Hatchet": "alexander@hatchet.run",
    "Viam": "amanda@viam.com",
    "FWD": "amays+hn@getfwd.com",
    "L2 Labs": "andrew@l2labs.ai",
    "Stpk": "arnav@stpkr.in",
    "Bucket Bot": "ben@bucket.bot",
    "Segments": "bert@segments.ai",
    "Silkline": "brent@silkline.ai",
    "Modal": "can@modal.com",
    "Babou": "careers@babou.ai",
    "Coder": "careers@coder.com",
    "Evertune": "casey@evertune.ai",
    "Opaxa": "colton@opaxa.ai",
    "Tech Mahindra": "cprabala@techmahindra.com",
    "Speckle": "d@speckle.systems",
    "Branch3D": "dcascaval@branch3d.com",
    "Kepler AI": "eddie.hammond@kepler.ai",
    "Frisson Labs": "founders@frisson-labs.com",
    "Brightcore": "frankie@brightcore.ie",
    "Aquabyte": "gem.openreq@aquabyte.ai",
    "Monk": "george@monk.com",
    "Diffusion": "hello@diffusion.io",
    "Kiloforge": "hello@kiloforge.com",
    "Pelo Tech": "henry.anderson@pelo.tech",
    "Focal VC": "hiring@focal.vc",
    "Hotwash": "hiring@hotwash.com",
    "Laminr": "hiring@laminr.co",
    "Neurohealth Collective": "hiring@neurohealthcollective.com",
    "Reef": "hiring@reef.pl",
    "Psiphon": "hr@psiphon.ca",
    "Fusionbox": "info@fusionbox.com",
    "Readifi Financial": "info@readifinancial.com",
    "Tapitab": "info@tapitab.com",
    "Emergence AI": "jack@emergences.ai",
    "Guac AI": "jack@guac-ai.com",
    "Upwave": "jason.kelly@upwave.com",
    "Authorium": "jay@authorium.com",
    "Deepcore Tech": "jeff@deepcoretech.com",
    "Shop Brands": "jobs@goshopbrands.com",
    "Zulip": "jobs@zulip.com",
    "Trashlab": "john@trashlab.io",
    "Z0 AI": "join@z0.ai",
    "Build": "jon@join.build",
    "Puls Security": "karriere@puls-security.de",
}

def extract_domain(email: str) -> str:
    """Extract domain from email address."""
    return email.split('@')[-1].lower()

def add_contacts(new_contacts: dict, source: str):
    """Add new contacts to contact_emails.json."""
    if CONTACTS_FILE.exists():
        contacts = json.loads(CONTACTS_FILE.read_text())
    else:
        contacts = {}
    
    added = 0
    for company, email in new_contacts.items():
        # Skip if company already exists
        if company.lower() in {k.lower() for k in contacts.keys()}:
            print(f"  SKIP: {company} already exists")
            continue
        
        # Skip if email already exists for another company
        existing_emails = {v.get('best') for v in contacts.values() if v.get('best')}
        if email.lower() in {e.lower() for e in existing_emails}:
            print(f"  SKIP: {email} already exists")
            continue
        
        domain = extract_domain(email)
        contacts[company] = {
            "domain": domain,
            "emails": [email],
            "best": email,
            "source": source
        }
        added += 1
        print(f"  ADD: {company} -> {email}")
    
    with open(CONTACTS_FILE, 'w') as f:
        json.dump(contacts, f, indent=2, ensure_ascii=False)
    
    print(f"\nAdded {added} new contacts from {source}")
    return added

if __name__ == "__main__":
    print("Adding HN July 2026 contacts...")
    july_count = add_contacts(JULY_2026_EMAILS, "HN Who is Hiring July 2026")
    
    print("\nAdding HN June 2026 contacts...")
    june_count = add_contacts(JUNE_2026_EMAILS, "HN Who is Hiring June 2026")
    
    print(f"\nTotal added: {july_count + june_count}")
