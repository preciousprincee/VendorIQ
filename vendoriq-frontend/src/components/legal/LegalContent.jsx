// Small, consistent building blocks for legal-page content. Kept separate
// from LegalLayout.jsx (the page shell) so each policy file can compose its
// own structure freely: <Section title="..."><P>...</P><UL>...</UL></Section>
export function Section({ title, children }) {
  return (
    <section>
      <h2 className="text-base font-semibold text-slate-text mb-2">{title}</h2>
      <div className="space-y-3">{children}</div>
    </section>
  )
}

export function P({ children }) {
  return <p className="text-sm text-slate-muted leading-relaxed">{children}</p>
}

export function UL({ children }) {
  return <ul className="list-disc pl-5 space-y-1.5 text-sm text-slate-muted leading-relaxed">{children}</ul>
}
