import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const badgeVariants = cva(
  "inline-flex items-center rounded-md border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-sage-400 focus:ring-offset-2",
  {
    variants: {
      variant: {
        default:
          "border-transparent bg-text-primary text-midnight-900",
        secondary:
          "border-transparent bg-midnight-700 text-text-secondary",
        destructive:
          "border-transparent bg-coral-500 text-text-primary",
        outline: "border-midnight-600 text-text-secondary",
        sage: "border-transparent bg-sage-500/20 text-sage-300",
        amber: "border-transparent bg-amber-500/20 text-amber-400",
        coral: "border-transparent bg-coral-500/20 text-coral-400",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  )
}

export { Badge, badgeVariants }
