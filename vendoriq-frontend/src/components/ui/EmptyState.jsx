export default function EmptyState({ icon: Icon, title, description, action }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-4 text-center">
      {Icon && (
        <div className="w-14 h-14 rounded-2xl bg-white/5 flex items-center justify-center mb-4">
          <Icon size={24} className="text-[#8896A5]" />
        </div>
      )}
      <h3 className="font-semibold text-white mb-1">{title}</h3>
      <p className="text-sm text-[#8896A5] mb-6 max-w-xs">{description}</p>
      {action}
    </div>
  )
}
