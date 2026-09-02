export default function FilterBar({ filters, onChange }) {
  const { status, minScore, sortBy } = filters;

  return (
    <div className="filter-bar">
      <label>
        Status
        <select value={status} onChange={e => onChange({ ...filters, status: e.target.value })}>
          <option value="">All</option>
          <option value="new">New</option>
          <option value="reviewed">Reviewed</option>
          <option value="follow_up">Follow Up</option>
          <option value="dismissed">Dismissed</option>
        </select>
      </label>

      <label>
        Min Score
        <input
          type="number"
          min="0"
          max="10"
          step="0.5"
          value={minScore}
          placeholder="0"
          onChange={e => onChange({ ...filters, minScore: e.target.value ? parseFloat(e.target.value) : '' })}
        />
      </label>

      <label>
        Sort By
        <select value={sortBy} onChange={e => onChange({ ...filters, sortBy: e.target.value })}>
          <option value="score">Relevance Score</option>
          <option value="date">Date Posted</option>
        </select>
      </label>
    </div>
  );
}
