"""Seed the database with demo clients and drafts for UI testing."""

from sophia.db.engine import SessionLocal, engine
from sophia.db.base import Base

# Import all models so create_all knows about them
import sophia.intelligence.models  # noqa: F401
import sophia.content.models  # noqa: F401
import sophia.approval.models  # noqa: F401
import sophia.research.models  # noqa: F401
import sophia.institutional.models  # noqa: F401

from sophia.intelligence.models import Client
from sophia.content.models import ContentDraft

# Create tables
Base.metadata.create_all(engine)

db = SessionLocal()

# Check if already seeded
if db.query(Client).count() > 0:
    print("Database already seeded. Skipping.")
    db.close()
    exit(0)

# --- Clients ---
clients = [
    Client(id=1, name="Maple & Main Bakery", industry="Food & Beverage",
           business_description="Artisan bakery in downtown Hamilton",
           geography_area="Hamilton, ON"),
    Client(id=4, name="Peak Fitness Studio", industry="Health & Fitness",
           business_description="Boutique fitness studio",
           geography_area="Hamilton, ON"),
    Client(id=5, name="Birchwood Dental", industry="Healthcare",
           business_description="Family dental practice",
           geography_area="Burlington, ON"),
    Client(id=6, name="Anchor Property Management", industry="Real Estate",
           business_description="Residential property management",
           geography_area="Hamilton, ON"),
    Client(id=7, name="Lakeside Auto Care", industry="Automotive",
           business_description="Full-service auto shop",
           geography_area="Burlington, ON"),
]
db.add_all(clients)
db.flush()

# --- Drafts (in_review status for approval queue) ---
drafts = [
    ContentDraft(
        id=101, client_id=1, platform="instagram", content_type="feed",
        copy="Fresh sourdough ready for Saturday morning. Our new rosemary olive oil loaf has been a hit this week -- stop by before noon if you want one warm from the oven.",
        image_prompt="Warm rosemary olive oil sourdough loaf on wooden cutting board, steam rising, rustic bakery setting",
        image_ratio="1:1",
        voice_confidence_pct=91,
        content_pillar="Product",
        hashtags=["HamiltonEats", "SourdoughBread", "LocalBakery"],
        status="in_review",
        gate_status="passed",
        gate_report={
            "voice_alignment": {"passed": True, "score": 0.91},
            "research_grounding": {"passed": True, "score": 0.85},
            "sensitivity": {"passed": True},
            "originality": {"passed": True, "score": 0.88},
        },
    ),
    ContentDraft(
        id=102, client_id=1, platform="facebook", content_type="feed",
        copy="This week's special: Dark chocolate hazelnut croissants. Limited batch every Thursday. Pre-order through our page or just drop in -- first come, first served.",
        image_prompt="Dark chocolate hazelnut croissants on parchment paper, flaky layers visible",
        image_ratio="1.91:1",
        voice_confidence_pct=88,
        content_pillar="Promotion",
        status="in_review",
        gate_status="passed",
        gate_report={
            "voice_alignment": {"passed": True, "score": 0.88},
            "research_grounding": {"passed": True, "score": 0.72},
            "sensitivity": {"passed": True},
        },
    ),
    ContentDraft(
        id=103, client_id=4, platform="instagram", content_type="feed",
        copy="Spring challenge starts March 1. Six weeks of guided programming, nutrition coaching, and community accountability. Early bird pricing through this weekend.",
        image_prompt="Group fitness class high-fiving, energetic spring morning light",
        image_ratio="4:5",
        voice_confidence_pct=85,
        content_pillar="Engagement",
        hashtags=["HamiltonFitness", "SpringChallenge", "FitnessGoals"],
        status="in_review",
        gate_status="passed",
        gate_report={
            "voice_alignment": {"passed": True, "score": 0.85},
            "research_grounding": {"passed": True, "score": 0.90},
            "sensitivity": {"passed": True},
            "originality": {"passed": True, "score": 0.92},
        },
    ),
    ContentDraft(
        id=104, client_id=5, platform="facebook", content_type="feed",
        copy="March is Oral Health Month. We're offering complimentary dental screenings for kids under 12 all month. Book online or call us to reserve a spot.",
        image_prompt="Smiling child in dental chair giving thumbs up, friendly dentist in background",
        image_ratio="1.91:1",
        voice_confidence_pct=92,
        content_pillar="Community",
        status="in_review",
        gate_status="passed",
    ),
    ContentDraft(
        id=105, client_id=6, platform="instagram", content_type="feed",
        copy="Thinking about renting out your basement apartment? Here's what Hamilton landlords need to know about the 2026 building code changes affecting secondary suites.",
        image_prompt="Modern basement apartment renovation, bright and clean",
        image_ratio="1:1",
        voice_confidence_pct=87,
        content_pillar="Education",
        hashtags=["HamiltonRealEstate", "LandlordTips", "SecondaryUnits"],
        status="in_review",
        gate_status="passed",
        gate_report={
            "voice_alignment": {"passed": True, "score": 0.87},
            "research_grounding": {"passed": True, "score": 0.95},
            "sensitivity": {"passed": True},
            "originality": {"passed": False, "score": 0.55},
        },
    ),
    ContentDraft(
        id=106, client_id=7, platform="facebook", content_type="feed",
        copy="Winter tire changeover season is here. Book early to avoid the rush -- we're already filling up March weekends. Free brake inspection with every tire swap.",
        image_prompt="Mechanic changing winter tires in clean auto shop",
        image_ratio="1.91:1",
        voice_confidence_pct=89,
        content_pillar="Seasonal",
        status="in_review",
        gate_status="passed",
    ),
]
db.add_all(drafts)
db.commit()
db.close()

print(f"Seeded {len(clients)} clients and {len(drafts)} drafts.")
