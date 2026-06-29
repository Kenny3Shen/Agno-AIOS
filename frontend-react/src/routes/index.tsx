import { createFileRoute } from '@tanstack/react-router'

import { SecurityPlatform } from '#/components/security-platform.tsx'

export const Route = createFileRoute('/')({
  component: SecurityPlatform,
})
