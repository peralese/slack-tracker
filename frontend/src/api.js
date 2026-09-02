import axios from 'axios';

const api = axios.create({
  baseURL: 'http://127.0.0.1:8000',
  headers: { 'Content-Type': 'application/json' },
});

export function getItems({ status, minScore, sortBy } = {}) {
  const params = {};
  if (status)             params.status   = status;
  if (minScore != null)   params.min_score = minScore;
  if (sortBy)             params.sort_by  = sortBy;
  return api.get('/items', { params }).then(r => r.data);
}

export function updateStatus(id, status) {
  return api.patch(`/items/${id}/status`, { status }).then(r => r.data);
}

export function updateNotes(id, notes) {
  return api.patch(`/items/${id}/notes`, { notes }).then(r => r.data);
}

export function triggerPoll() {
  return api.post('/poll/trigger').then(r => r.data);
}
