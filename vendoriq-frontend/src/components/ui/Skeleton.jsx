export const SkeletonLine = ({ className = '' }) => (
  <div className={`skeleton h-4 ${className}`} />
)

export const SkeletonCard = () => (
  <div className="bg-[#162236] rounded-2xl border border-white/5 p-5 space-y-3">
    <SkeletonLine className="w-1/3" />
    <SkeletonLine className="w-2/3 h-8" />
    <SkeletonLine className="w-1/2" />
  </div>
)
