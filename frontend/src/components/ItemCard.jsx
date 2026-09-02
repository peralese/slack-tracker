import { useState } from 'react';
import { updateNotes, updateStatus } from '../api';

const STATUS_LABELS = {
  new:       'New',
  reviewed:  'Reviewed',
  follow_up: 'Follow Up',
  dismissed: 'Dismissed',
};

function ScoreBadge({ score }) {
  const cls =
    score >= 7 ? 'badge badge-green' :
    score >= 4 ? 'badge badge-yellow' :
                 'badge badge-red';
  return <span className={cls}>{score.toFixed(1)}</span>;
}

export default function ItemCard({ item, onUpdated }) {
  const [notes, setNotes]     = useState(item.user_notes || '');
  const [saving, setSaving]   = useState(false);
  const [error, setError]     = useState('');

  async function handleStatusChange(e) {
    const newStatus = e.target.value;
    try {
      const updated = await updateStatus(item.id, newStatus);
      onUpdated(updated);
    } catch {
      setError('Failed to update status.');
    }
  }

  async function handleSaveNotes() {
    setSaving(true);
    setError('');
    try {
      const updated = await updateNotes(item.id, notes);
      onUpdated(updated);
    } catch {
      setError('Failed to save notes.');
    } finally {
      setSaving(false);
    }
  }

  const postedAt = item.posted_at
    ? new Date(item.posted_at).toLocaleString()
    : '—';

  return (
    <div className="item-card">
      <div className="item-card-header">
        <ScoreBadge score={item.relevance_score} />
        <span className="item-date">{postedAt}</span>
        <select
          className="status-select"
          value={item.status}
          onChange={handleStatusChange}
        >
          {Object.entries(STATUS_LABELS).map(([val, label]) => (
            <option key={val} value={val}>{label}</option>
          ))}
        </select>
      </div>

      {item.relevance_explanation && (
        <p className="relevance-explanation">{item.relevance_explanation}</p>
      )}

      <p className="raw-text">{item.raw_text || <em>No message text</em>}</p>

      {item.event_dates?.length > 0 && (
        <div className="dates-section">
          <strong>📅 Dates Mentioned</strong>
          <div className="date-pills">
            {item.event_dates.map((d, i) => (
              <span key={i} className="date-pill">{d}</span>
            ))}
          </div>
        </div>
      )}

      {item.doc_summary && (
        item.doc_summary === 'Summary unavailable — document attached but could not be processed.'
          ? (
            <div className="doc-summary-failed">
              <strong>📄 Document Summary</strong>
              {item.doc_summary}
            </div>
          ) : (
            <div className="doc-summary">
              <strong>📄 Document Summary</strong>
              {item.doc_summary}
            </div>
          )
      )}

      {item.extracted_urls?.length > 0 && (
        <div className="urls">
          <strong>Links:</strong>
          <ul>
            {item.extracted_urls.map((url, i) => (
              <li key={i}>
                <a href={url} target="_blank" rel="noreferrer">{url}</a>
              </li>
            ))}
          </ul>
        </div>
      )}

      {item.attachment_names?.length > 0 && (
        <div className="attachments">
          <strong>Attachments:</strong>
          <ul>
            {item.attachment_names.map((name, i) => (
              <li key={i}>{name}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="notes-section">
        <textarea
          rows={2}
          placeholder="Add notes…"
          value={notes}
          onChange={e => setNotes(e.target.value)}
        />
        <button onClick={handleSaveNotes} disabled={saving}>
          {saving ? 'Saving…' : 'Save Notes'}
        </button>
      </div>

      {error && <p className="card-error">{error}</p>}
    </div>
  );
}
