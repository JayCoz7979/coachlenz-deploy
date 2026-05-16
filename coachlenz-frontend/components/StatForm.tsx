'use client'

import { useState } from 'react'

interface StatFormProps {
  sport: string
  initialStats?: Record<string, number>
  onChange: (stats: Record<string, number>) => void
}

const sportStatFields: Record<string, Array<{ key: string; label: string }>> = {
  football: [
    { key: 'passing_yards', label: 'Passing Yards' },
    { key: 'rushing_yards', label: 'Rushing Yards' },
    { key: 'receiving_yards', label: 'Receiving Yards' },
    { key: 'touchdowns', label: 'Touchdowns' },
    { key: 'tackles', label: 'Tackles' },
    { key: 'sacks', label: 'Sacks' },
    { key: 'interceptions', label: 'Interceptions' },
    { key: 'completions', label: 'Completions' },
    { key: 'attempts', label: 'Pass Attempts' },
  ],
  basketball: [
    { key: 'points', label: 'Points' },
    { key: 'rebounds', label: 'Rebounds' },
    { key: 'assists', label: 'Assists' },
    { key: 'steals', label: 'Steals' },
    { key: 'blocks', label: 'Blocks' },
    { key: 'turnovers', label: 'Turnovers' },
    { key: 'field_goals_made', label: 'FG Made' },
    { key: 'field_goals_attempted', label: 'FG Attempted' },
    { key: 'three_pointers', label: '3-Pointers' },
    { key: 'free_throws_made', label: 'FT Made' },
    { key: 'minutes', label: 'Minutes Played' },
  ],
  baseball: [
    { key: 'at_bats', label: 'At Bats' },
    { key: 'hits', label: 'Hits' },
    { key: 'runs', label: 'Runs' },
    { key: 'rbi', label: 'RBI' },
    { key: 'home_runs', label: 'Home Runs' },
    { key: 'walks', label: 'Walks' },
    { key: 'strikeouts_batting', label: 'Strikeouts (Bat)' },
    { key: 'stolen_bases', label: 'Stolen Bases' },
    { key: 'innings_pitched', label: 'Innings Pitched' },
    { key: 'earned_runs', label: 'Earned Runs' },
    { key: 'strikeouts_pitching', label: 'Strikeouts (Pitch)' },
    { key: 'walks_allowed', label: 'Walks Allowed' },
  ],
  softball: [
    { key: 'at_bats', label: 'At Bats' },
    { key: 'hits', label: 'Hits' },
    { key: 'runs', label: 'Runs' },
    { key: 'rbi', label: 'RBI' },
    { key: 'home_runs', label: 'Home Runs' },
    { key: 'walks', label: 'Walks' },
    { key: 'strikeouts_batting', label: 'Strikeouts (Bat)' },
    { key: 'stolen_bases', label: 'Stolen Bases' },
    { key: 'innings_pitched', label: 'Innings Pitched' },
    { key: 'earned_runs', label: 'Earned Runs' },
    { key: 'strikeouts_pitching', label: 'Strikeouts (Pitch)' },
  ],
  soccer: [
    { key: 'goals', label: 'Goals' },
    { key: 'assists', label: 'Assists' },
    { key: 'shots', label: 'Shots' },
    { key: 'shots_on_target', label: 'Shots on Target' },
    { key: 'saves', label: 'Saves (GK)' },
    { key: 'tackles', label: 'Tackles' },
    { key: 'yellow_cards', label: 'Yellow Cards' },
    { key: 'red_cards', label: 'Red Cards' },
    { key: 'minutes', label: 'Minutes Played' },
  ],
  volleyball: [
    { key: 'kills', label: 'Kills' },
    { key: 'assists', label: 'Assists' },
    { key: 'aces', label: 'Aces' },
    { key: 'digs', label: 'Digs' },
    { key: 'blocks', label: 'Blocks' },
    { key: 'errors', label: 'Errors' },
    { key: 'service_aces', label: 'Service Aces' },
    { key: 'reception_errors', label: 'Reception Errors' },
  ],
}

export default function StatForm({ sport, initialStats = {}, onChange }: StatFormProps) {
  const [stats, setStats] = useState<Record<string, number>>(initialStats)
  const fields = sportStatFields[sport] || []

  const handleChange = (key: string, value: string) => {
    const numVal = value === '' ? 0 : parseFloat(value)
    const updated = { ...stats, [key]: numVal }
    setStats(updated)
    onChange(updated)
  }

  if (fields.length === 0) {
    return (
      <div className="text-[#9ca3af] text-sm">
        No stat fields configured for sport: {sport}
      </div>
    )
  }

  return (
    <div className="grid grid-cols-2 gap-3">
      {fields.map((field) => (
        <div key={field.key}>
          <label className="block text-xs text-[#9ca3af] mb-1">{field.label}</label>
          <input
            type="number"
            min="0"
            step="0.5"
            value={stats[field.key] ?? ''}
            onChange={(e) => handleChange(field.key, e.target.value)}
            placeholder="0"
            className="w-full bg-[#0d0d0d] border border-[#1e1e1e] rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-[#2563eb] transition-colors"
          />
        </div>
      ))}
    </div>
  )
}
