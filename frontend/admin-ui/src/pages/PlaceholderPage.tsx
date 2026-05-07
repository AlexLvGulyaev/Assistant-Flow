interface PlaceholderPageProps {
  title: string;
}

export function PlaceholderPage({ title }: PlaceholderPageProps) {
  return (
    <div className="page">
      <h1 className="page__title">{title}</h1>
      <p className="page__lead muted">
        Page is not migrated from Streamlit yet.
      </p>
      <div className="panel panel--muted">
        Use the legacy Streamlit admin UI for full functionality until this
        section is ported to the React console.
      </div>
    </div>
  );
}
