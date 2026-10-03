"""
Seed default roles/permissions, a first admin account, and a small set of
sample reference data (disorder categories/disorders, exercises, a game,
and a Knowledge Base document) so the platform is usable immediately after
setup.

This is DEVELOPMENT / BOOTSTRAP data only (spec section 112) — it must never
be confused with real patient data, and should be re-run safely (idempotent)
against a fresh database.

Usage:
    python scripts/seed.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.session import Base, SessionLocal, engine  # noqa: E402
from app.models.disorders import Disorder, DisorderCategory  # noqa: E402
from app.models.exercises import Exercise  # noqa: E402
from app.models.games import Game  # noqa: E402
from app.models.knowledge_base import KnowledgeDocument  # noqa: E402
from app.models.rbac import DEFAULT_PERMISSIONS, DEFAULT_ROLES, Permission, Role  # noqa: E402
from app.models.user import User  # noqa: E402
from app.security.tokens import hash_password  # noqa: E402
from app.services.knowledge_base_service import ingest_document_text  # noqa: E402


def seed_roles_and_permissions(db) -> dict[str, Role]:
    permissions_by_code: dict[str, Permission] = {}
    for code, description in DEFAULT_PERMISSIONS.items():
        perm = db.scalar(select(Permission).where(Permission.code == code))
        if perm is None:
            perm = Permission(code=code, description=description)
            db.add(perm)
        permissions_by_code[code] = perm
    db.flush()

    roles_by_name: dict[str, Role] = {}
    for role_name, perm_codes in DEFAULT_ROLES.items():
        role = db.scalar(select(Role).where(Role.name == role_name))
        if role is None:
            role = Role(name=role_name, description=f"{role_name.title()} role")
            db.add(role)
            db.flush()
        role.permissions = [permissions_by_code[code] for code in perm_codes]
        roles_by_name[role_name] = role

    db.commit()
    print(f"Seeded {len(permissions_by_code)} permissions and {len(roles_by_name)} roles.")
    return roles_by_name


def seed_first_admin(db, roles_by_name: dict[str, Role]) -> None:
    existing = db.scalar(select(User).where(User.email == settings.FIRST_ADMIN_EMAIL))
    if existing:
        print(f"Admin '{settings.FIRST_ADMIN_EMAIL}' already exists — skipping.")
        return

    admin = User(
        email=settings.FIRST_ADMIN_EMAIL,
        hashed_password=hash_password(settings.FIRST_ADMIN_PASSWORD),
        full_name="System Administrator",
        preferred_language="en",
        is_active=True,
        is_email_verified=True,
        roles=[roles_by_name["ADMIN"]],
    )
    db.add(admin)
    db.commit()
    print(f"Created first admin: {settings.FIRST_ADMIN_EMAIL}")
    print("!! Change FIRST_ADMIN_PASSWORD immediately in production. !!")


def seed_first_specialist(db, roles_by_name: dict[str, Role]) -> None:
    if not settings.FIRST_SPECIALIST_EMAIL:
        return
    existing = db.scalar(select(User).where(User.email == settings.FIRST_SPECIALIST_EMAIL))
    if existing:
        print(f"Specialist '{settings.FIRST_SPECIALIST_EMAIL}' already exists — skipping.")
        return

    specialist = User(
        email=settings.FIRST_SPECIALIST_EMAIL,
        hashed_password=hash_password(settings.FIRST_SPECIALIST_PASSWORD),
        full_name="Speech-Language Pathologist",
        preferred_language="en",
        is_active=True,
        is_email_verified=True,
        roles=[roles_by_name["SPECIALIST"]],
    )
    db.add(specialist)
    db.commit()
    print(f"Created first specialist: {settings.FIRST_SPECIALIST_EMAIL}")
    print("!! Change FIRST_SPECIALIST_PASSWORD immediately in production. !!")


def seed_sample_content(db) -> None:
    if db.scalar(select(DisorderCategory)):
        print("Sample content already present — skipping.")
        return

    fluency_category = DisorderCategory(name="Fluency Disorders", description="Disorders affecting the flow of speech.")
    voice_category = DisorderCategory(name="Voice Disorders", description="Disorders affecting vocal quality, pitch, or loudness.")
    motor_speech_category = DisorderCategory(
        name="Motor Speech Disorders",
        description="Disorders affecting the planning, programming, or execution of the movements needed for speech.",
    )
    language_category = DisorderCategory(
        name="Language Disorders",
        description="Disorders affecting the ability to understand or express language.",
    )
    db.add_all([fluency_category, voice_category, motor_speech_category, language_category])
    db.flush()

    stuttering = Disorder(
        category_id=fluency_category.id,
        name="Stuttering",
        slug="stuttering",
        language="en",
        overview=(
            "Stuttering is a fluency disorder characterized by disruptions in the "
            "flow of speech, such as repetitions, prolongations, or blocks."
        ),
        possible_characteristics="Sound/syllable repetitions, prolongations, blocks, interjections.",
        speech_features="Reduced speaking rate, increased pause frequency, secondary behaviors.",
        assessment_notes=(
            "AI screening in this platform is based on acoustic pattern detection only "
            "and must not be treated as a diagnosis — professional assessment is recommended."
        ),
    )

    apraxia = Disorder(
        category_id=motor_speech_category.id,
        name="Childhood Apraxia of Speech",
        slug="childhood-apraxia-of-speech",
        language="en",
        overview=(
            "Childhood Apraxia of Speech (CAS) is a neurological motor speech disorder in "
            "which a child has difficulty planning and coordinating the precise, sequenced "
            "movements needed for speech, even though the speech muscles themselves are not "
            "weak. The disruption is in the brain's ability to plan and program those "
            "movements, not in muscle strength."
        ),
        possible_characteristics=(
            "Inconsistent errors on consonants and vowels across repeated productions of the "
            "same word; longer or more distorted sounds and syllables as words/phrases get "
            "longer; visible groping movements of the jaw, lips, or tongue while attempting "
            "speech sounds; difficulty imitating speech; equal or misplaced stress across "
            "syllables (e.g. \"ba-NA-na\" produced as \"BA-NA-NA\")."
        ),
        speech_features=(
            "Difficulty sequencing sounds and syllables into words, particularly longer or "
            "more complex words; inconsistent voicing errors; disrupted prosody — the rhythm, "
            "stress, and intonation of speech; sounds may be produced correctly in isolation "
            "but not in connected speech."
        ),
        assessment_notes=(
            "Assessment is typically performed by a speech-language pathologist and includes "
            "case history review, an oral-motor examination to rule out muscle weakness, and "
            "analysis of speech across single words, phrases, and connected speech — paying "
            "particular attention to the consistency of errors and prosody. CAS can be "
            "difficult to distinguish from other speech sound disorders in young children, so "
            "diagnosis often benefits from observation over time rather than a single visit."
        ),
    )

    dysarthria = Disorder(
        category_id=motor_speech_category.id,
        name="Dysarthria",
        slug="dysarthria",
        language="en",
        overview=(
            "Dysarthria is a motor speech disorder that results from weakness, paralysis, or "
            "incoordination of the muscles used for speech, typically caused by damage to the "
            "nervous system (for example, stroke, traumatic brain injury, Parkinson's disease, "
            "ALS, or cerebral palsy). Unlike apraxia, the difficulty comes from impaired muscle "
            "control itself, not from planning the movements."
        ),
        possible_characteristics=(
            "Slurred or 'mumbled' speech; abnormally slow or, in some presentations, unusually "
            "rapid speech rate; irregular rhythm and stress patterns; changes in voice quality "
            "such as breathiness, harshness, or a strained-strangled sound; hypernasality or "
            "hyponasality; reduced volume or difficulty controlling loudness."
        ),
        speech_features=(
            "Imprecise articulation of consonants; reduced range and speed of movement of the "
            "lips, tongue, and jaw; breath support and control difficulties affecting phrasing "
            "and loudness; may co-occur with drooling or difficulty with non-speech oral-motor "
            "tasks such as chewing and swallowing."
        ),
        assessment_notes=(
            "Assessment typically involves a perceptual evaluation of speech intelligibility, "
            "an oral-motor examination, and consideration of the underlying medical condition — "
            "dysarthria has several recognized subtypes (e.g. spastic, flaccid, ataxic, "
            "hypokinetic, hyperkinetic) linked to different areas of nervous system involvement. "
            "Assessment is usually coordinated with the person's broader medical care team."
        ),
    )

    aphasia = Disorder(
        category_id=language_category.id,
        name="Aphasia",
        slug="aphasia",
        language="en",
        overview=(
            "Aphasia is an acquired language disorder that results from damage to the parts of "
            "the brain responsible for language — most commonly caused by stroke, but also by "
            "traumatic brain injury, brain tumors, or progressive neurological conditions. It "
            "affects the ability to express and/or understand language but does not reflect a "
            "person's underlying intelligence."
        ),
        possible_characteristics=(
            "Difficulty finding words during conversation (word-finding difficulty); difficulty "
            "forming complete or grammatically correct sentences; difficulty understanding "
            "spoken or written language; difficulty reading or writing; may substitute "
            "unintended words or sounds (paraphasia)."
        ),
        speech_features=(
            "Speech may be fluent but contain word-finding pauses and circumlocution (talking "
            "around a word), or may be non-fluent, effortful, and reduced to short phrases — "
            "the pattern depends on the type and location of brain damage; repetition of words "
            "or phrases may also be impaired."
        ),
        assessment_notes=(
            "Assessment is typically conducted by a speech-language pathologist in coordination "
            "with the person's medical team, and includes standardized language testing across "
            "auditory comprehension, verbal expression, reading, and writing, along with a "
            "review of medical history and any relevant brain imaging."
        ),
    )

    db.add_all([stuttering, apraxia, dysarthria, aphasia])
    db.flush()

    # --- Expanded taxonomy (spec section 17): two new categories plus five
    # new disorders, each with the full required page structure (Overview,
    # Common Characteristics, Speech/Language Features, Assessment
    # Considerations — assessment_notes below — plus the Safety/Limitations
    # language baked into every disorder's assessment_notes). This is
    # original, responsibly-written general educational content — NOT
    # sourced from or claiming to cite specific peer-reviewed literature,
    # consistent with spec section 17's "do not generate fake medical
    # content": nothing here invents a citation or a study that wasn't
    # actually checked. See docs/FINAL_UPGRADE_PLAN.md for which
    # additional disorders from the spec's suggested list (e.g.
    # Phonological Disorder, Apraxia of Speech in adults, Language Delay,
    # resonance disorders) were left for a future pass rather than rushed.
    speech_sound_category = DisorderCategory(
        name="Speech Sound Disorders",
        description="Disorders affecting the production of individual speech sounds.",
    )
    social_comm_category = DisorderCategory(
        name="Other Communication Areas",
        description="Communication difficulties outside the classic fluency/voice/motor-speech/language groupings.",
    )
    db.add_all([speech_sound_category, social_comm_category])
    db.flush()

    cluttering = Disorder(
        category_id=fluency_category.id,
        name="Cluttering",
        slug="cluttering",
        language="en",
        overview=(
            "Cluttering is a fluency disorder characterized by a speech rate that is "
            "perceived as too fast, irregular, or both, along with breakdowns in speech "
            "clarity that are not explained by typical stuttering-type disfluencies. It is "
            "often under-recognized and can co-occur with stuttering, which makes careful "
            "differential assessment important."
        ),
        possible_characteristics=(
            "Rapid and/or irregular speech rate; excessive collapsing or deletion of "
            "syllables in longer words; disorganized language formulation (false starts, "
            "revisions); listener often reports needing to ask for repetition; the person "
            "may have limited awareness of their own disfluency, unlike many people who stutter."
        ),
        speech_features=(
            "Telescoped or 'mushy' multisyllabic words; irregular rhythm rather than the "
            "sound/syllable repetitions typical of stuttering; language may sound disorganized "
            "independent of the speech-motor pattern."
        ),
        assessment_notes=(
            "Assessment differentiates cluttering from stuttering and from typical fast "
            "speech, often using recorded-speech rate and clarity measures alongside "
            "listener-intelligibility judgments. AI screening in this platform is based on "
            "acoustic pattern detection only and must not be treated as a diagnosis — "
            "professional assessment is recommended, particularly since cluttering and "
            "stuttering can co-occur."
        ),
    )

    dev_language_disorder = Disorder(
        category_id=language_category.id,
        name="Developmental Language Disorder",
        slug="developmental-language-disorder",
        language="en",
        overview=(
            "Developmental Language Disorder (DLD) is a difficulty learning and using "
            "language that is not explained by another condition such as hearing loss, "
            "intellectual disability, or autism. It is a lifelong difference in language "
            "ability that begins in early childhood and can persist into adulthood in some "
            "form, though its impact can change significantly with support."
        ),
        possible_characteristics=(
            "Smaller vocabulary than same-age peers; difficulty with grammar (verb tense, "
            "sentence structure); difficulty following multi-step spoken instructions; "
            "difficulty organizing spoken narratives or retelling events in order; these "
            "difficulties are present despite typical hearing and typical nonverbal "
            "cognitive ability."
        ),
        speech_features=(
            "Language-level difficulty rather than a speech-sound-production difficulty — "
            "articulation of individual sounds may be entirely typical while sentence "
            "construction, word-finding, and comprehension of complex language lag behind."
        ),
        assessment_notes=(
            "Assessment is typically conducted by a speech-language pathologist using "
            "standardized language tests covering vocabulary, grammar, and narrative/"
            "discourse skills, alongside case history to rule out other explanatory "
            "conditions. AI screening in this platform does not diagnose DLD — it can at "
            "most flag language-sample patterns for a qualified professional to review."
        ),
    )

    articulation_disorder = Disorder(
        category_id=speech_sound_category.id,
        name="Articulation Disorder",
        slug="articulation-disorder",
        language="en",
        overview=(
            "An articulation disorder involves difficulty physically producing specific "
            "speech sounds correctly — sounds may be substituted, omitted, added, or "
            "distorted. It differs from a phonological disorder in that the difficulty is "
            "with the physical production of a sound rather than with the underlying sound-"
            "pattern rules of the language, though the two frequently co-occur and can be "
            "hard to tell apart without professional assessment."
        ),
        possible_characteristics=(
            "Consistent difficulty with one or a few specific sounds (e.g. a persistent "
            "lisp on /s/ and /z/, or difficulty with /r/); distortions that make speech "
            "sound 'off' without necessarily being unintelligible; errors that are "
            "relatively consistent across words, unlike the word-to-word variability seen "
            "in apraxia."
        ),
        speech_features=(
            "Sound-specific substitutions (e.g. 'wabbit' for 'rabbit'), omissions (e.g. "
            "'nana' for 'banana'), or distortions (e.g. a lateral /s/); intelligibility "
            "impact ranges from minor to significant depending on how many sounds are "
            "affected and the child's age."
        ),
        assessment_notes=(
            "Assessment by a speech-language pathologist typically includes a single-word "
            "and connected-speech articulation test, an oral-motor exam, and comparison "
            "against typical developmental norms for when each sound is expected to be "
            "mastered (many sound errors are entirely typical at younger ages). AI "
            "screening in this platform is not a substitute for this professional evaluation."
        ),
    )

    dysphonia = Disorder(
        category_id=voice_category.id,
        name="Dysphonia (Voice Disorder)",
        slug="dysphonia",
        language="en",
        overview=(
            "Dysphonia refers to an abnormal change in vocal quality, pitch, loudness, or "
            "vocal effort. It can result from vocal misuse/overuse (e.g. chronic yelling), "
            "structural changes to the vocal folds (e.g. nodules, polyps), neurological "
            "conditions, or medical issues such as reflux — the underlying cause "
            "significantly affects both prognosis and treatment, so medical evaluation is "
            "an important part of assessment."
        ),
        possible_characteristics=(
            "Hoarse, breathy, strained, or rough vocal quality; reduced pitch range or "
            "pitch breaks; vocal fatigue with extended talking; reduced loudness or "
            "difficulty being heard; in children, chronic hoarseness is a common presenting "
            "concern."
        ),
        speech_features=(
            "Perceptual voice-quality changes rather than articulation or language "
            "difficulty; may be accompanied by visible vocal strain or effort; severity and "
            "pattern vary considerably depending on the underlying cause."
        ),
        assessment_notes=(
            "Assessment typically involves an ENT (otolaryngologist) examination — often "
            "including visualization of the vocal folds — alongside a speech-language "
            "pathologist's perceptual and acoustic voice evaluation. Because dysphonia can "
            "signal a range of underlying causes, some of which are medical rather than "
            "purely behavioral, professional medical evaluation (not just AI screening) is "
            "particularly important here."
        ),
    )

    social_communication_disorder = Disorder(
        category_id=social_comm_category.id,
        name="Social Communication Difficulties",
        slug="social-communication-difficulties",
        language="en",
        overview=(
            "Social communication difficulties involve challenges using language "
            "appropriately in social contexts — for example, adjusting communication style "
            "for different listeners or settings, following conversational rules like "
            "turn-taking, or understanding non-literal language (idioms, humor, inference). "
            "These difficulties can occur on their own or alongside other conditions such "
            "as autism, DLD, or ADHD, so careful differential consideration matters."
        ),
        possible_characteristics=(
            "Difficulty with conversational turn-taking or staying on topic; literal "
            "interpretation of figurative language; difficulty adjusting tone/formality for "
            "different listeners (e.g. talking to a teacher the same way as a friend); "
            "difficulty following social communication cues like body language or tone of voice."
        ),
        speech_features=(
            "Speech-sound production and grammar may be entirely typical — the difficulty is "
            "specifically in the pragmatic (social-use) dimension of language, which "
            "requires observing real conversational interaction to assess, not just "
            "single-word or sentence-level testing."
        ),
        assessment_notes=(
            "Assessment typically involves structured and naturalistic observation of "
            "conversational interaction, caregiver/teacher interview, and standardized "
            "pragmatic-language measures, usually by a speech-language pathologist, "
            "sometimes alongside other specialists depending on co-occurring concerns. AI "
            "screening in this platform does not evaluate social/pragmatic language at all "
            "in its current form — this disorder page is informational content only."
        ),
    )

    db.add_all(
        [cluttering, dev_language_disorder, articulation_disorder, dysphonia, social_communication_disorder]
    )
    db.flush()

    exercises = [
        Exercise(
            title="Slow Speech Practice",
            category="fluency",
            difficulty="beginner",
            language="en",
            instructions="Read the provided passage slowly, pausing naturally at punctuation.",
            duration_minutes=10,
            goal="Reduce speaking rate to support fluency.",
            disorder_id=stuttering.id,
        ),
        Exercise(
            title="Easy Onset Practice",
            category="fluency",
            difficulty="intermediate",
            language="en",
            instructions="Practice starting words with a gentle, gradual onset of voicing.",
            duration_minutes=15,
            goal="Reduce tension at the start of utterances.",
            disorder_id=stuttering.id,
        ),
        Exercise(
            title="Breath Support for Voice",
            category="voice",
            difficulty="beginner",
            language="en",
            instructions="Practice diaphragmatic breathing exercises before speaking tasks.",
            duration_minutes=10,
            goal="Improve breath support for voice production.",
        ),
        Exercise(
            title="General Communication Warm-up",
            category="communication",
            difficulty="beginner",
            language="en",
            instructions="Describe your day out loud in 5 short sentences.",
            duration_minutes=5,
            goal="General verbal expression practice.",
        ),
        Exercise(
            title="Syllable Sequencing Practice",
            category="articulation",
            difficulty="beginner",
            language="en",
            instructions=(
                "Practice repeating simple syllable sequences (e.g. 'pa-ta-ka'), then move to "
                "sequencing them into short familiar words. Focus on consistency across repeated "
                "attempts, not speed."
            ),
            duration_minutes=10,
            goal="Improve consistency and sequencing of speech sound production.",
            disorder_id=apraxia.id,
        ),
        Exercise(
            title="Prosody and Stress Practice",
            category="articulation",
            difficulty="intermediate",
            language="en",
            instructions=(
                "Practice two- and three-syllable words with clear, exaggerated stress on the "
                "correct syllable, then gradually reduce exaggeration toward natural speech."
            ),
            duration_minutes=10,
            goal="Improve natural rhythm, stress, and intonation of speech.",
            disorder_id=apraxia.id,
        ),
        Exercise(
            title="Oral-Motor Strength and Range of Motion",
            category="articulation",
            difficulty="beginner",
            language="en",
            instructions=(
                "Under guidance, practice non-speech oral-motor exercises (e.g. lip rounding/"
                "spreading, tongue lateralization) followed by exaggerated articulation of target "
                "sounds to support precision."
            ),
            duration_minutes=10,
            goal="Support articulatory precision affected by reduced muscle control.",
            disorder_id=dysarthria.id,
        ),
        Exercise(
            title="Loudness and Breath Support Drill",
            category="voice",
            difficulty="beginner",
            language="en",
            instructions=(
                "Practice sustained vowel phonation at a steady, comfortably loud volume, then "
                "extend to short phrases while maintaining consistent loudness."
            ),
            duration_minutes=10,
            goal="Improve breath support and vocal loudness control.",
            disorder_id=dysarthria.id,
        ),
        Exercise(
            title="Word-Finding Practice",
            category="language",
            difficulty="beginner",
            language="en",
            instructions=(
                "Practice naming pictured objects, then describing their category, use, and "
                "one related word if the exact name doesn't come quickly."
            ),
            duration_minutes=10,
            goal="Support word retrieval and use of compensatory strategies.",
            disorder_id=aphasia.id,
        ),
        Exercise(
            title="Sentence Building Practice",
            category="language",
            difficulty="intermediate",
            language="en",
            instructions=(
                "Practice building short, complete sentences from a picture or prompt, "
                "gradually increasing sentence length as accuracy improves."
            ),
            duration_minutes=15,
            goal="Support sentence formulation and grammatical structure.",
            disorder_id=aphasia.id,
        ),
        Exercise(
            title="Rate Control with a Pacing Board",
            category="fluency",
            difficulty="intermediate",
            language="en",
            instructions=(
                "Read a short passage while tapping a finger on a printed pacing board once "
                "per syllable, deliberately slowing and evening out the rhythm of speech."
            ),
            duration_minutes=10,
            goal="Reduce irregular/excessive speaking rate.",
            disorder_id=cluttering.id,
        ),
        Exercise(
            title="Self-Monitoring Recording Review",
            category="fluency",
            difficulty="advanced",
            language="en",
            instructions=(
                "Record one minute of spontaneous speech, then listen back and mark any "
                "spots that were hard to understand or where words ran together."
            ),
            duration_minutes=15,
            goal="Build self-awareness of clarity/rate breakdowns.",
            disorder_id=cluttering.id,
        ),
        Exercise(
            title="Following Multi-Step Directions",
            category="language",
            difficulty="beginner",
            language="en",
            instructions=(
                "Practice listening to and carrying out 2-3 step spoken instructions "
                "(e.g. 'pick up the red block, then put it in the box')."
            ),
            duration_minutes=10,
            goal="Support auditory comprehension and working memory for language.",
            disorder_id=dev_language_disorder.id,
        ),
        Exercise(
            title="Story Retelling Practice",
            category="language",
            difficulty="intermediate",
            language="en",
            instructions=(
                "Listen to or read a short story, then retell it in order, covering who, "
                "what, where, and how it ended."
            ),
            duration_minutes=15,
            goal="Support narrative organization and expressive language.",
            disorder_id=dev_language_disorder.id,
        ),
        Exercise(
            title="Target Sound Drill",
            category="articulation",
            difficulty="beginner",
            language="en",
            instructions=(
                "Practice a specific target sound in isolation, then in syllables (e.g. "
                "'sa, se, si, so, su'), focusing on correct tongue/lip placement."
            ),
            duration_minutes=10,
            goal="Establish correct production of a target speech sound.",
            disorder_id=articulation_disorder.id,
        ),
        Exercise(
            title="Minimal Pairs Practice",
            category="articulation",
            difficulty="intermediate",
            language="en",
            instructions=(
                "Practice word pairs that differ by only the target sound (e.g. 'sip' vs. "
                "'ship'), saying each clearly enough that a listener could tell them apart."
            ),
            duration_minutes=15,
            goal="Improve production accuracy and listener intelligibility.",
            disorder_id=articulation_disorder.id,
        ),
        Exercise(
            title="Resonant Voice Warm-up",
            category="voice",
            difficulty="beginner",
            language="en",
            instructions=(
                "Practice gentle humming that transitions into open vowel sounds ('mmm-ah'), "
                "focusing on an easy, forward vocal placement without strain."
            ),
            duration_minutes=10,
            goal="Reduce vocal strain and support healthy voice production.",
            disorder_id=dysphonia.id,
        ),
        Exercise(
            title="Vocal Hygiene Check-in",
            category="voice",
            difficulty="beginner",
            language="en",
            instructions=(
                "Review daily vocal habits (hydration, throat-clearing frequency, shouting) "
                "and note any patterns that may be straining the voice."
            ),
            duration_minutes=5,
            goal="Build awareness of vocal-hygiene factors affecting voice quality.",
            disorder_id=dysphonia.id,
        ),
        Exercise(
            title="Conversational Turn-Taking Practice",
            category="communication",
            difficulty="intermediate",
            language="en",
            instructions=(
                "Practice a short conversation with a partner, focusing on waiting for a "
                "pause before responding and staying on the same topic for 3-4 exchanges."
            ),
            duration_minutes=15,
            goal="Support conversational turn-taking and topic maintenance.",
            disorder_id=social_communication_disorder.id,
        ),
        Exercise(
            title="Idioms and Figurative Language Practice",
            category="communication",
            difficulty="advanced",
            language="en",
            instructions=(
                "Review a common idiom or figure of speech (e.g. 'it's raining cats and "
                "dogs'), discuss its literal vs. intended meaning, then use it correctly in "
                "a sentence."
            ),
            duration_minutes=10,
            goal="Support understanding of non-literal language.",
            disorder_id=social_communication_disorder.id,
        ),
    ]
    db.add_all(exercises)

    word_matching_game = Game(
        title="Word & Sound Matching",
        slug="word-sound-matching",
        game_type="word_matching",
        description="Match each word to its correct meaning.",
        difficulty="beginner",
        language="en",
        content_json=json.dumps(
            {
                "pairs": [
                    {"word": "Cat", "match": "A small domesticated animal that says meow"},
                    {"word": "Sun", "match": "The star at the center of our solar system"},
                    {"word": "Book", "match": "A set of printed pages bound together"},
                    {"word": "Tree", "match": "A tall plant with a trunk and branches"},
                    {"word": "River", "match": "A large natural stream of flowing water"},
                ]
            }
        ),
    )
    db.add(word_matching_game)

    sentence_builder_game = Game(
        title="Sentence Builder",
        slug="sentence-builder",
        game_type="sentence_builder",
        description="Rearrange the shuffled words to build a correct sentence.",
        difficulty="intermediate",
        language="en",
        content_json=json.dumps(
            {
                "sentences": [
                    {"words": ["The", "cat", "sat", "on", "the", "mat"], "correct_sentence": "The cat sat on the mat"},
                    {"words": ["She", "likes", "to", "read", "books"], "correct_sentence": "She likes to read books"},
                    {"words": ["We", "are", "going", "to", "the", "park"], "correct_sentence": "We are going to the park"},
                    {"words": ["He", "plays", "football", "every", "day"], "correct_sentence": "He plays football every day"},
                    {"words": ["The", "sun", "is", "very", "bright", "today"], "correct_sentence": "The sun is very bright today"},
                ]
            }
        ),
    )
    db.add(sentence_builder_game)

    memory_match_game = Game(
        title="Memory Match",
        slug="memory-match",
        game_type="memory_match",
        description="Decide whether the two cards shown belong to the same pair.",
        difficulty="beginner",
        language="en",
        content_json=json.dumps(
            {
                "pairs": [
                    {"id": "1", "a": "Cat", "b": "\U0001F431"},
                    {"id": "2", "a": "Dog", "b": "\U0001F436"},
                    {"id": "3", "a": "Sun", "b": "\u2600\ufe0f"},
                    {"id": "4", "a": "Tree", "b": "\U0001F333"},
                    {"id": "5", "a": "Car", "b": "\U0001F697"},
                    {"id": "6", "a": "Book", "b": "\U0001F4DA"},
                ]
            }
        ),
    )
    db.add(memory_match_game)

    sound_hunt_game = Game(
        title="Sound Hunt: /S/ Sound",
        slug="sound-hunt-s",
        game_type="sound_hunt",
        description="Listen for words that start with the /s/ sound.",
        difficulty="beginner",
        language="en",
        content_json=json.dumps(
            {
                "target_sound": "s",
                "items": [
                    {"word": "sun", "starts_with_target": True},
                    {"word": "snake", "starts_with_target": True},
                    {"word": "sock", "starts_with_target": True},
                    {"word": "cat", "starts_with_target": False},
                    {"word": "moon", "starts_with_target": False},
                    {"word": "soap", "starts_with_target": True},
                    {"word": "dog", "starts_with_target": False},
                    {"word": "star", "starts_with_target": True},
                ]
            }
        ),
    )
    db.add(sound_hunt_game)

    picture_naming_game = Game(
        title="Picture Naming",
        slug="picture-naming",
        game_type="picture_naming",
        description="Look at the picture and say (or type) its name out loud.",
        difficulty="beginner",
        language="en",
        content_json=json.dumps(
            {
                "items": [
                    {"image_description": "A red apple", "target_word": "apple"},
                    {"image_description": "A yellow banana", "target_word": "banana"},
                    {"image_description": "A small brown dog", "target_word": "dog"},
                    {"image_description": "A blue ball", "target_word": "ball"},
                    {"image_description": "A pair of shoes", "target_word": "shoes"},
                ]
            }
        ),
    )
    db.add(picture_naming_game)

    db.commit()

    sample_kb_text = (
        "Stuttering: An Overview for Families and Clinicians\n\n"
        "Stuttering is a communication disorder that disrupts the normal flow of speech. "
        "It commonly includes repetitions of sounds or syllables, prolongations of sounds, "
        "and blocks where the person is unable to produce a sound despite effort.\n\n"
        "Onset typically occurs in early childhood, often between the ages of 2 and 6, "
        "during a period of rapid language development. Many children who begin stuttering "
        "recover naturally within the first year or two, while others continue to stutter "
        "into adolescence and adulthood.\n\n"
        "Assessment by a qualified speech-language pathologist should consider frequency and "
        "type of disfluencies, secondary behaviors such as facial tension, the impact on daily "
        "communication, and family history. AI-based screening tools can help flag patterns for "
        "further review, but they are not a substitute for a professional evaluation.\n\n"
        "Common evidence-based approaches include fluency shaping techniques, stuttering "
        "modification therapy, and family-centered approaches for young children such as the "
        "Lidcombe Program. Treatment planning should always be individualized.\n"
    )
    apraxia_kb_text = (
        "Childhood Apraxia of Speech: An Overview for Families and Clinicians\n\n"
        "Childhood Apraxia of Speech (CAS) is a neurological motor speech disorder in which "
        "a child has difficulty planning and coordinating the precise, sequenced movements "
        "needed for speech. It is not caused by muscle weakness — the muscles themselves work "
        "normally for non-speech tasks; the difficulty lies in the brain's ability to plan and "
        "program speech movements.\n\n"
        "Children with CAS often show inconsistent errors: the same word may be produced "
        "differently each time it is attempted. Errors tend to increase with the length and "
        "complexity of words and phrases, and prosody (the rhythm and stress of speech) is "
        "often affected, sometimes producing a flat or evenly-stressed pattern.\n\n"
        "Diagnosis is typically made by a speech-language pathologist after ruling out muscle "
        "weakness through an oral-motor exam, and after observing the characteristic pattern "
        "of inconsistent errors, groping movements, and prosodic difficulty across single "
        "words, phrases, and connected speech — often over more than one session, since CAS "
        "can resemble other speech sound disorders early on.\n\n"
        "Evidence-based treatment approaches for CAS emphasize principles of motor learning: "
        "frequent, intensive practice; a focus on movement sequences rather than isolated "
        "sounds; and systematic progression from simple to more complex targets. Treatment "
        "plans are highly individualized and typically involve frequent short sessions.\n"
    )
    dysarthria_kb_text = (
        "Dysarthria: An Overview for Families and Clinicians\n\n"
        "Dysarthria is a motor speech disorder caused by weakness, paralysis, or "
        "incoordination of the muscles used for speech, resulting from damage to the nervous "
        "system. Common causes include stroke, traumatic brain injury, Parkinson's disease, "
        "amyotrophic lateral sclerosis (ALS), and cerebral palsy.\n\n"
        "Because dysarthria affects the physical execution of speech movements rather than "
        "the planning of those movements, speech may sound slurred, slow, or strained, with "
        "changes to voice quality, loudness, and nasal resonance depending on which muscles "
        "and nerve pathways are affected.\n\n"
        "There are several recognized subtypes of dysarthria — including spastic, flaccid, "
        "ataxic, hypokinetic, and hyperkinetic — each associated with damage to a different "
        "part of the nervous system and each with a somewhat different perceptual speech "
        "pattern. Identifying the subtype can help guide both medical and therapeutic "
        "management.\n\n"
        "Assessment typically combines a perceptual speech evaluation with an oral-motor exam "
        "and is usually coordinated with the person's broader medical team, since dysarthria "
        "is a symptom of an underlying neurological condition rather than a standalone "
        "diagnosis. Treatment approaches may include exercises to improve breath support, "
        "strategies to improve speech clarity (e.g. slowing rate, over-articulating), and, in "
        "some cases, augmentative and alternative communication (AAC) supports.\n"
    )
    aphasia_kb_text = (
        "Aphasia: An Overview for Families and Clinicians\n\n"
        "Aphasia is an acquired language disorder caused by damage to the language-dominant "
        "areas of the brain, most commonly from a stroke, but also from traumatic brain "
        "injury, brain tumors, infections, or progressive neurological conditions.\n\n"
        "Aphasia can affect any combination of speaking, understanding spoken language, "
        "reading, and writing. It does not affect a person's intelligence, and many people "
        "with aphasia know exactly what they want to say but have difficulty retrieving or "
        "producing the words. Word-finding difficulty is one of the most common features "
        "across nearly all types of aphasia.\n\n"
        "Different patterns of aphasia are often described in relation to fluency: some "
        "people speak fluently but with frequent word-finding pauses and word substitutions, "
        "while others produce speech that is slow, effortful, and reduced to short phrases. "
        "Comprehension can be relatively preserved or significantly affected, independent of "
        "how fluent the person's own speech sounds.\n\n"
        "Assessment is typically performed by a speech-language pathologist using standardized "
        "tests covering auditory comprehension, verbal expression, reading, and writing, "
        "alongside a review of medical history and brain imaging where available. Treatment is "
        "highly individualized and may include impairment-based approaches targeting specific "
        "language skills, communication strategy training, and involvement of family members "
        "or communication partners to support everyday conversation.\n"
    )

    kb_documents = [
        (
            "Stuttering: An Overview for Families and Clinicians",
            sample_kb_text,
            "Fluency Disorders",
            "stuttering_overview.txt",
        ),
        (
            "Childhood Apraxia of Speech: An Overview for Families and Clinicians",
            apraxia_kb_text,
            "Motor Speech Disorders",
            "apraxia_overview.txt",
        ),
        (
            "Dysarthria: An Overview for Families and Clinicians",
            dysarthria_kb_text,
            "Motor Speech Disorders",
            "dysarthria_overview.txt",
        ),
        (
            "Aphasia: An Overview for Families and Clinicians",
            aphasia_kb_text,
            "Language Disorders",
            "aphasia_overview.txt",
        ),
        (
            "Cluttering: An Overview for Families and Clinicians",
            (
                "Cluttering: An Overview for Families and Clinicians\n\n"
                "Cluttering is a fluency disorder marked by a speech rate perceived as too "
                "fast or irregular, alongside breakdowns in clarity not explained by typical "
                "stuttering-type disfluencies. It is frequently under-recognized and can "
                "co-occur with stuttering.\n\n"
                "Unlike many people who stutter, people who clutter often have limited "
                "awareness of their own disfluency, and listeners commonly report needing to "
                "ask for repetition rather than noticing obvious sound repetitions or blocks.\n\n"
                "Differential assessment — distinguishing cluttering from stuttering and from "
                "typical fast speech — is an important first step and is best performed by a "
                "speech-language pathologist using both perceptual judgment and recorded-speech "
                "rate/clarity measures.\n\n"
                "Treatment approaches commonly focus on increasing self-monitoring and rate "
                "control, along with language-organization strategies when language "
                "formulation difficulties are also present.\n"
            ),
            "Fluency Disorders",
            "cluttering_overview.txt",
        ),
        (
            "Developmental Language Disorder: An Overview for Families and Clinicians",
            (
                "Developmental Language Disorder (DLD): An Overview for Families and Clinicians\n\n"
                "DLD is a difficulty learning and using language that is not explained by "
                "another condition such as hearing loss, intellectual disability, or autism. "
                "It begins in early childhood and, while its impact can change significantly "
                "with support, some form of the difficulty can persist into adulthood.\n\n"
                "Children with DLD often have a smaller vocabulary than peers, difficulty with "
                "grammar such as verb tense marking, trouble following multi-step spoken "
                "instructions, and difficulty organizing spoken narratives — despite typical "
                "hearing and typical nonverbal cognitive ability.\n\n"
                "Assessment by a speech-language pathologist uses standardized tests of "
                "vocabulary, grammar, and narrative/discourse skills, combined with case "
                "history to rule out other explanatory conditions.\n\n"
                "Because DLD is language-based rather than speech-sound-based, intervention "
                "typically targets vocabulary growth, sentence structure, and narrative/"
                "discourse skills directly, often through structured, high-repetition practice "
                "embedded in meaningful activities.\n"
            ),
            "Language Disorders",
            "dld_overview.txt",
        ),
        (
            "Articulation Disorder: An Overview for Families and Clinicians",
            (
                "Articulation Disorder: An Overview for Families and Clinicians\n\n"
                "An articulation disorder is difficulty physically producing specific speech "
                "sounds correctly, resulting in substitutions, omissions, additions, or "
                "distortions. It differs from a phonological disorder, which involves the "
                "underlying sound-pattern rules of the language rather than physical "
                "production — the two frequently co-occur and can be hard to tell apart "
                "without professional assessment.\n\n"
                "Common patterns include a persistent lisp on /s/ and /z/, difficulty with "
                "/r/, or a distorted (e.g. lateral) production of certain sounds. Errors tend "
                "to be relatively consistent across words, which helps distinguish this from "
                "the word-to-word inconsistency seen in apraxia of speech.\n\n"
                "Assessment includes a single-word and connected-speech articulation test, an "
                "oral-motor exam, and comparison against typical developmental sound-mastery "
                "norms, since many sound errors are entirely typical at younger ages and "
                "resolve without intervention.\n\n"
                "Treatment (traditional articulation therapy) typically targets the specific "
                "sound(s) in isolation, then in syllables, words, phrases, and conversation, "
                "using auditory, visual, and tactile cues to help the person learn the correct "
                "placement and movement.\n"
            ),
            "Speech Sound Disorders",
            "articulation_overview.txt",
        ),
        (
            "Dysphonia (Voice Disorder): An Overview for Families and Clinicians",
            (
                "Dysphonia (Voice Disorder): An Overview for Families and Clinicians\n\n"
                "Dysphonia is an abnormal change in vocal quality, pitch, loudness, or vocal "
                "effort. Causes range from vocal misuse/overuse to structural changes of the "
                "vocal folds (nodules, polyps), neurological conditions, or medical issues "
                "such as reflux — the underlying cause significantly affects prognosis and "
                "treatment.\n\n"
                "Common presentations include a hoarse, breathy, strained, or rough vocal "
                "quality; reduced pitch range or pitch breaks; vocal fatigue with extended "
                "talking; and reduced loudness. In children, chronic hoarseness is a common "
                "presenting concern that warrants evaluation.\n\n"
                "Because dysphonia can signal a range of underlying medical causes, assessment "
                "typically starts with an ENT examination — often including direct "
                "visualization of the vocal folds — alongside a speech-language pathologist's "
                "perceptual and acoustic voice evaluation.\n\n"
                "Voice therapy approaches vary by cause but often include vocal hygiene "
                "education, resonant-voice or flow-based phonation techniques, and, when "
                "structural changes are present, coordination with medical/surgical "
                "management.\n"
            ),
            "Voice Disorders",
            "dysphonia_overview.txt",
        ),
        (
            "Social Communication Difficulties: An Overview for Families and Clinicians",
            (
                "Social Communication Difficulties: An Overview for Families and Clinicians\n\n"
                "Social communication difficulties involve challenges using language "
                "appropriately in social contexts — adjusting communication style for "
                "different listeners, following conversational turn-taking, or understanding "
                "non-literal language such as idioms, humor, or inference. These can occur on "
                "their own or alongside other conditions such as autism, Developmental "
                "Language Disorder, or ADHD.\n\n"
                "Common characteristics include difficulty staying on topic in conversation, "
                "literal interpretation of figurative language, difficulty adjusting formality "
                "for different listeners, and difficulty reading social communication cues "
                "such as body language or tone of voice.\n\n"
                "Because the difficulty is specifically in the pragmatic (social-use) "
                "dimension of language, assessment requires observing real conversational "
                "interaction — structured and naturalistic observation, caregiver/teacher "
                "interview, and standardized pragmatic-language measures — rather than "
                "single-word or sentence-level testing alone.\n\n"
                "Intervention commonly uses structured social-skills practice, video modeling, "
                "and explicit teaching of conversational rules and perspective-taking, "
                "generalized into real social contexts with support from caregivers and "
                "educators.\n"
            ),
            "Other Communication Areas",
            "social_communication_overview.txt",
        ),
    ]

    for title, text, category_name, filename in kb_documents:
        kb_doc = KnowledgeDocument(
            title=title,
            author="Sample Educational Content",
            publication_year=2024,
            document_type="guideline",
            source_type="internal",
            disorder_category=category_name,
            language="en",
            original_filename=filename,
            storage_path=f"seed/{filename}",
            status="PROCESSING",
        )
        db.add(kb_doc)
        db.commit()
        db.refresh(kb_doc)
        ingest_document_text(db, kb_doc, text)
        kb_doc.status = "INDEXED"
        db.add(kb_doc)
        db.commit()

    print(
        "Seeded disorder taxonomy (9 disorders across 6 categories), "
        "20 exercises, 5 games, and 9 Knowledge Base documents."
    )


def main() -> None:
    # In production, tables should come from `alembic upgrade head`, not this.
    # create_all() here just makes local/dev bootstrapping (and tests) painless.
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        roles_by_name = seed_roles_and_permissions(db)
        seed_first_admin(db, roles_by_name)
        seed_first_specialist(db, roles_by_name)
        seed_sample_content(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
