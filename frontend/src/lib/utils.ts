import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

/**
 * Utility function to merge Tailwind CSS classes efficiently,
 * resolving conflicts appropriately.
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
