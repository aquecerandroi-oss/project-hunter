"use client";

import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

export const Sheet = DialogPrimitive.Root;
export const SheetTrigger = DialogPrimitive.Trigger;
export const SheetClose = DialogPrimitive.Close;

const SIDE_CLASSES = {
  left: "inset-y-0 left-0 h-full w-3/4 max-w-xs border-r",
  right: "inset-y-0 right-0 h-full w-3/4 max-w-xs border-l",
} as const;

export interface SheetContentProps extends ComponentProps<typeof DialogPrimitive.Content> {
  side?: keyof typeof SIDE_CLASSES;
}

export function SheetContent({ className, side = "left", children, ...props }: SheetContentProps) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/50" />
      <DialogPrimitive.Content
        className={cn("fixed z-50 flex flex-col border-border bg-bg-elevated shadow-lg", SIDE_CLASSES[side], className)}
        {...props}
      >
        {children}
        <DialogPrimitive.Close className="absolute right-4 top-4 rounded-sm text-fg-muted hover:text-fg" aria-label="Fechar">
          <X className="size-4" />
        </DialogPrimitive.Close>
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
}

export function SheetHeader({ className, ...props }: ComponentProps<"div">) {
  return <div className={cn("border-b border-border p-4", className)} {...props} />;
}

export function SheetTitle({ className, ...props }: ComponentProps<typeof DialogPrimitive.Title>) {
  return <DialogPrimitive.Title className={cn("text-sm font-semibold text-fg", className)} {...props} />;
}
