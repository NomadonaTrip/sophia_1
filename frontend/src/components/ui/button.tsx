import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-sage-400 disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0 cursor-pointer",
  {
    variants: {
      variant: {
        default:
          "bg-text-primary text-midnight-900 shadow-sm hover:bg-text-primary/90",
        destructive:
          "bg-coral-500 text-text-primary shadow-sm hover:bg-coral-400",
        outline:
          "border border-midnight-600 bg-transparent text-text-primary shadow-sm hover:bg-midnight-700",
        secondary:
          "bg-midnight-700 text-text-primary border border-midnight-600 shadow-sm hover:bg-midnight-600",
        ghost:
          "text-text-muted hover:bg-midnight-700 hover:text-text-secondary",
        link: "text-sage-400 underline-offset-4 hover:underline",
        sage: "bg-sage-500 text-white shadow-[0_0_12px_rgba(74,124,89,0.3)] hover:bg-sage-400",
      },
      size: {
        default: "h-9 px-4 py-2",
        sm: "h-8 rounded-md px-3 text-xs",
        lg: "h-10 rounded-md px-8",
        icon: "h-9 w-9",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button"
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    )
  },
)
Button.displayName = "Button"

export { Button, buttonVariants }
