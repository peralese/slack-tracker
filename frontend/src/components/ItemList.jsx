import { useCallback, useEffect, useRef, useState } from 'react';
import { getItems } from '../api';
import FilterBar from './FilterBar';
import ItemCard from './ItemCard';

const DEFAULT_FILTERS = { status: '', minScore: '', sortBy: 'score' };
const AUTO_REFRESH_MS = 5 * 60 * 1000; // 5 minutes

export default function ItemList() {
  const [items,     setItems]     = useState([]);
  const [filters,   setFilters]   = useState(DEFAULT_FILTERS);
  const [loading,   setLoading]   = useState(false);
  const [error,     setError]     = useState('');
  const [lastSync,  setLastSync]  = useState(null);
  const isFirstLoad = useRef(true);

  const fetchItems = useCallback(async ({ silent = false } = {}) => {
    if (!silent) setLoading(true);
    setError('');
    try {
      const data = await getItems({
        status:   filters.status   || undefined,
        minScore: filters.minScore !== '' ? filters.minScore : undefined,
        sortBy:   filters.sortBy,
      });
      setItems(data);
      setLastSync(new Date());
    } catch {
      setError('Could not load items. Is the backend running?');
    } finally {
      if (!silent) setLoading(false);
    }
  }, [filters]);

  // Fetch on mount and whenever filters change
  useEffect(() => {
    isFirstLoad.current = true;
    fetchItems({ silent: false });
    isFirstLoad.current = false;
  }, [fetchItems]);

  // Auto-refresh every 5 minutes (silent — no spinner)
  useEffect(() => {
    const timer = setInterval(() => {
      fetchItems({ silent: true });
    }, AUTO_REFRESH_MS);
    return () => clearInterval(timer);
  }, [fetchItems]);

  function handleUpdated(updatedItem) {
    setItems(prev => prev.map(it => it.id === updatedItem.id ? updatedItem : it));
  }

  return (
    <div className="item-list">
      <FilterBar filters={filters} onChange={setFilters} />

      {lastSync && (
        <p className="last-sync">
          Last updated: {lastSync.toLocaleTimeString()} · auto-refreshes every 5 min
        </p>
      )}

      {loading && <p className="status-msg">Loading…</p>}
      {error   && <p className="status-msg error">{error}</p>}
      {!loading && !error && items.length === 0 && (
        <p className="status-msg">No items match the current filters.</p>
      )}

      {items.map(item => (
        <ItemCard key={item.id} item={item} onUpdated={handleUpdated} />
      ))}
    </div>
  );
}
