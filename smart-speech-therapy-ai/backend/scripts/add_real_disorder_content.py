"""
One-off script: adds real, evidence-grounded disorder content via the
actual admin API (not direct DB writes) — this exercises the exact same
code path a human admin uses, as a genuine end-to-end check.

Content is written in original wording, informed by (not copied from)
ASHA Practice Portal pages and other cited sources — see the chat
transcript for the specific sources checked for each disorder.
"""
import httpx

BASE = "http://127.0.0.1:8000/api/v1"

def login(email, password):
    r = httpx.post(f"{BASE}/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    return r.json()["access_token"]

def main():
    token = login("admin@example.com", "change-me-strong-password")
    headers = {"Authorization": f"Bearer {token}"}

    # --- Categories ---------------------------------------------------
    categories = {}
    for name, desc in [
        ("Motor Speech Disorders", "Disorders affecting the planning, programming, or execution of the movements needed for speech."),
        ("Language Disorders", "Disorders affecting the understanding and/or use of spoken or written language."),
        ("Social Communication Disorders", "Conditions affecting communication in social contexts; some are primarily psychiatric/anxiety-related but involve SLPs due to their communication impact."),
    ]:
        r = httpx.post(f"{BASE}/disorders/categories", json={"name": name, "description": desc}, headers=headers)
        if r.status_code == 201:
            categories[name] = r.json()["id"]
            print(f"Created category: {name}")
        else:
            print(f"Category '{name}' skipped ({r.status_code}): {r.text[:100]}")

    # Fetch existing categories too (e.g. "Voice Disorders" from seed data)
    r = httpx.get(f"{BASE}/disorders/categories")
    for c in r.json():
        categories.setdefault(c["name"], c["id"])

    # --- Disorders ------------------------------------------------------
    disorders = [
        {
            "name": "Childhood Apraxia of Speech",
            "slug": "childhood-apraxia-of-speech",
            "category_id": categories.get("Motor Speech Disorders"),
            "overview": (
                "Childhood Apraxia of Speech (CAS) is a neurological pediatric speech sound "
                "disorder that affects a child's ability to plan and program the precise, "
                "coordinated movements needed for speech — even though the speech muscles "
                "themselves are not weak. This distinguishes it from other speech sound "
                "disorders, where the difficulty typically lies in muscle strength or in "
                "learning phonological rules rather than motor planning."
            ),
            "possible_characteristics": (
                "Inconsistent errors on the same sounds or words across repeated attempts; "
                "visible groping or searching movements of the jaw, lips, or tongue when "
                "attempting speech; increasing difficulty as words and utterances get longer "
                "or more complex."
            ),
            "speech_features": (
                "A limited consonant and vowel repertoire, frequent vowel distortions, "
                "disrupted transitions between sounds (coarticulation), and unusual stress or "
                "rhythm patterns — for example, equal stress across syllables or a "
                "\"choppy\" speech rhythm."
            ),
            "assessment_notes": (
                "A comprehensive motor speech evaluation by an SLP experienced with pediatric "
                "motor speech disorders is recommended. There is no single definitive "
                "instrumental test; diagnosis relies on a trained clinician's perceptual "
                "judgment, generally looking for the combination of inconsistent errors, "
                "disrupted coarticulation, and inappropriate prosody. CAS is estimated to "
                "affect roughly 1-2 children per 1,000, and can share features with other "
                "speech disorders, so differential diagnosis benefits from clinicians "
                "experienced with the condition."
            ),
        },
        {
            "name": "Dysarthria",
            "slug": "dysarthria",
            "category_id": categories.get("Motor Speech Disorders"),
            "overview": (
                "Dysarthria refers to a group of neurologic speech disorders caused by "
                "weakness, paralysis, or incoordination of the speech musculature, resulting "
                "from damage to the central or peripheral nervous system. Unlike apraxia, the "
                "movements themselves are physically impaired, rather than their planning — "
                "and effects can appear in any combination of five speech subsystems: "
                "respiration, phonation, resonance, articulation, and prosody."
            ),
            "possible_characteristics": (
                "Reduced speech intelligibility, changes in vocal quality (e.g., a breathy, "
                "strained, or hoarse voice), imprecise consonant production, and a speaking "
                "rate that is slower, faster, or more variable than typical."
            ),
            "speech_features": (
                "Presentation varies by underlying type — for example, flaccid dysarthria "
                "(from lower motor neuron damage) often produces a breathy, hypernasal voice, "
                "while spastic dysarthria (upper motor neuron damage) tends to produce a "
                "strained, harsh voice with slow, effortful speech. Ataxic, hypokinetic, "
                "hyperkinetic, and mixed patterns are also recognized, each associated with "
                "different neurological causes."
            ),
            "assessment_notes": (
                "Assessment typically evaluates each speech subsystem individually, "
                "identifies the dysarthria type/pattern, and considers the impact on "
                "intelligibility, speech naturalness, and everyday communication "
                "participation. Assessment should take place in the language(s) the person "
                "uses, with appropriate accommodations for multilingual speakers."
            ),
        },
        {
            "name": "Aphasia",
            "slug": "aphasia",
            "category_id": categories.get("Language Disorders"),
            "overview": (
                "Aphasia is an acquired language disorder, most commonly resulting from "
                "stroke or other brain injury, that affects the ability to produce and/or "
                "understand spoken or written language. Aphasia is a disorder of language, "
                "not of intelligence — comprehension of the underlying ideas is generally "
                "distinct from a person's cognitive ability, even when communication is "
                "significantly affected."
            ),
            "possible_characteristics": (
                "Difficulty finding words, forming complete sentences, understanding spoken "
                "or written language, or a combination of these — the specific pattern "
                "depends on the location and extent of the brain injury."
            ),
            "speech_features": (
                "Broadly grouped into non-fluent patterns (effortful, halting speech with "
                "relatively preserved comprehension, as in Broca's aphasia) and fluent "
                "patterns (grammatically intact-sounding but often meaning-poor speech with "
                "impaired comprehension, as in Wernicke's aphasia). Other recognized patterns "
                "include global aphasia (severe difficulty with both production and "
                "comprehension), anomic aphasia (primarily word-finding difficulty), and "
                "conduction aphasia (particular difficulty repeating phrases despite good "
                "comprehension)."
            ),
            "assessment_notes": (
                "Assessment considers the severity and subtype of aphasia together with its "
                "functional impact on daily communication, to guide intervention planning and "
                "counseling for the person and their care partners. Clinicians take care not "
                "to assume reduced intelligence based on communication difficulty alone."
            ),
        },
        {
            "name": "Voice Disorders",
            "slug": "voice-disorders",
            "category_id": categories.get("Voice Disorders"),
            "overview": (
                "A voice disorder is present when pitch, loudness, or vocal quality differs "
                "from what would be expected for a person's age, gender, and cultural "
                "background in a way that draws attention to the voice or interferes with "
                "communication — often related to structural, functional, or neurological "
                "changes in how the voice is produced."
            ),
            "possible_characteristics": (
                "Hoarseness, breathiness, vocal strain, voice breaks, a reduced pitch range, "
                "or vocal fatigue that increases with extended voice use."
            ),
            "speech_features": (
                "May stem from structural changes to the vocal folds (e.g., nodules or "
                "polyps, often linked to vocal misuse patterns), functional voice-use "
                "patterns without a structural cause, or neurological conditions affecting "
                "vocal fold movement or coordination."
            ),
            "assessment_notes": (
                "Evaluation typically involves a team approach: an ENT/laryngologist "
                "examines the vocal folds directly (e.g., via laryngoscopy), while an SLP "
                "assesses vocal function, use patterns, and contributing behaviors."
            ),
        },
        {
            "name": "Selective Mutism",
            "slug": "selective-mutism",
            "category_id": categories.get("Social Communication Disorders"),
            "overview": (
                "Selective mutism is a childhood condition, classified in the DSM-5 as an "
                "anxiety disorder, in which a person consistently does not speak in specific "
                "social situations (e.g., school) despite speaking comfortably in other "
                "settings (e.g., home). Speech-language pathologists are often part of the "
                "care team given the direct impact on communication participation, even "
                "though the underlying condition itself is not a primary speech-language "
                "disorder."
            ),
            "possible_characteristics": (
                "Consistent silence in specific settings or with specific people while "
                "speaking normally elsewhere; onset typically between ages 3 and 6; commonly "
                "co-occurs with other anxiety symptoms."
            ),
            "speech_features": (
                "When a child does speak in a difficult setting, speech may be produced in a "
                "whisper, at reduced volume, or with an altered vocal quality — linked to "
                "increased laryngeal tension associated with anxiety in that moment."
            ),
            "assessment_notes": (
                "Diagnosis is made through a multidisciplinary evaluation involving "
                "psychology/psychiatry alongside speech-language assessment. The SLP's role "
                "typically focuses on identifying or ruling out co-occurring speech/language "
                "disorders and documenting communication and vocal patterns — not on "
                "diagnosing the underlying anxiety disorder."
            ),
        },
    ]

    for d in disorders:
        r = httpx.post(f"{BASE}/disorders", json=d, headers=headers)
        if r.status_code == 201:
            print(f"Created disorder: {d['name']}")
        else:
            print(f"Disorder '{d['name']}' skipped ({r.status_code}): {r.text[:150]}")

if __name__ == "__main__":
    main()
