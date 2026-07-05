interface QuickRepliesProps {
  options: Array<{ label: string; value: string }>
  onSelect: (value: string) => void
  disabled: boolean
}

export default function QuickReplies({ options, onSelect, disabled }: QuickRepliesProps) {
  if (!options || options.length === 0) return null

  return (
    <div className="mt-2 flex flex-wrap gap-2">
      {options.map((option) => (
        <button
          key={option.value}
          onClick={() => onSelect(option.value)}
          disabled={disabled}
          className="rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1 text-sm text-indigo-700 transition hover:bg-indigo-100 disabled:opacity-50"
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}
