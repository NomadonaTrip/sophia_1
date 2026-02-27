import { useCallback } from 'react'
import { BatchApprovalGrid } from '@/components/approval/BatchApprovalGrid'
import { useKeyboardShortcuts } from '@/hooks/useKeyboardShortcuts'
import type { ContentDraft } from '@/components/approval/ContentItem'

// Demo data for approval queue
const DEMO_DRAFTS: ContentDraft[] = [
  {
    id: 101,
    client_id: 1,
    client_name: "Maple & Main Bakery",
    platform: 'instagram',
    copy: "Fresh sourdough ready for Saturday morning. Our new rosemary olive oil loaf has been a hit this week -- stop by before noon if you want one warm from the oven.",
    voice_alignment_pct: 91,
    research_source_count: 2,
    content_pillar: 'Product',
    scheduled_time: 'Sat 8:00 AM',
    status: 'in_review',
    hashtags: ['HamiltonEats', 'SourdoughBread', 'LocalBakery'],
  },
  {
    id: 102,
    client_id: 1,
    client_name: "Maple & Main Bakery",
    platform: 'facebook',
    copy: "This week's special: Dark chocolate hazelnut croissants. Limited batch every Thursday. Pre-order through our page or just drop in -- first come, first served.",
    voice_alignment_pct: 88,
    research_source_count: 1,
    content_pillar: 'Promotion',
    scheduled_time: 'Thu 7:30 AM',
    status: 'in_review',
  },
  {
    id: 103,
    client_id: 4,
    client_name: "Peak Fitness Studio",
    platform: 'instagram',
    copy: "Spring challenge starts March 1. Six weeks of guided programming, nutrition coaching, and community accountability. Early bird pricing through this weekend.",
    voice_alignment_pct: 85,
    research_source_count: 3,
    content_pillar: 'Engagement',
    scheduled_time: 'Mon 6:00 AM',
    status: 'in_review',
    hashtags: ['HamiltonFitness', 'SpringChallenge', 'FitnessGoals'],
  },
  {
    id: 104,
    client_id: 5,
    client_name: "Birchwood Dental",
    platform: 'facebook',
    copy: "March is Oral Health Month. We're offering complimentary dental screenings for kids under 12 all month. Book online or call us to reserve a spot.",
    voice_alignment_pct: 92,
    research_source_count: 2,
    content_pillar: 'Community',
    scheduled_time: 'Tue 10:00 AM',
    status: 'in_review',
  },
  {
    id: 105,
    client_id: 6,
    client_name: "Anchor Property Management",
    platform: 'instagram',
    copy: "Thinking about renting out your basement apartment? Here's what Hamilton landlords need to know about the 2026 building code changes affecting secondary suites.",
    voice_alignment_pct: 87,
    research_source_count: 4,
    content_pillar: 'Education',
    scheduled_time: 'Wed 12:00 PM',
    status: 'in_review',
    hashtags: ['HamiltonRealEstate', 'LandlordTips', 'SecondaryUnits'],
  },
  {
    id: 106,
    client_id: 7,
    client_name: "Lakeside Auto Care",
    platform: 'facebook',
    copy: "Winter tire changeover season is here. Book early to avoid the rush -- we're already filling up March weekends. Free brake inspection with every tire swap.",
    voice_alignment_pct: 89,
    research_source_count: 1,
    content_pillar: 'Seasonal',
    scheduled_time: 'Mon 9:00 AM',
    status: 'in_review',
  },
]

export function ApprovalQueue() {
  const handleApprove = useCallback((draftId: number) => {
    console.log('Approve:', draftId)
  }, [])

  const handleReject = useCallback((draftId: number) => {
    console.log('Reject:', draftId)
  }, [])

  const handleEdit = useCallback((draftId: number) => {
    console.log('Edit:', draftId)
  }, [])

  // Keyboard shortcuts for queue navigation
  useKeyboardShortcuts({
    onApprove: () => console.log('Keyboard: approve focused'),
    onReject: () => console.log('Keyboard: reject focused'),
    onEdit: () => console.log('Keyboard: edit focused'),
    onNext: () => console.log('Keyboard: next item'),
  })

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h2 className="text-lg font-medium text-text-primary mb-1">
          Approval Queue
        </h2>
        <p className="text-xs text-text-muted">
          Review and approve content across your portfolio. Use keyboard shortcuts: A (approve), R (reject), E (edit), N (next).
        </p>
      </div>

      <BatchApprovalGrid
        drafts={DEMO_DRAFTS}
        onApprove={handleApprove}
        onReject={handleReject}
        onEdit={handleEdit}
      />
    </div>
  )
}
