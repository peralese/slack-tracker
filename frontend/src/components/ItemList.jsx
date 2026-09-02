import { useCallback, useEffect, useState } from 'react';
import { getItems } from '../api';
import FilterBar from './FilterBar';
import ItemCard from './ItemCard';

const DEFAULT_FILTERS = { status: '', minScore: '', sortBy: 'score' };

export default function ItemList() {
  const [items,   setItems]   = useState([]);
  const [filters, setFilters] = useState(DEFAULT_FILTERS);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState('');

  const fetchItems = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await getItems({
        status:   filters.status   || undefined,
        minScore: filters.minScore !== '' ? filters.minScore : undefined,
        sortBy:   filters.sortBy,
      });
      setItems(data);
    } catch {
      setError('Could not load items. Is the backend running?');
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => { fetchItems(); }, [fetchItems]);

  function handleUpdated(updatedItem) {
    setItems(prev => prev.map(it => it.id === updatedItem.id ? updatedItem : it));
  }

  return (
    <div className="item-list">
      <FilterBar filters={filters} onChange={setFilters} />

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
