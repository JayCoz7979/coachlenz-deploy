import type { Metadata } from 'next'
import { closedPageRobots } from '@/lib/signups'

export const dynamic = 'force-dynamic'

export async function generateMetadata(): Promise<Metadata> {
  return closedPageRobots()
}

export default function ReferLayout({ children }: { children: React.ReactNode }) {
  return children
}