interface PlayerBadgeProps {
  status: 'active' | 'injured' | 'inactive' | string
  className?: string
}

const statusConfig = {
  active: {
    label: 'Active',
    classes: 'bg-green-900/40 text-green-400 border border-green-800',
  },
  injured: {
    label: 'Injured',
    classes: 'bg-red-900/40 text-red-400 border border-red-800',
  },
  inactive: {
    label: 'Inactive',
    classes: 'bg-gray-800/60 text-gray-400 border border-gray-700',
  },
}

export default function PlayerBadge({ status, className = '' }: PlayerBadgeProps) {
  const config = statusConfig[status as keyof typeof statusConfig] ?? {
    label: status,
    classes: 'bg-gray-800/60 text-gray-400 border border-gray-700',
  }

  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${config.classes} ${className}`}
    >
      <span
        className={`w-1.5 h-1.5 rounded-full mr-1.5 ${
          status === 'active'
            ? 'bg-green-400'
            : status === 'injured'
            ? 'bg-red-400'
            : 'bg-gray-500'
        }`}
      />
      {config.label}
    </span>
  )
}
